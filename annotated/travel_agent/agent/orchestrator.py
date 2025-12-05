from typing import List, Dict, Any, Optional
import json
import logging
import asyncio
from datetime import datetime
from .llm import LLMProvider
from ..mcp.mcp_server import MCPServer
from .memory import AgentMemory, InMemoryMemory
from ..config import setup_logging

# Ensure logging is configured when this module is imported
setup_logging()
logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """
    The Agent Orchestrator manages the core loop of the agent's cognition:
    1. Receive user input
    2. Consult LLM with context and tools
    3. Execute tools if requested
    4. Feed results back to LLM
    5. Repeat until a final text response is generated
    """
    def __init__(self, llm: LLMProvider, server: MCPServer, memory: Optional[AgentMemory] = None):
        self.llm = llm
        self.server = server
        self.memory = memory or InMemoryMemory()
        
        # The System Prompt defines the Agent's personality and core rules.
        # It's crucial for instructing the LLM on how to behave, especially for
        # complex tasks like handling dates, multiple languages, and booking workflows.
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

    async def run_generator(self, user_input: str, request_id: str = "default"):
        """
        Run one turn of the agent loop, yielding events (Async Generator).
        This method is designed to be streamed to the client (Server-Sent Events).
        """
        logger.info(f"Starting agent turn", extra={"request_id": request_id})
        
        # Add the new user message to conversation memory
        self.memory.add_message({"role": "user", "content": user_input})
        
        # Limit the number of turns (thought/action cycles) to prevent infinite loops.
        # We increased this to 10 to support complex multi-step flows like booking + payment.
        max_turns = 10
        current_turn = 0
        
        while current_turn < max_turns:
            current_turn += 1
            
            # 1. Get available tools from the MCP Server
            # The agent dynamically sees what tools are available (e.g., search_flights, rent_car)
            tools = self.server.list_tools()
            
            # 2. Prepare the context for the LLM
            logger.info("Calling LLM", extra={"request_id": request_id, "turn": current_turn})
            
            # Inject dynamic time context into the system prompt.
            # This is critical for the LLM to understand what "tomorrow" or "Jan 30" implies relative to today.
            now = datetime.now()
            current_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
            current_date = now.strftime("%Y-%m-%d")
            
            # Enhanced System Prompt with specific date inference rules to fix recent issues with year nagging.
            enhanced_system_prompt = f"""{self.system_prompt}

CRITICAL DATE CONTEXT:
- TODAY'S DATE: {current_date} ({now.strftime('%A')})
- If the user provides a date without a year (e.g., "Jan 30", "8 feb"), you MUST assume the NEXT occurrence of that date relative to today.
  * Example: If today is 2025-12-05 and user says "Jan 30", interpret as 2026-01-30.
  * Example: If today is 2025-01-01 and user says "Mar 5", interpret as 2025-03-05.
- Handle month abbreviations and typos intelligently (e.g., "fab" -> "feb", "sept" -> "sep").
- DO NOT ask for the year if it can be inferred from the rules above.
"""
            
            # Construct full message history for the LLM call
            messages = [{"role": "system", "content": enhanced_system_prompt}] + self.memory.get_messages()
            
            # 3. Call The LLM (with Retry Logic)
            # We wrap the LLM call in a retry loop to handle transient API errors or rate limits.
            response = None
            max_llm_retries = 3
            
            for attempt in range(max_llm_retries):
                try:
                    response = await self.llm.call_tool(messages, tools)
                    break
                except Exception as e:
                    logger.warning(f"LLM call failed (attempt {attempt+1}/{max_llm_retries}): {e}", extra={"request_id": request_id})
                    if attempt == max_llm_retries - 1:
                        logger.error(f"LLM error after {max_llm_retries} attempts: {e}")
                        # Yield an error event if all retries fail
                        yield {"type": "error", "content": f"I'm having trouble connecting to my brain right now. Error: {str(e)}"}
                        return # Stop generator
                    await asyncio.sleep(1) # Wait before retry (non-blocking sleep)
            
            if not response:
                break

            content = response.get("content")
            tool_calls = response.get("tool_calls")
            
            # 4. Handle LLM Response
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
                
                # Only yield message event if there is actual text content to display to the user
                if content:
                    yield {"type": "message", "content": content}
                
            if not tool_calls:
                # No more tools to call, we are done with this turn
                logger.info("No tool calls, turn complete", extra={"request_id": request_id})
                break
                
            # 5. Execute Tools (if any)
            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["arguments"]
                tool_id = tool_call["id"]
                
                logger.info(f"Executing tool: {tool_name}", extra={"request_id": request_id, "tool_args": tool_args})
                # Yield a tool_call event so the UI can show "Checking flights..." capabilities
                yield {"type": "tool_call", "name": tool_name, "arguments": tool_args}
                
                # Retry logic for Tool Execution
                max_retries = 3
                result_text = ""
                is_error = False
                
                for attempt in range(max_retries):
                    try:
                        result = await self.server.call_tool(tool_name, tool_args)
                        result_text = result.content[0]["text"]
                        is_error = result.isError
                        break # Success
                    except Exception as e:
                        logger.warning(f"Tool execution failed (attempt {attempt+1}/{max_retries}): {e}", extra={"request_id": request_id})
                        if attempt == max_retries - 1:
                            result_text = f"Error executing tool {tool_name}: {str(e)}"
                            is_error = True
                        else:
                            await asyncio.sleep(1 * (attempt + 1)) # Exponential backoff
                
                logger.info(f"Tool result: {result_text[:50]}...", extra={"request_id": request_id, "is_error": is_error})
                yield {"type": "tool_result", "name": tool_name, "content": result_text, "is_error": is_error}
                
                # Append the tool result to memory so the LLM knows what happened
                self.memory.add_message({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": result_text
                })

    async def run(self, user_input: str, request_id: str = "default"):
        """
        Run one turn of the agent loop (async wrapper for CLI/Testing).
        This consumes the generator and prints events to stdout.
        """
        async for event in self.run_generator(user_input, request_id):
            if event["type"] == "message":
                print(f"Agent: {event['content']}")
            elif event["type"] == "tool_call":
                print(f"Calling Tool: {event['name']} with {event['arguments']}")
            elif event["type"] == "tool_result":
                print(f"Tool Result: {event['content']}")
            elif event["type"] == "error":
                print(f"Error: {event['content']}")
