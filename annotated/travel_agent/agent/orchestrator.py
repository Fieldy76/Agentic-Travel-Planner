from typing import List, Dict, Any  # Import typing utilities
import json  # Import json module
from .llm import LLMProvider  # Import LLMProvider class
from ..mcp.server import MCPServer  # Import MCPServer class

class AgentOrchestrator:  # Define AgentOrchestrator class
    def __init__(self, llm: LLMProvider, server: MCPServer):  # Constructor
        self.llm = llm  # Store LLM provider
        self.server = server  # Store MCP server
        self.messages: List[Dict[str, Any]] = []  # Initialize message history
        self.system_prompt = """You are a helpful travel assistant. 
        You have access to tools to search flights, book flights, rent cars, check weather, and process payments.
        
        When a user asks for a travel plan:
        1. Search for options (flights, cars, weather).
        2. Present options to the user.
        3. If the user confirms, proceed to booking and payment.
        
        Always check the weather before finalizing a plan.
        """  # Define system prompt

    def run(self, user_input: str):  # Define run method
        """Run one turn of the agent loop."""  # Docstring
        self.messages.append({"role": "user", "content": user_input})  # Add user input to history
        
        # Main Loop
        while True:  # Start agent loop
            # 1. Get available tools
            tools = self.server.list_tools()  # List available tools from server
            
            # 2. Call LLM
            print("Thinking...")  # Print status
            response = self.llm.call_tool(self.messages, tools)  # Call LLM with history and tools
            
            content = response.get("content")  # Get content from response
            tool_calls = response.get("tool_calls")  # Get tool calls from response
            
            if content:  # Check if there is content
                print(f"Agent: {content}")  # Print agent response
                self.messages.append({"role": "assistant", "content": content})  # Add assistant response to history
                
            if not tool_calls:  # Check if there are no tool calls
                # No more tools to call, we are done with this turn
                break  # Exit loop
                
            # 3. Execute Tools
            for tool_call in tool_calls:  # Iterate through tool calls
                tool_name = tool_call["name"]  # Get tool name
                tool_args = tool_call["arguments"]  # Get tool arguments
                tool_id = tool_call["id"]  # Get tool ID
                
                print(f"Calling Tool: {tool_name} with {tool_args}")  # Print tool call info
                
                result = self.server.call_tool(tool_name, tool_args)  # Execute tool on server
                
                result_text = result.content[0]["text"]  # Get result text
                print(f"Tool Result: {result_text}")  # Print result
                
                # Append standard tool result message
                self.messages.append({  # Add tool result to history
                    "role": "tool",  # Set role to tool
                    "tool_call_id": tool_id,  # Set tool call ID
                    "name": tool_name,  # Set tool name
                    "content": result_text  # Set content
                })
