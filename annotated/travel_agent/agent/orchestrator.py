from typing import List, Dict, Any, Optional
import json
import logging
import time
from .llm import LLMProvider
from ..mcp.mcp_server import MCPServer
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
        self.system_prompt = """You are a helpful travel assistant. Guide users through booking trips step-by-step.

CRITICAL DATE HANDLING:
- All tools require dates in YYYY-MM-DD format
- Convert relative dates ("tomorrow", "next week") to YYYY-MM-DD before calling tools
- Current date will be provided in context below

WORKFLOW RULES:

1. FLIGHT SEARCH & SELECTION:
   - Ask if one-way or round-trip if not specified
   - Search flights and include weather forecast
   - Present options clearly with prices and times

2. ROUND TRIP BOOKING:
   When user selects an outbound flight:
   - Acknowledge their choice
   - IMMEDIATELY search for return flights in the same response
   - Do NOT wait for user to prompt - proceed automatically
   - After return flight selected, ask for passenger details
   - Book both flights together
   
3. USER INPUT:
   - Always acknowledge when user provides information
   - When receiving passenger details, confirm them and proceed to booking immediately
   - Never wait silently - always respond

4. BOOKING & PAYMENT:
   - Accept flight selection in any format (code, number, "first one", etc.)
   - After booking flight(s), AUTOMATICALLY process payment
   - Calculate total from flight prices
   - Confirm booking AND payment together
   
5. RESPONSES:
   - Be concise and helpful
   - Always confirm completed actions
   - Never ask "so?" - proceed automatically

Be brief and efficient."""

    def run_generator(self, user_input: str, request_id: str = "default"):
        """Run one turn of the agent loop, yielding events."""
        logger.info(f"Starting agent turn", extra={"request_id": request_id})
        
        # Add user message to memory
        self.memory.add_message({"role": "user", "content": user_input})
        
        # Main Loop - Increased to 10 to handle multi-step flows like booking
        max_turns = 10
        current_turn = 0
        
        while current_turn < max_turns:
            current_turn += 1
            
            # 1. Get available tools
            tools = self.server.list_tools()
            
            # 2. Call LLM with current date/time context
            logger.info("Calling LLM", extra={"request_id": request_id, "turn": current_turn})
            
            # Inject current date/time into system prompt
            from datetime import datetime
            now = datetime.now()
            current_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
            current_date = now.strftime("%Y-%m-%d")
            
            enhanced_system_prompt = f"""{self.system_prompt}

IMPORTANT CONTEXT:
- Current date and time: {current_datetime}
- Today's date: {current_date}
- When users ask about "today", "now", or relative dates, use this information.
"""
            
            # Construct full history with enhanced system prompt
            messages = [{"role": "system", "content": enhanced_system_prompt}] + self.memory.get_messages()
            
            try:
                response = self.llm.call_tool(messages, tools)
            except Exception as e:
                logger.error(f"LLM call failed: {e}", extra={"request_id": request_id})
                yield {"type": "error", "content": str(e)}
                break
            
            content = response.get("content")
            tool_calls = response.get("tool_calls")
            
            # Add assistant message to memory if there is content OR tool calls
            if content or tool_calls:
                # Log content if present
                if content:
                    logger.info(f"Agent response: {content[:50]}...", extra={"request_id": request_id})
                
                self.memory.add_message({
                    "role": "assistant", 
                    "content": content,
                    "tool_calls": tool_calls
                })
                
                # Only yield message event if there is actual text content
                if content:
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
