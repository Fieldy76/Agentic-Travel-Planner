import json

import pytest

from travel_agent.mcp.mcp_server import MCPServer


def sync_tool(a: int, b: str = "x") -> dict:
    """A short docstring."""
    return {"a": a, "b": b}


async def async_tool(name: str) -> str:
    return f"hello {name}"


def tool_raises_value_error(x: int):
    raise ValueError("bad input")


def tool_raises_generic(x: int):
    raise RuntimeError("kaboom")


def test_register_uses_docstring_as_description():
    srv = MCPServer()
    srv.register_tool(sync_tool)
    defn = srv.list_tools()[0]
    assert defn["description"] == "A short docstring."
    assert defn["inputSchema"]["properties"]["a"]["type"] == "integer"
    assert defn["inputSchema"]["properties"]["b"]["type"] == "string"
    assert defn["inputSchema"]["required"] == ["a"]


async def test_call_async_tool():
    srv = MCPServer()
    srv.register_tool(async_tool)
    result = await srv.call_tool("async_tool", {"name": "world"})
    assert not result.isError
    assert result.content[0]["text"] == "hello world"


async def test_call_sync_tool_jsonifies_dict():
    srv = MCPServer()
    srv.register_tool(sync_tool)
    result = await srv.call_tool("sync_tool", {"a": 3})
    assert not result.isError
    parsed = json.loads(result.content[0]["text"])
    assert parsed == {"a": 3, "b": "x"}


async def test_missing_required_arg_returns_error():
    srv = MCPServer()
    srv.register_tool(sync_tool)
    result = await srv.call_tool("sync_tool", {})
    assert result.isError
    assert "Missing required arguments" in result.content[0]["text"]


async def test_unknown_arg_is_dropped():
    srv = MCPServer()
    srv.register_tool(sync_tool)
    result = await srv.call_tool("sync_tool", {"a": 5, "hallucinated": "x"})
    assert not result.isError


async def test_unknown_tool_returns_error():
    srv = MCPServer()
    result = await srv.call_tool("does_not_exist", {})
    assert result.isError
    assert "Tool not found" in result.content[0]["text"]


async def test_value_error_returned_cleanly():
    srv = MCPServer()
    srv.register_tool(tool_raises_value_error)
    result = await srv.call_tool("tool_raises_value_error", {"x": 1})
    assert result.isError
    assert "Invalid input" in result.content[0]["text"]


async def test_generic_error_caught():
    srv = MCPServer()
    srv.register_tool(tool_raises_generic)
    result = await srv.call_tool("tool_raises_generic", {"x": 1})
    assert result.isError
    assert "Error executing tool" in result.content[0]["text"]
