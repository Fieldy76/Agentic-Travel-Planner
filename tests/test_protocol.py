import pytest
from pydantic import ValidationError

from travel_agent.mcp.protocol import (
    CallToolRequest,
    CallToolResult,
    JsonRpcRequest,
    JsonRpcResponse,
    create_tool_definition,
)


def test_jsonrpc_request_defaults_version():
    req = JsonRpcRequest(method="tools/list")
    assert req.jsonrpc == "2.0"
    assert req.to_dict() == {"method": "tools/list", "jsonrpc": "2.0"}


def test_jsonrpc_request_rejects_wrong_version():
    with pytest.raises(ValidationError):
        JsonRpcRequest(method="tools/list", jsonrpc="1.0")


def test_jsonrpc_response_excludes_none():
    resp = JsonRpcResponse(result={"ok": True}, id=1)
    d = resp.to_dict()
    assert "error" not in d
    assert d["result"] == {"ok": True}


def test_call_tool_request_round_trip():
    req = CallToolRequest(name="x", arguments={"a": 1})
    assert req.name == "x"
    assert req.arguments == {"a": 1}


def test_call_tool_result_is_error_default():
    result = CallToolResult(content=[{"type": "text", "text": "ok"}])
    assert result.isError is False


def test_create_tool_definition():
    d = create_tool_definition("x", "desc", {"type": "object", "properties": {}})
    assert d["name"] == "x"
    assert d["description"] == "desc"
    assert d["inputSchema"]["type"] == "object"
