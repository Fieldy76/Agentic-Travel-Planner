from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import json

# JSON-RPC 2.0 Constants
JSONRPC_VERSION = "2.0"

@dataclass
class JsonRpcRequest:
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None
    jsonrpc: str = JSONRPC_VERSION

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
        }
        if self.params is not None:
            data["params"] = self.params
        if self.id is not None:
            data["id"] = self.id
        return data

@dataclass
class JsonRpcResponse:
    result: Any = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None
    jsonrpc: str = JSONRPC_VERSION

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "jsonrpc": self.jsonrpc,
            "id": self.id
        }
        if self.error:
            data["error"] = self.error
        else:
            data["result"] = self.result
        return data

# MCP Specific Structures

@dataclass
class Tool:
    name: str
    description: str
    inputSchema: Dict[str, Any]

@dataclass
class CallToolRequest:
    name: str
    arguments: Dict[str, Any]

@dataclass
class CallToolResult:
    content: List[Dict[str, Any]]
    isError: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "isError": self.isError
        }

# Helper to create a tool definition
def create_tool_definition(name: str, description: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": parameters
    }
