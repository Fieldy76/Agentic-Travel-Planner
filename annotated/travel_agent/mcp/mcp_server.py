"""
================================================================================
MCP SERVER - Model Context Protocol Server Implementation
================================================================================

This module implements a simplified MCP (Model Context Protocol) server that
manages tool registration, introspection, and execution. It serves as the
bridge between the LLM and the actual tool functions.

What is MCP?
------------
Model Context Protocol is a standard for connecting LLMs to external tools
and data sources. This implementation provides a lightweight, in-process
version of an MCP server, handling:

1. Tool Registration: Register Python functions as callable tools
2. Schema Generation: Automatically generate JSON schemas from function signatures
3. Tool Discovery: List available tools with their schemas for the LLM
4. Tool Execution: Call tools by name with validated arguments

Architecture:
-------------
    ┌─────────────────────────────────────────────────────┐
    │              AgentOrchestrator                      │
    │         (Coordinates LLM and Tools)                 │
    └────────────────────┬────────────────────────────────┘
                         │
                         │ list_tools()
                         │ call_tool()
                         ▼
    ┌─────────────────────────────────────────────────────┐
    │                  MCP Server                         │
    │  ┌───────────────────────────────────────────────┐ │
    │  │              Tool Registry                     │ │
    │  │  ┌─────────┐  ┌─────────┐  ┌─────────┐       │ │
    │  │  │search_  │  │book_    │  │get_     │  ...  │ │
    │  │  │flights  │  │flight   │  │forecast │       │ │
    │  │  └────┬────┘  └────┬────┘  └────┬────┘       │ │
    │  │       │            │            │             │ │
    │  │       ▼            ▼            ▼             │ │
    │  │    Schema       Schema       Schema           │ │
    │  └───────────────────────────────────────────────┘ │
    └─────────────────────────────────────────────────────┘

JSON Schema Generation:
-----------------------
When a tool is registered, the server inspects its function signature
and generates a JSON Schema that describes its parameters:

    Python Function:
        async def search_flights(origin: str, destination: str, date: str):
            '''Search for flights between airports.'''
            ...
    
    Generated Schema:
        {
            "name": "search_flights",
            "description": "Search for flights between airports.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "Parameter origin"},
                    "destination": {"type": "string", "description": "Parameter destination"},
                    "date": {"type": "string", "description": "Parameter date"}
                },
                "required": ["origin", "destination", "date"]
            }
        }

Async Support:
--------------
The server supports both synchronous and asynchronous tool functions.
It automatically detects if a function is async and handles it appropriately.

Pydantic Integration:
---------------------
While this implementation uses Python's inspect module for schema generation,
the architecture supports Pydantic models for more complex validation.
See the FlightSearchArgs class in flights.py for an example.

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import inspect                                # Function signature introspection
from typing import Callable, Dict, Any, List  # Type hints
from .protocol import Tool, create_tool_definition, CallToolResult  # MCP types
from pydantic import BaseModel                # For type checking Pydantic models

# =============================================================================
# MCP SERVER CLASS
# =============================================================================

class MCPServer:
    """
    A simple in-process MCP Server to host tools.
    
    This class manages the lifecycle of tools from registration through
    execution, providing a clean interface for the orchestrator.
    
    Key Features:
    - Automatic JSON schema generation from function signatures
    - Support for both sync and async tool functions
    - Error handling with standardized result format
    - Type hint inspection for accurate schema types
    
    Attributes:
        tools (Dict[str, Callable]): Map of tool names to functions
        tool_definitions (List[Dict]): List of tool schemas for LLM
        tool_models (Dict[str, BaseModel]): Optional Pydantic models for validation
    
    Example:
        >>> server = MCPServer()
        >>> 
        >>> # Register a simple tool
        >>> @server.register_tool
        ... async def greeting(name: str) -> str:
        ...     '''Greet someone by name.'''
        ...     return f"Hello, {name}!"
        >>> 
        >>> # List available tools
        >>> tools = server.list_tools()
        >>> print(tools[0]["name"])
        "greeting"
        >>> 
        >>> # Call a tool
        >>> result = await server.call_tool("greeting", {"name": "World"})
        >>> print(result.content[0]["text"])
        "Hello, World!"
    """
    
    def __init__(self):
        """
        Initialize an empty MCP Server.
        
        Creates empty registries for tools and their definitions.
        Tools must be registered explicitly using register_tool().
        """
        # Map of tool names to their implementation functions
        self.tools: Dict[str, Callable] = {}
        
        # List of tool definitions (JSON schemas) for LLM consumption
        self.tool_definitions: List[Dict[str, Any]] = []
        
        # Optional: Pydantic models for input validation
        # Currently unused but ready for future enhancement
        self.tool_models: Dict[str, BaseModel] = {}

    def register_tool(self, func: Callable, name: str = None, description: str = None):
        """
        Register a Python function as an MCP tool.
        
        This method:
        1. Extracts tool name (from function name or explicit parameter)
        2. Extracts description (from docstring or explicit parameter)
        3. Inspects function signature to generate JSON schema
        4. Stores the function and its definition
        
        Args:
            func: The function to register as a tool
            name: Optional explicit name (defaults to function.__name__)
            description: Optional explicit description (defaults to docstring)
        
        Returns:
            None. The tool is registered in-place.
        
        Type Mapping:
            Python Type    -> JSON Schema Type
            str           -> "string"
            int           -> "integer"
            float         -> "number"
            bool          -> "boolean"
            list          -> "array"
            dict          -> "object"
            (other/none)  -> "string" (default)
        
        Required Parameters:
            Parameters without default values are marked as required in the schema.
            Parameters with default values are optional.
        
        Example:
            >>> async def my_tool(required_arg: str, optional_arg: int = 10):
            ...     '''Do something useful.'''
            ...     pass
            >>> 
            >>> server.register_tool(my_tool)
            >>> # Results in schema:
            >>> # {
            >>> #     "required": ["required_arg"],
            >>> #     "properties": {
            >>> #         "required_arg": {"type": "string"},
            >>> #         "optional_arg": {"type": "integer"}
            >>> #     }
            >>> # }
        """
        # Use function name if not explicitly provided
        if name is None:
            name = func.__name__
            
        # Use docstring if description not explicitly provided
        if description is None:
            description = func.__doc__ or ""
            
        # =====================================================================
        # SIGNATURE INTROSPECTION
        # =====================================================================
        # Inspect the function signature to extract parameter information.
        # This allows automatic JSON schema generation without requiring
        # explicit schema definitions for each tool.
        
        sig = inspect.signature(func)
        
        # =====================================================================
        # DESIGN NOTES ON PYDANTIC INTEGRATION
        # =====================================================================
        # There are two approaches for handling tool parameters:
        #
        # Method 1: Signature Inspection (Current Implementation)
        #   - Inspect Python type hints directly
        #   - Simple, works with any function
        #   - Limited type validation at runtime
        #
        # Method 2: Pydantic Models (Future Enhancement)
        #   - Define a Pydantic model for each tool's arguments
        #   - Rich validation with descriptive errors
        #   - More complex to set up
        #
        # For ABI compatibility with LLMs, we generate JSON Schema from
        # the signature, which works with both approaches.
        
        # Initialize the JSON Schema structure
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # =====================================================================
        # PARAMETER PROCESSING
        # =====================================================================
        # Iterate through each parameter in the function signature and
        # build the corresponding JSON Schema property.
        
        for param_name, param in sig.parameters.items():
            # Map Python types to JSON Schema types
            param_type = "string"  # Default to string for unknown types
            
            if param.annotation == int:
                param_type = "integer"
            elif param.annotation == float:
                param_type = "number"
            elif param.annotation == bool:
                param_type = "boolean"
            elif param.annotation == list:
                param_type = "array"
            elif param.annotation == dict:
                param_type = "object"
            # Note: str and untyped parameters default to "string"
                
            # Add the parameter to the schema
            parameters["properties"][param_name] = {
                "type": param_type,
                # TODO: Could parse docstring for parameter descriptions
                "description": f"Parameter {param_name}"
            }
            
            # Mark as required if no default value
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(param_name)
        
        # =====================================================================
        # REGISTRATION
        # =====================================================================
        # Store the function and its definition
        
        self.tools[name] = func
        self.tool_definitions.append(create_tool_definition(name, description, parameters))

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all registered tools with their schemas.
        
        This method is called by the orchestrator to provide the LLM
        with information about available tools.
        
        Returns:
            List of tool definition dictionaries, each containing:
            - name: Tool identifier
            - description: Human-readable description
            - inputSchema: JSON Schema for arguments
        
        Example:
            >>> tools = server.list_tools()
            >>> for tool in tools:
            ...     print(f"{tool['name']}: {tool['description'][:50]}")
        """
        return self.tool_definitions

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """
        Execute a tool by name with the given arguments.
        
        This method handles both synchronous and asynchronous tools,
        automatically detecting and handling each appropriately.
        
        Args:
            name: Name of the tool to execute
            arguments: Dictionary of arguments to pass to the tool
        
        Returns:
            CallToolResult: A result object containing:
                - content: List with a single {"type": "text", "text": str} entry
                - isError: Boolean indicating if an error occurred
        
        Error Handling:
            - Unknown tool name: Returns error result, does not raise
            - Tool execution error: Catches exception, returns error result
        
        Example:
            >>> # Successful call
            >>> result = await server.call_tool("search_flights", {
            ...     "origin": "NYC",
            ...     "destination": "LAX",
            ...     "date": "2024-03-15"
            ... })
            >>> print(result.isError)
            False
            >>> print(result.content[0]["text"])
            "[{...flight data...}]"
            >>> 
            >>> # Error case
            >>> result = await server.call_tool("unknown_tool", {})
            >>> print(result.isError)
            True
            >>> print(result.content[0]["text"])
            "Tool not found: unknown_tool"
        """
        # Check if the tool exists
        if name not in self.tools:
            return CallToolResult(
                content=[{"type": "text", "text": f"Tool not found: {name}"}],
                isError=True
            )
            
        try:
            func = self.tools[name]
            
            # Check if the function is async and handle appropriately
            if inspect.iscoroutinefunction(func):
                # Async function: await it
                result = await func(**arguments)
            else:
                # Synchronous function: call directly
                # Note: This blocks the event loop; consider asyncio.to_thread()
                # for CPU-bound sync functions in production
                result = func(**arguments)
                
            # Wrap the result in the standard MCP format
            return CallToolResult(
                content=[{"type": "text", "text": str(result)}],
                isError=False
            )
            
        except Exception as e:
            # Catch any exception during tool execution
            # and return it as an error result
            return CallToolResult(
                content=[{"type": "text", "text": f"Error executing tool {name}: {str(e)}"}],
                isError=True
            )
