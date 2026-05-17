import contextlib
import inspect
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from .protocol import CallToolResult, create_tool_definition

logger = logging.getLogger(__name__)

_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

_SUBPROCESS_MARKER = "__mcp_subprocess_proxy__"


class MCPServer:
    """In-process tool server with optional stdio MCP subprocess integration.

    Tools registered via ``register_tool`` run in-process. Tools discovered
    via ``register_mcp_subprocess`` are proxied to a Node/Python MCP server
    spawned as a subprocess (Google Maps, filesystem, etc.). To the LLM and
    the orchestrator they look identical — same tool list, same call_tool API.
    """

    def __init__(self) -> None:
        self.tools: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict[str, Any]] = []
        self._exit_stack: Optional[contextlib.AsyncExitStack] = None

    # ------------------------------------------------------------------
    # In-process registration (unchanged behaviour)
    # ------------------------------------------------------------------
    def register_tool(self, func: Callable, name: str | None = None, description: str | None = None) -> None:
        tool_name = name or func.__name__
        tool_description = description or (inspect.getdoc(func) or "").strip()
        sig = inspect.signature(func)

        properties: Dict[str, Dict[str, Any]] = {}
        required: List[str] = []
        for param_name, param in sig.parameters.items():
            properties[param_name] = {
                "type": _TYPE_MAP.get(param.annotation, "string"),
                "description": f"Parameter {param_name}",
            }
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        parameters = {"type": "object", "properties": properties, "required": required}
        self.tools[tool_name] = func
        self.tool_definitions.append(create_tool_definition(tool_name, tool_description, parameters))

    # ------------------------------------------------------------------
    # Stdio MCP subprocess integration
    # ------------------------------------------------------------------
    async def register_mcp_subprocess(
        self,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None,
        *,
        label: str = "",
    ) -> int:
        """Spawn an MCP server subprocess, discover its tools, register them.

        Returns the number of tools registered. The subprocess stays alive
        for the lifetime of the ``MCPServer`` instance (closed by ``close``).
        Tool names collide with the in-process registry on a last-write-wins
        basis; we log a warning when that happens.
        """
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        if self._exit_stack is None:
            self._exit_stack = contextlib.AsyncExitStack()

        params = StdioServerParameters(command=command, args=args, env=env)
        read_stream, write_stream = await self._exit_stack.enter_async_context(stdio_client(params))
        session: ClientSession = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        listing = await session.list_tools()
        registered = 0
        for tool in listing.tools:
            if tool.name in self.tools:
                logger.warning(
                    "MCP subprocess tool %r collides with existing tool; overwriting (source=%s)",
                    tool.name, label or command,
                )
                # Drop stale definition so we don't ship two entries to the LLM.
                self.tool_definitions = [d for d in self.tool_definitions if d.get("name") != tool.name]

            self.tools[tool.name] = self._make_subprocess_proxy(session, tool.name)
            self.tool_definitions.append(
                create_tool_definition(
                    tool.name,
                    tool.description or "",
                    tool.inputSchema or {"type": "object", "properties": {}, "required": []},
                )
            )
            registered += 1

        logger.info(
            "Registered %d tool(s) from MCP subprocess %s", registered, label or command,
        )
        return registered

    @staticmethod
    def _make_subprocess_proxy(session, tool_name: str) -> Callable:
        async def _proxy(**kwargs: Any) -> CallToolResult:
            remote = await session.call_tool(tool_name, kwargs or {})
            content: List[Dict[str, Any]] = []
            for item in (remote.content or []):
                if getattr(item, "type", None) == "text":
                    content.append({"type": "text", "text": item.text})
                elif getattr(item, "type", None) == "image":
                    content.append(
                        {
                            "type": "image",
                            "data": getattr(item, "data", ""),
                            "mimeType": getattr(item, "mimeType", ""),
                        }
                    )
                else:
                    content.append({"type": "text", "text": str(item)})
            return CallToolResult(content=content, isError=bool(remote.isError))

        setattr(_proxy, _SUBPROCESS_MARKER, True)
        return _proxy

    async def close(self) -> None:
        """Shut down any registered MCP subprocesses cleanly."""
        if self._exit_stack is not None:
            try:
                await self._exit_stack.aclose()
            except Exception:
                logger.exception("Failed to close MCP subprocess exit stack")
            finally:
                self._exit_stack = None

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    def list_tools(self) -> List[Dict[str, Any]]:
        return self.tool_definitions

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        if name not in self.tools:
            return CallToolResult(
                content=[{"type": "text", "text": f"Tool not found: {name}"}],
                isError=True,
            )

        func = self.tools[name]

        # Subprocess proxies validate args remotely and already return a
        # CallToolResult — skip the inspect-based argument filtering.
        if getattr(func, _SUBPROCESS_MARKER, False):
            try:
                return await func(**(arguments or {}))
            except Exception as e:
                logger.exception("MCP subprocess tool %s raised", name)
                return CallToolResult(
                    content=[{"type": "text", "text": f"Error executing tool {name}: {e}"}],
                    isError=True,
                )

        sig = inspect.signature(func)
        accepted = set(sig.parameters)

        # Strip parameters the function doesn't accept (LLMs occasionally hallucinate extras).
        filtered = {k: v for k, v in (arguments or {}).items() if k in accepted}

        # Check required args are present.
        missing = [
            n for n, p in sig.parameters.items()
            if p.default is inspect.Parameter.empty and n not in filtered
        ]
        if missing:
            return CallToolResult(
                content=[{"type": "text", "text": f"Missing required arguments: {missing}"}],
                isError=True,
            )

        try:
            if inspect.iscoroutinefunction(func):
                result = await func(**filtered)
            else:
                result = func(**filtered)
        except ValueError as e:
            # Validation errors raised by the tool itself — return cleanly.
            return CallToolResult(
                content=[{"type": "text", "text": f"Invalid input: {e}"}],
                isError=True,
            )
        except Exception as e:
            logger.exception("Tool %s raised", name)
            return CallToolResult(
                content=[{"type": "text", "text": f"Error executing tool {name}: {e}"}],
                isError=True,
            )

        # Preserve structure: JSON-serialise dicts/lists; pass scalars through as str.
        if isinstance(result, (dict, list)):
            text = json.dumps(result, default=str, ensure_ascii=False)
        else:
            text = str(result)
        return CallToolResult(content=[{"type": "text", "text": text}], isError=False)
