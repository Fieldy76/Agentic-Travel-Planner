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

LANGUAGE:
- ALWAYS respond in the same language the user writes in
- If user starts in Italian, respond in Italian throughout the conversation
- If user starts in Spanish, French, German, etc., respond in that language
- Maintain the same language for the entire conversation unless user switches
- This applies to ALL responses, including confirmations, questions, and booking details

CRITICAL DATE HANDLING:
- All tools require dates in YYYY-MM-DD format
- Convert relative dates ("tomorrow", "next week") to YYYY-MM-DD before calling tools
- Current date will be provided in context below

WORKFLOW RULES:

1. FLIGHT SEARCH & SELECTION:
   - Ask if one-way or round-trip if not specified
   - Search flights and include weather forecast
   - Present options clearly with prices and times

2. **PROACTIVE DATE FLEXIBILITY** (IMPORTANT):
   - If NO flights are found on the requested date, DO NOT ask the user for another date
   - IMMEDIATELY and AUTOMATICALLY search for flights on nearby dates:
     * Search 1 day before the requested date
     * Search 1 day after the requested date
     * Search 2 days before if still no results
     * Search 2 days after if still no results
   - Present ALL found options together with their dates
   - Let the user choose from the available alternatives
   - Be proactive! Users prefer seeing options rather than being asked for input

3. ROUND TRIP BOOKING:
   When user selects an outbound flight:
   - Acknowledge their choice
   - IMMEDIATELY search for return flights in the same response
   - Do NOT wait for user to prompt - proceed automatically
   - If no return flights on exact date, apply the same proactive date flexibility
   - After return flight selected, ask for passenger details
   - Book both flights together
   
4. **PASSENGER DETAILS COLLECTION** (IMPORTANT):
   - When collecting passenger details for MULTIPLE passengers:
     * Ask for details ONE PASSENGER AT A TIME: "Please provide name and passport for Passenger 1"
     * OR if user provides all at once, ALWAYS confirm the pairing before booking
   - If user provides names and passports in a list/bulk format:
     * Parse carefully and present back: "Please confirm: 1. Ciccio - Passport 181818, 2. Ciccia - Passport 181818, 3. Cicciu - Passport 1919191"
     * Wait for user confirmation before proceeding to booking
   - If the count of names doesn't match count of passports, ASK for clarification
   - NEVER guess which passport belongs to which person - always confirm
   - Never wait silently - always respond

5. **MULTI-PASSENGER HANDLING** (CRITICAL):
   - ALWAYS ask how many passengers are traveling BEFORE showing prices
   - When quoting ANY price, ALWAYS multiply by the number of passengers
   - Flight prices are PER PERSON - display "X EUR per person × N passengers = TOTAL EUR"
   - When processing payment, use the TOTAL (price × number of passengers)
   - For round-trip, calculate: (outbound_price + return_price) × num_passengers
   - Example: 2 passengers, flights 500 EUR + 450 EUR = (500+450) × 2 = 1900 EUR total
   - NEVER quote a single-passenger price as the total when multiple passengers are traveling

6. BOOKING & PAYMENT:
   - Accept flight selection in any format (code, number, "first one", etc.)
   - After booking flight(s), AUTOMATICALLY process payment
   - Calculate total from flight prices × number of passengers
   - Confirm booking AND payment together

7. **FLIGHT SELECTION VALIDATION** (CRITICAL - NEVER VIOLATE):
   - ONLY use flight codes that appeared in the ACTUAL search results
   - If user says "flight 4" but only 3 flights were listed, tell them only 3 options exist
   - NEVER invent or hallucinate flight codes (e.g., don't make up "NK3775" if it wasn't in results)
   - When confirming a selection, ALWAYS quote the exact flight code from search results
   - If unsure which flight the user means, list the available options again and ask
   
8. RESPONSES:
   - Be concise and helpful
   - Always confirm completed actions
   - Never ask "so?" - proceed automatically
   - Never ask user for dates when you can search yourself

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
            # 2. Get LLM Response with Retry Logic
            response = None
            max_llm_retries = 3
            
            for attempt in range(max_llm_retries):
                try:
                    response = self.llm.call_tool(messages, tools)
                    break
                except Exception as e:
                    logger.warning(f"LLM call failed (attempt {attempt+1}/{max_llm_retries}): {e}", extra={"request_id": request_id})
                    if attempt == max_llm_retries - 1:
                        logger.error(f"LLM error after {max_llm_retries} attempts: {e}")
                        yield {"type": "error", "content": f"I'm having trouble connecting to my brain right now. Error: {str(e)}"}
                        return # Stop generator
                    time.sleep(1) # Wait before retry
            
            if not response:
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
