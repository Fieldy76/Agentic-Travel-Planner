import inspect  # Import inspect module for introspection
from typing import Callable, Dict, Any, List  # Import typing utilities
from .protocol import Tool, create_tool_definition, CallToolResult  # Import protocol definitions

class MCPServer:  # Define MCPServer class
    """A simple in-process MCP Server to host tools."""  # Docstring
    
    def __init__(self):  # Constructor
        self.tools: Dict[str, Callable] = {}  # Initialize tools dictionary
        self.tool_definitions: List[Dict[str, Any]] = []  # Initialize tool definitions list

    def register_tool(self, func: Callable, name: str = None, description: str = None):  # Method to register a tool
        """Register a python function as a tool."""  # Docstring
        if name is None:  # Check if name is provided
            name = func.__name__  # Use function name if not provided
        if description is None:  # Check if description is provided
            description = func.__doc__ or ""  # Use function docstring if not provided
            
        # Inspect function signature to generate schema
        sig = inspect.signature(func)  # Get function signature
        parameters = {  # Initialize parameters dictionary
            "type": "object",  # Set type to object
            "properties": {},  # Initialize properties
            "required": []  # Initialize required list
        }
        
        for param_name, param in sig.parameters.items():  # Iterate through parameters
            param_type = "string" # Default to string
            if param.annotation == int:  # Check if int
                param_type = "integer"  # Set type to integer
            elif param.annotation == float:  # Check if float
                param_type = "number"  # Set type to number
            elif param.annotation == bool:  # Check if bool
                param_type = "boolean"  # Set type to boolean
            elif param.annotation == list:  # Check if list
                param_type = "array"  # Set type to array
            elif param.annotation == dict:  # Check if dict
                param_type = "object"  # Set type to object
                
            parameters["properties"][param_name] = {  # Add parameter property
                "type": param_type,  # Set type
                "description": f"Parameter {param_name}" # Could parse docstring for better desc
            }
            if param.default == inspect.Parameter.empty:  # Check if parameter is required
                parameters["required"].append(param_name)  # Add to required list
                
        self.tools[name] = func  # Add function to tools dictionary
        self.tool_definitions.append(create_tool_definition(name, description, parameters))  # Add definition to list

    def list_tools(self) -> List[Dict[str, Any]]:  # Method to list tools
        return self.tool_definitions  # Return tool definitions

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:  # Method to call a tool
        if name not in self.tools:  # Check if tool exists
            return CallToolResult(  # Return error result
                content=[{"type": "text", "text": f"Tool not found: {name}"}],  # Set error message
                isError=True  # Set error flag
            )
            
        try:  # Try block for execution
            func = self.tools[name]  # Get function
            result = func(**arguments)  # Execute function with arguments
            return CallToolResult(  # Return success result
                content=[{"type": "text", "text": str(result)}],  # Set result text
                isError=False  # Set error flag
            )
        except Exception as e:  # Catch exceptions
            return CallToolResult(  # Return error result
                content=[{"type": "text", "text": f"Error executing tool {name}: {str(e)}"}],  # Set error message
                isError=True  # Set error flag
            )
