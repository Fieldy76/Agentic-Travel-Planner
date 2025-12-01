from typing import List, Dict, Any
import json
from .llm import LLMProvider
from ..mcp.server import MCPServer

class AgentOrchestrator:
    def __init__(self, llm: LLMProvider, server: MCPServer):
        self.llm = llm
        self.server = server
        self.messages: List[Dict[str, Any]] = []
        self.system_prompt = """You are a helpful travel assistant. 
        You have access to tools to search flights, book flights, rent cars, check weather, and process payments.
        
        When a user asks for a travel plan:
        1. Search for options (flights, cars, weather).
        2. Present options to the user.
        3. If the user confirms, proceed to booking and payment.
        
        Always check the weather before finalizing a plan.
        """

    def run(self, user_input: str):
        """Run one turn of the agent loop."""
        self.messages.append({"role": "user", "content": user_input})
        
        # Main Loop
        while True:
            # 1. Get available tools
            tools = self.server.list_tools()
            
            # 2. Call LLM
            print("Thinking...")
            response = self.llm.call_tool(self.messages, tools)
            
            content = response.get("content")
            tool_calls = response.get("tool_calls")
            
            if content:
                print(f"Agent: {content}")
                self.messages.append({"role": "assistant", "content": content})
                
            if not tool_calls:
                # No more tools to call, we are done with this turn
                break
                
            # 3. Execute Tools
            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["arguments"]
                tool_id = tool_call["id"]
                
                print(f"Calling Tool: {tool_name} with {tool_args}")
                
                result = self.server.call_tool(tool_name, tool_args)
                
                result_text = result.content[0]["text"]
                print(f"Tool Result: {result_text}")
                
                # Append standard tool result message
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": result_text
                })
