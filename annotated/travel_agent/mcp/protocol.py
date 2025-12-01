from typing import Any, Dict, List, Optional, Union  # Import typing utilities
from dataclasses import dataclass  # Import dataclass decorator
import json  # Import json module

# JSON-RPC 2.0 Constants
JSONRPC_VERSION = "2.0"  # Define JSON-RPC version constant

@dataclass  # Decorator to create a data class
class JsonRpcRequest:  # Define JsonRpcRequest class
    method: str  # Method name
    params: Optional[Dict[str, Any]] = None  # Optional parameters
    id: Optional[Union[str, int]] = None  # Optional ID
    jsonrpc: str = JSONRPC_VERSION  # JSON-RPC version

    def to_dict(self) -> Dict[str, Any]:  # Method to convert to dictionary
        data = {  # Initialize dictionary
            "jsonrpc": self.jsonrpc,  # Set version
            "method": self.method,  # Set method
        }
        if self.params is not None:  # Check if params exist
            data["params"] = self.params  # Add params
        if self.id is not None:  # Check if ID exists
            data["id"] = self.id  # Add ID
        return data  # Return dictionary

@dataclass  # Decorator to create a data class
class JsonRpcResponse:  # Define JsonRpcResponse class
    result: Any = None  # Result data
    error: Optional[Dict[str, Any]] = None  # Error data
    id: Optional[Union[str, int]] = None  # Request ID
    jsonrpc: str = JSONRPC_VERSION  # JSON-RPC version

    def to_dict(self) -> Dict[str, Any]:  # Method to convert to dictionary
        data = {  # Initialize dictionary
            "jsonrpc": self.jsonrpc,  # Set version
            "id": self.id  # Set ID
        }
        if self.error:  # Check if error exists
            data["error"] = self.error  # Add error
        else:  # If no error
            data["result"] = self.result  # Add result
        return data  # Return dictionary

# MCP Specific Structures

@dataclass  # Decorator to create a data class
class Tool:  # Define Tool class
    name: str  # Tool name
    description: str  # Tool description
    inputSchema: Dict[str, Any]  # Input schema

@dataclass  # Decorator to create a data class
class CallToolRequest:  # Define CallToolRequest class
    name: str  # Tool name
    arguments: Dict[str, Any]  # Tool arguments

@dataclass  # Decorator to create a data class
class CallToolResult:  # Define CallToolResult class
    content: List[Dict[str, Any]]  # Result content
    isError: bool = False  # Error flag

    def to_dict(self) -> Dict[str, Any]:  # Method to convert to dictionary
        return {  # Return dictionary
            "content": self.content,  # Set content
            "isError": self.isError  # Set error flag
        }

# Helper to create a tool definition
def create_tool_definition(name: str, description: str, parameters: Dict[str, Any]) -> Dict[str, Any]:  # Helper function
    return {  # Return dictionary
        "name": name,  # Set name
        "description": description,  # Set description
        "inputSchema": parameters  # Set parameters
    }
