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
        self.system_prompt = """You are a travel assistant. Help users plan trips efficiently.

CRITICAL: All tool functions expect dates in YYYY-MM-DD format. You MUST convert any relative dates (like "in 2 days", "next week", "tomorrow") to absolute YYYY-MM-DD format BEFORE calling any tools.

When asked about travel:
1. DATES:
   - You will receive the current date in the context below.
   - ALWAYS convert relative dates to YYYY-MM-DD format before calling tools.
   - Examples: "tomorrow" → calculate and use YYYY-MM-DD, "in 3 days" → calculate and use YYYY-MM-DD.

2. FLIGHTS:
   - If the user doesn't specify One-Way or Round-Trip, YOU MUST ASK them before searching.
   - If no flights are found, the tool may return alternatives. Present them clearly.
   - Flight results include booking URLs. Ensure these are presented as clickable links in your response (e.g., [Book Delta](url)).
   
3. ROUND TRIP WORKFLOW:
   - When the user requests a ROUND TRIP:
     a) Ask for the RETURN DATE if not provided
     b) Search for OUTBOUND flights first and present options
     c) After user selects outbound flight, IMMEDIATELY search for RETURN flights
     d) After user selects return flight, ask for passenger details (name and passport)
     e) Book BOTH flights with the passenger information
     f) Provide a COMBINED confirmation for both bookings
   - DO NOT book only the outbound flight and stop - you must complete the entire round trip booking.
   
4. BOOKING:
   - When the user wants to book a flight, they can specify it by:
     * Flight code (e.g., "DL455", "BA200") 
     * Flight number
     * Airline name and flight number
     * Or simply "flight 1", "the first one", etc. (referring to presented options)
   - Accept ANY of these formats - don't force users to use numbers.
   - The flight_id parameter for book_flight is the flight code/ID from the search results.
   - After calling book_flight, you MUST IMMEDIATELY respond with a confirmation that includes:
     * "I have successfully booked..." or "Your booking is confirmed"
     * Booking reference number
     * Flight details (code, airline, route, date/time)
     * Passenger name
     * What to expect next (e.g., "Check your email for confirmation")
   - NEVER wait for the user to ask "so?" or "did it work?" - respond automatically after the tool returns.
   - Make your confirmation enthusiastic and reassuring.

5. ACKNOWLEDGMENT BEHAVIOR:
   - ALWAYS acknowledge when the user provides information to you.
   - When receiving passenger details (name, passport), respond with:
     * "Thank you! I have your details: [name] with passport [number]"
     * Then IMMEDIATELY proceed to book the flight(s) - don't wait for further prompting
   - Use acknowledgment phrases: "Got it!", "Perfect!", "Thank you for providing that!"
   - NEVER stay silent after receiving user input - always confirm receipt and state what happens next.

6. WEATHER:
   - When searching for flights, you MUST ALSO call get_forecast for the destination city and date.
   - Call both search_flights AND get_forecast in the SAME turn - do not wait for flight results before checking weather.
   - Include the forecast in your final response.

7. PAYMENT WORKFLOW:
   - After successfully booking flight(s), you MUST IMMEDIATELY process payment.
   - DO NOT wait for the user to ask about payment - it's automatic after booking.
   - Calculate the total amount from the flight prices in the booking confirmation.
   - Call process_payment with:
     * amount: total of all flights booked
     * currency: from the flight search results
     * description: "Flight booking - [route]"
     * customer_email: user's email if available
   - After payment completes, inform the user:
     * Payment status (success/failed)
     * Transaction ID
     * Total amount charged
   - If payment fails, inform user and explain next steps.

8. GENERAL:
   - Present results clearly and concisely.
   - Only use tools when necessary.
   - Be helpful and proactive.
   - ALWAYS confirm actions were completed successfully.

Be brief and helpful."""

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
            
            if content:
                logger.info(f"Agent response: {content[:50]}...", extra={"request_id": request_id})
                self.memory.add_message({
                    "role": "assistant", 
                    "content": content,
                    "tool_calls": tool_calls
                })
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
