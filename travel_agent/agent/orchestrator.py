from typing import List, Dict, Any, Optional
import json
import logging
import time
from .llm import LLMProvider
from ..mcp.server import MCPServer
from .memory import AgentMemory, InMemoryMemory
from ..config import setup_logging

# Ensure logging is configured
setup_logging()
logger = logging.getLogger(__name__)

class AgentOrchestrator:
    def __init__(self, llm: LLMProvider, server: MCPServer, memory: Optional[AgentMemory] = None):
        self.llm = llm
        self.server = server
        self.memory = memory or InMemoryMemory()
        self.system_prompt = """You are a helpful travel assistant. 
        You have access to tools to search flights, book flights, rent cars, check weather, and process payments.
        
        When a user asks for a travel plan:
        1. Search for options (flights, cars, weather).
        2. Present options to the user.
        3. If the user confirms, proceed to booking and payment.
        
        Always check the weather before finalizing a plan.
        """

    def run_generator(self, user_input: str, request_id: str = "default"):
        """Run one turn of the agent loop, yielding events."""
        logger.info(f"Starting agent turn", extra={"request_id": request_id})
        
        # Add user message to memory
        self.memory.add_message({"role": "user", "content": user_input})
        
        # Main Loop
        max_turns = 10
        current_turn = 0
        
        while current_turn < max_turns:
            current_turn += 1
            
            # 1. Get available tools
            tools = self.server.list_tools()
            
            # 2. Call LLM
            logger.info("Calling LLM", extra={"request_id": request_id, "turn": current_turn})
            
            # Construct full history with system prompt
            messages = [{"role": "system", "content": self.system_prompt}] + self.memory.get_messages()
            
            try:
                response = self.llm.call_tool(messages, tools)
            except Exception as e:
                logger.error(f"LLM call failed: {e}", extra={"request_id": request_id})
                yield {"type": "error", "content": str(e)}
                break
            
            content = response.get("content")
            tool_calls = response.get("tool_calls")
            
            if content:
                logger.info(f"Agent response: {content[:50]}...", extra={"request_id": request_id})
                self.memory.add_message({"role": "assistant", "content": content})
                yield {"type": "message", "content": content}
                
            if not tool_calls:
                # No more tools to call, we are done with this turn
                logger.info("No tool calls, turn complete", extra={"request_id": request_id})
                break
                
            # 3. Execute Tools
            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["arguments"]
                tool_id = tool_call["id"]
                
                logger.info(f"Executing tool: {tool_name}", extra={"request_id": request_id, "tool_args": tool_args})
                yield {"type": "tool_call", "name": tool_name, "arguments": tool_args}
                
                # Retry logic
                max_retries = 3
                result_text = ""
                is_error = False
                
                for attempt in range(max_retries):
                    try:
                        result = self.server.call_tool(tool_name, tool_args)
                        result_text = result.content[0]["text"]
                        is_error = result.isError
                        break # Success
                    except Exception as e:
                        logger.warning(f"Tool execution failed (attempt {attempt+1}/{max_retries}): {e}", extra={"request_id": request_id})
                        if attempt == max_retries - 1:
                            result_text = f"Error executing tool {tool_name}: {str(e)}"
                            is_error = True
                        else:
                            time.sleep(1 * (attempt + 1)) # Exponential backoff
                
                logger.info(f"Tool result: {result_text[:50]}...", extra={"request_id": request_id, "is_error": is_error})
                yield {"type": "tool_result", "name": tool_name, "content": result_text, "is_error": is_error}
                
                # Append standard tool result message
                self.memory.add_message({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": result_text
                })

    def run(self, user_input: str, request_id: str = "default"):
        """Run one turn of the agent loop (synchronous wrapper for CLI)."""
        for event in self.run_generator(user_input, request_id):
            if event["type"] == "message":
                print(f"Agent: {event['content']}")
            elif event["type"] == "tool_call":
                print(f"Calling Tool: {event['name']} with {event['arguments']}")
            elif event["type"] == "tool_result":
                print(f"Tool Result: {event['content']}")
            elif event["type"] == "error":
                print(f"Error: {event['content']}")
