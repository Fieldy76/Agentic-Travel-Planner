import inspect
import json
import logging
from typing import Any, Callable, Dict, List

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


class MCPServer:
    """In-process tool server. Schemas inferred from function signatures + docstrings."""

    def __init__(self) -> None:
        self.tools: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict[str, Any]] = []

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

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.tool_definitions

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        if name not in self.tools:
            return CallToolResult(
                content=[{"type": "text", "text": f"Tool not found: {name}"}],
                isError=True,
            )

        func = self.tools[name]
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
