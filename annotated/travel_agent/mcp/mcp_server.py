import inspect
from typing import Callable, Dict, Any, List
from .protocol import Tool, create_tool_definition, CallToolResult

class MCPServer:
    """A simple in-process MCP Server to host tools."""
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict[str, Any]] = []

    def register_tool(self, func: Callable, name: str = None, description: str = None):
        """Register a python function as a tool."""
        if name is None:
            name = func.__name__
        if description is None:
            description = func.__doc__ or ""
            
        # Inspect function signature to generate schema
        sig = inspect.signature(func)
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        for param_name, param in sig.parameters.items():
            param_type = "string" # Default to string
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
                
            parameters["properties"][param_name] = {
                "type": param_type,
                "description": f"Parameter {param_name}" # Could parse docstring for better desc
            }
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(param_name)
                
        self.tools[name] = func
        self.tool_definitions.append(create_tool_definition(name, description, parameters))

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.tool_definitions

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        if name not in self.tools:
            return CallToolResult(
                content=[{"type": "text", "text": f"Tool not found: {name}"}],
                isError=True
            )
            
        try:
            func = self.tools[name]
            result = func(**arguments)
            return CallToolResult(
                content=[{"type": "text", "text": str(result)}],
                isError=False
            )
        except Exception as e:
            return CallToolResult(
                content=[{"type": "text", "text": f"Error executing tool {name}: {str(e)}"}],
                isError=True
            )
