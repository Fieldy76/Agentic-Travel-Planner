import unittest
from travel_agent.mcp.protocol import JsonRpcRequest, JsonRpcResponse, Tool, CallToolRequest, CallToolResult
from pydantic import ValidationError

class TestProtocol(unittest.TestCase):
    def test_json_rpc_request_valid(self):
        req = JsonRpcRequest(method="test", params={"a": 1}, id=1)
        self.assertEqual(req.jsonrpc, "2.0")
        self.assertEqual(req.method, "test")
        
    def test_json_rpc_request_invalid_version(self):
        with self.assertRaises(ValidationError):
            JsonRpcRequest(method="test", jsonrpc="1.0")

    def test_tool_definition(self):
        tool = Tool(name="my_tool", description="desc", inputSchema={"type": "object"})
        self.assertEqual(tool.name, "my_tool")
        
    def test_call_tool_result(self):
        res = CallToolResult(content=[{"text": "ok"}])
        self.assertFalse(res.isError)
        self.assertEqual(res.to_dict()["content"][0]["text"], "ok")

if __name__ == "__main__":
    unittest.main()
