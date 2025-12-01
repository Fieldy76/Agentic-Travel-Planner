from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

# JSON-RPC 2.0 Constants
JSONRPC_VERSION = "2.0"

class JsonRpcRequest(BaseModel):
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None
    jsonrpc: str = Field(default=JSONRPC_VERSION, pattern=r"^2\.0$")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)

class JsonRpcResponse(BaseModel):
    result: Any = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None
    jsonrpc: str = Field(default=JSONRPC_VERSION, pattern=r"^2\.0$")

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(exclude_none=True)

# MCP Specific Structures

class Tool(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any]

class CallToolRequest(BaseModel):
    name: str
    arguments: Dict[str, Any]

class CallToolResult(BaseModel):
    content: List[Dict[str, Any]]
    isError: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()

# Helper to create a tool definition
def create_tool_definition(name: str, description: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    tool = Tool(name=name, description=description, inputSchema=parameters)
    return tool.model_dump()
