# Import type hints for better code documentation and IDE support
from typing import Any, Dict, List, Optional, Union
# Import Pydantic for runtime data validation
# BaseModel provides the base class for validated data structures
# Field allows us to add constraints and metadata to fields
from pydantic import BaseModel, Field

# JSON-RPC 2.0 Constants
# The Model Context Protocol (MCP) uses JSON-RPC 2.0 for communication
JSONRPC_VERSION = "2.0"

# JSON-RPC Request Model
# Represents a request sent from client to server
# Pydantic will automatically validate all incoming requests against this schema
class JsonRpcRequest(BaseModel):
    method: str  # The name of the method to invoke (e.g., "tools/list")
    params: Optional[Dict[str, Any]] = None  # Optional parameters for the method
    id: Optional[Union[str, int]] = None  # Optional request ID for matching responses
    # Field with validation pattern - ensures version is exactly "2.0"
    # This prevents protocol version mismatches
    jsonrpc: str = Field(default=JSONRPC_VERSION, pattern=r"^2\.0$")

    def to_dict(self) -> Dict[str, Any]:
        """Convert the Pydantic model to a dictionary for serialization."""
        # model_dump() is Pydantic v2 method (replaces dict() from v1)
        # exclude_none=True means fields with None values won't be in the output
        return self.model_dump(exclude_none=True)

# JSON-RPC Response Model
# Represents a response from server to client
class JsonRpcResponse(BaseModel):
    result: Any = None  # The result of a successful method call
    error: Optional[Dict[str, Any]] = None  # Error object if the call failed
    id: Optional[Union[str, int]] = None  # Matches the request ID
    # Validate that jsonrpc version is "2.0"
    jsonrpc: str = Field(default=JSONRPC_VERSION, pattern=r"^2\.0$")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return self.model_dump(exclude_none=True)

# MCP Specific Structures

# Tool Definition Model
# Describes a tool (function) that the LLM can call
class Tool(BaseModel):
    name: str  # Unique identifier for the tool (e.g., "search_flights")
    description: str  # Human-readable description of what the tool does
    inputSchema: Dict[str, Any]  # JSON Schema describing the tool's parameters

# Call Tool Request Model
# Represents a request from the LLM to invoke a specific tool
class CallToolRequest(BaseModel):
    name: str  # Which tool to call
    arguments: Dict[str, Any]  # Arguments to pass to the tool

# Call Tool Result Model
# Represents the result of a tool invocation
class CallToolResult(BaseModel):
    # Content is a list of response objects
    # Each object has a "text" key with the tool's output
    content: List[Dict[str, Any]]
    # Flag indicating if the tool execution resulted in an error
    isError: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump()

# Helper function to create a tool definition
# This ensures all tool definitions follow the standard format
def create_tool_definition(name: str, description: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a validated tool definition.
    
    Args:
        name: Tool identifier
        description: What the tool does
        parameters: JSON Schema for the tool's input
        
    Returns:
        Dictionary representation of the tool
    """
    # Create a Tool instance - Pydantic will validate the inputs
    tool = Tool(name=name, description=description, inputSchema=parameters)
    # Convert to dictionary for transmission
    return tool.model_dump()
