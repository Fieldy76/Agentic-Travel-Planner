"""
================================================================================
MCP PROTOCOL - Model Context Protocol Data Types
================================================================================

This module defines the core data types used in the MCP (Model Context Protocol)
implementation. These types provide a standard format for tool definitions,
requests, and responses.

Protocol Overview:
------------------
MCP is inspired by JSON-RPC 2.0 and provides a standardized way for LLMs
to interact with external tools. This implementation includes:

1. JSON-RPC Base Types: Standard request/response format
2. Tool Definition: Schema describing callable tools
3. Tool Execution: Request and result types for tool calls

JSON-RPC 2.0:
-------------
JSON-RPC is a remote procedure call protocol encoded in JSON.
Format: {"jsonrpc": "2.0", "method": "...", "params": {...}, "id": 1}

MCP Tool Format:
----------------
Tools are described using JSON Schema:

    {
        "name": "search_flights",
        "description": "Search for flights...",
        "inputSchema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string"},
                "destination": {"type": "string"}
            },
            "required": ["origin", "destination"]
        }
    }

Pydantic Usage:
---------------
This module uses Pydantic for:
- Data validation (automatic type checking)
- Serialization (model_dump() for JSON conversion)
- Documentation (field descriptions)

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

from typing import Any, Dict, List, Optional, Union  # Type hints
from pydantic import BaseModel, Field                 # Data validation

# =============================================================================
# CONSTANTS
# =============================================================================

# JSON-RPC version constant
# MCP is based on JSON-RPC 2.0 specification
JSONRPC_VERSION = "2.0"

# =============================================================================
# JSON-RPC BASE TYPES
# =============================================================================

class JsonRpcRequest(BaseModel):
    """
    Standard JSON-RPC 2.0 request object.
    
    This class represents a request message in the JSON-RPC 2.0 format.
    While not directly used in this simplified MCP implementation,
    it provides the foundation for a full MCP client-server setup.
    
    Attributes:
        method (str): The name of the method to invoke
        params (dict, optional): Parameters for the method call
        id (str|int, optional): Request identifier for matching responses
        jsonrpc (str): Protocol version, always "2.0"
    
    Example:
        >>> request = JsonRpcRequest(
        ...     method="tools/call",
        ...     params={"name": "search_flights", "arguments": {...}},
        ...     id=1
        ... )
        >>> print(request.to_dict())
        {"jsonrpc": "2.0", "method": "tools/call", "params": {...}, "id": 1}
    """
    method: str  # Required: The method being called
    
    # Optional parameters for the method call
    params: Optional[Dict[str, Any]] = None
    
    # Optional request ID for matching with response
    # Can be string or integer; None for notifications (fire-and-forget)
    id: Optional[Union[str, int]] = None
    
    # Protocol version - validated with regex to ensure "2.0"
    jsonrpc: str = Field(default=JSONRPC_VERSION, pattern=r"^2\.0$")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary, excluding None values.
        
        Returns:
            dict: JSON-RPC request as dictionary
        """
        return self.model_dump(exclude_none=True)


class JsonRpcResponse(BaseModel):
    """
    Standard JSON-RPC 2.0 response object.
    
    A response contains either a result (success) or an error (failure),
    never both. The id field matches the corresponding request.
    
    Attributes:
        result (Any, optional): The result of a successful method call
        error (dict, optional): Error object if method failed
        id (str|int, optional): ID matching the request
        jsonrpc (str): Protocol version, always "2.0"
    
    Success Response:
        {"jsonrpc": "2.0", "result": {...}, "id": 1}
    
    Error Response:
        {"jsonrpc": "2.0", "error": {"code": -32600, "message": "..."}, "id": 1}
    """
    # Success result (exclusive with error)
    result: Any = None
    
    # Error object for failures (exclusive with result)
    # Format: {"code": int, "message": str, "data": optional}
    error: Optional[Dict[str, Any]] = None
    
    # Response ID matching the request
    id: Optional[Union[str, int]] = None
    
    # Protocol version
    jsonrpc: str = Field(default=JSONRPC_VERSION, pattern=r"^2\.0$")

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary, excluding None values.
        
        Returns:
            dict: JSON-RPC response as dictionary
        """
        return self.model_dump(exclude_none=True)

# =============================================================================
# MCP SPECIFIC TYPES
# =============================================================================

class Tool(BaseModel):
    """
    Represents a tool definition in MCP format.
    
    Tools are the core concept in MCP - they represent functions that
    the LLM can call to interact with external systems.
    
    Attributes:
        name (str): Unique identifier for the tool
        description (str): Human-readable description of what the tool does
        inputSchema (dict): JSON Schema describing the tool's parameters
    
    The inputSchema follows JSON Schema draft-07 format:
        {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "..."},
                "param2": {"type": "integer"}
            },
            "required": ["param1"]
        }
    
    Example:
        >>> tool = Tool(
        ...     name="get_weather",
        ...     description="Get weather forecast for a location",
        ...     inputSchema={
        ...         "type": "object",
        ...         "properties": {
        ...             "location": {"type": "string"},
        ...             "date": {"type": "string"}
        ...         },
        ...         "required": ["location"]
        ...     }
        ... )
    """
    name: str                      # Tool identifier (e.g., "search_flights")
    description: str               # Human-readable description
    inputSchema: Dict[str, Any]    # JSON Schema for parameters


class CallToolRequest(BaseModel):
    """
    Request to execute a specific tool.
    
    This represents the data needed to invoke a tool, separating
    the tool name from its arguments.
    
    Attributes:
        name (str): Name of the tool to call
        arguments (dict): Arguments to pass to the tool
    
    Example:
        >>> request = CallToolRequest(
        ...     name="search_flights",
        ...     arguments={"origin": "NYC", "destination": "LAX", "date": "2024-03-15"}
        ... )
    """
    name: str                      # Tool to invoke
    arguments: Dict[str, Any]      # Arguments for the tool


class CallToolResult(BaseModel):
    """
    Result from executing a tool.
    
    This standardizes the format of tool execution results,
    distinguishing between successful results and errors.
    
    Attributes:
        content (List[dict]): List of content blocks (usually text)
        isError (bool): Whether the result represents an error
    
    Content Format:
        The content field is a list of content blocks. For most tools,
        this is a single text block:
        
            [{"type": "text", "text": "Result text here"}]
        
        This format allows for future extension to include images,
        structured data, or other content types.
    
    Success Example:
        >>> result = CallToolResult(
        ...     content=[{"type": "text", "text": "Flight found: AA123"}],
        ...     isError=False
        ... )
    
    Error Example:
        >>> result = CallToolResult(
        ...     content=[{"type": "text", "text": "No flights available"}],
        ...     isError=True
        ... )
    """
    # List of content blocks (typically text)
    content: List[Dict[str, Any]]
    
    # Flag indicating if this is an error result
    isError: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.
        
        Returns:
            dict: Result as dictionary
        """
        return self.model_dump()

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_tool_definition(name: str, description: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a tool definition dictionary from component parts.
    
    This is a convenience function for creating tool definitions
    consistently. It creates a Tool model and converts it to a dict.
    
    Args:
        name: Unique tool identifier
        description: Human-readable description of the tool
        parameters: JSON Schema for the tool's input parameters
    
    Returns:
        dict: Tool definition ready for LLM consumption
    
    Example:
        >>> definition = create_tool_definition(
        ...     name="add_numbers",
        ...     description="Add two numbers together",
        ...     parameters={
        ...         "type": "object",
        ...         "properties": {
        ...             "a": {"type": "integer"},
        ...             "b": {"type": "integer"}
        ...         },
        ...         "required": ["a", "b"]
        ...     }
        ... )
        >>> print(definition["name"])
        "add_numbers"
    """
    tool = Tool(name=name, description=description, inputSchema=parameters)
    return tool.model_dump()
