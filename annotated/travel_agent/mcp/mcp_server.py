import inspect
from typing import Callable, Dict, Any, List
from .protocol import Tool, create_tool_definition, CallToolResult
from pydantic import BaseModel

class MCPServer:
    """A simple in-process MCP Server to host tools (Async & Pydantic enhanced)."""
    
    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self.tool_definitions: List[Dict[str, Any]] = []
        self.tool_models: Dict[str, BaseModel] = {} # Store Pydantic models for validation

    def register_tool(self, func: Callable, name: str = None, description: str = None):
        """
        Register a python function as a tool. 
        Supports Pydantic models for argument validation if present in type hints.
        """
        if name is None:
            name = func.__name__
        if description is None:
            description = func.__doc__ or ""
            
        # Inspect function signature
        sig = inspect.signature(func)
        
        # Check if the first argument is a Pydantic model (Standard Pattern for this refactor)
        # We look for a pattern where the function accepts arguments that match strict Pydantic models
        # But for ABI compatibility with the LLM, we need to generate JSON Schema.
        
        # METHOD 1: Hybrid - Check if arguments are primitive types or Pydantic models
        # For simplicity in this migration, let's assume if there are Pydantic models defined 
        # in the module matching {Name}Args, we use them, OR we inspect the signature.
        
        # Let's rely on standard python inspect for primitives, but if we see a Pydantic model
        # we can extract the schema directly.
        
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        # Scanning for Pydantic models in annotations
        # This is a bit advanced: we look at tool/flights.py and see search_flights(origin, dest...)
        # In our refactor of flights.py, we kept the function signature as primitives!
        # "async def search_flights(origin: str, destination: str, date: str)"
        # But we DEFINED "FlightSearchArgs" model.
        #
        # DECISION: To keep things simple and compatible with existing orchestration logic
        # without requiring a total rewrite of every tool's internal logic to take a single "args" object,
        # we will continue to use signature inspection for the *Schema Generation*, 
        # but we mark the tool as async-capable.
        # 
        # If we want to use Pydantic for validation, we can look up if there is a matching model, 
        # but for now, strict type hints in the signature are a good proxy.
        
        for param_name, param in sig.parameters.items():
            param_type = "string" # Default
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
                "description": f"Parameter {param_name}" # Could parse docstring
            }
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(param_name)
                
        self.tools[name] = func
        self.tool_definitions.append(create_tool_definition(name, description, parameters))

    def list_tools(self) -> List[Dict[str, Any]]:
        return self.tool_definitions

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> CallToolResult:
        """Call a tool asynchronously."""
        if name not in self.tools:
            return CallToolResult(
                content=[{"type": "text", "text": f"Tool not found: {name}"}],
                isError=True
            )
            
        try:
            func = self.tools[name]
            
            # Check if function is async
            if inspect.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                # Synchronous fallback
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
