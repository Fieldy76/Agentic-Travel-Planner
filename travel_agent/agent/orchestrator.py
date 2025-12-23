from typing import List, Dict, Any, Optional
import json
import logging
import asyncio
from datetime import datetime
import io
import pypdf
import docx
from .llm import LLMProvider, LANGFUSE_ENABLED, langfuse_trace, langfuse_generation, langfuse_flush
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

LANGUAGE CONSISTENCY (HIGHEST PRIORITY):
- DETECT the user's language immediately.
- RESPOND in the EXACT SAME language.
- If the user writes in Italian, you MUST respond in Italian.
- If the user writes in German, you MUST respond in German.
- If the user writes in English, you MUST respond in English.
- NEVER switch languages unless explicitly asked.
- NEVER mix languages (e.g. English intro with Italian details).
- This applies to ALL output: tool results, questions, lists, confirmations.

CRITICAL DATE HANDLING:
- All tools require dates in YYYY-MM-DD format
- Convert relative dates ("tomorrow", "next week") to YYYY-MM-DD before calling tools
- Current date will be provided in context below

WORKFLOW RULES:
 
 GLOBAL FORMATTING RULE (APPLIES TO EVERYTHING):
 - STRICTLY FORBIDDEN: 
   1. Do NOT use bullet points for lists.
   2. Do NOT use Markdown BOLD or ITALICS syntax. NEVER output double asterisks.
 - MANDATORY: ALWAYS use Numbered Lists (1., 2., 3.) for ANY list of items, options, or questions.
 - EXAMPLE: 
   CORRECT (Plain text):
   1. Airline: Ryanair, Price: 50 EUR
   2. Date of Departure: When do you want to leave?
   
   WRONG:
   1. **Airline**: Ryanair
 - This applies to flight options, lists of missing info, passenger lists, everything.
 
 0. MANDATORY DATA CHECK (PERFORM THIS BEFORE ANYTHING ELSE):
    - ONE-WAY: Check for Origin, Destination, Departure Date, Passengers.
    - ROUND-TRIP: Check for Origin, Destination, DEPARTURE DATE, RETURN DATE, Passengers.
    - IF ANY IS MISSING: STOP and ask the user for the missing piece.
    - CRITICAL: A Return Date (e.g., "returning Jan 10") is NOT a Departure Date. You MUST ask "When do you want to leave?" if they only gave the return date.
    - NEVER assume the departure date is "today" unless the user explicitly says "today" or "now".
    - IF DEPARTURE DATE IS MISSING: You MUST ask "When would you like to depart?".
    - Do NOT call search_flights until you have the Departure Date.
    - FORMATTING MISSING INFO: When asking for missing info, use a numbered list for clarity. ALWAYS include "Date of Departure" if missing.
        Example:
        1. Date of Departure: When would you like to leave?
        2. Passengers: How many people are traveling?
 
 1. FLIGHT SEARCH & SELECTION:
   - Ask for the departure city (origin) if not specified. NEVER assume the origin.
   - CRITICAL: Origin and Destination MUST be different cities. NEVER search for "X to X".
     If you only have ONE city, ask: "Where will you be departing from?"
   - Ask for the departure date (when they want to leave) if not specified. DO NOT SKIP THIS.
   - Ask if one-way or round-trip if not specified
   - If round-trip is selected but NO return date is specified, ASK for the return date. DO NOT assume default dates.
   - Search flights and include weather forecast
   - Present options as a NUMBERED LIST (1., 2., 3.) so user can select by number.
   - For each option, include: Airline (Flight Num), Time, Price.

2. PROACTIVE DATE FLEXIBILITY (IMPORTANT):
   - If NO flights are found on the requested date, DO NOT ask the user for another date
   - IMMEDIATELY and AUTOMATICALLY search for flights on nearby dates:
     1. Search 1 day before the requested date
     2. Search 1 day after the requested date
     3. Search 2 days before if still no results
     4. Search 2 days after if still no results
   - Present ALL found options together with their dates (as a numbered list). Let the user choose from the available alternatives
   - Be proactive! Users prefer seeing options rather than being asked for input

3. ROUND TRIP BOOKING:
   When user selects an outbound flight:
   - Acknowledge their choice
   - If return date is KNOWN: IMMEDIATELY search for return flights in the same response
   - If return date is UNKNOWN: ASK for the return date. DO NOT assume same-day return.
   - Do NOT wait for user to prompt if date is known - proceed automatically
   - If no return flights on exact date, apply the same proactive date flexibility
   - After return flight selected, ask for passenger details
   - Book both flights together
   
4. PASSENGER DETAILS COLLECTION (IMPORTANT):
   - When collecting passenger details for MULTIPLE passengers:
     - Ask for details ONE PASSENGER AT A TIME: "Please provide name and passport for Passenger 1"
     - OR if user provides all at once, ALWAYS confirm the pairing before booking
   - If user provides names and passports in a list/bulk format:
     - Parse carefully and present back: "Please confirm: 1. Ciccio - Passport 181818, 2. Ciccia - Passport 181818, 3. Cicciu - Passport 1919191"
     - Wait for user confirmation before proceeding to booking
   - If the count of names doesn't match count of passports, ASK for clarification
   - NEVER guess which passport belongs to which person - always confirm
   - Never wait silently - always respond

5. MULTI-PASSENGER HANDLING (CRITICAL):
   - ALWAYS ask how many passengers are traveling BEFORE showing prices
   - When quoting ANY price, ALWAYS multiply by the number of passengers
   - Flight prices are PER PERSON - display "X EUR per person x N passengers = TOTAL EUR"
   - When processing payment, use the TOTAL (price x number of passengers)
   - For round-trip, calculate: (outbound_price + return_price) x num_passengers
   - Example: 2 passengers, flights 500 EUR + 450 EUR = (500+450) x 2 = 1900 EUR total
   - NEVER quote a single-passenger price as the total when multiple passengers are traveling

6. BOOKING & PAYMENT:
   - Accept flight selection in any format (code, number, "first one", etc.)
   - BEFORE processing payment, ASK for the customer's email address to send the booking confirmation
   - Pass the email to process_payment using the customer_email parameter
   - After booking flight(s), process payment with the provided email
   - Calculate total from flight prices x number of passengers
   - Confirm booking AND payment together, mentioning that confirmation was sent to their email

7. FLIGHT SELECTION VALIDATION (CRITICAL - NEVER VIOLATE):
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

    async def run_generator(self, user_input: str, file_data: Optional[bytes] = None, mime_type: Optional[str] = None, request_id: str = "default"):
        """Run one turn of the agent loop, yielding events (Async Generator)."""
        logger.info(f"Starting agent turn", extra={"request_id": request_id})
        
        # Create Langfuse trace for this agent turn
        trace = langfuse_trace(
            name="agent-turn",
            session_id=request_id,
            metadata={"user_input_preview": user_input[:100]}
        )
        
        # New Logic: Server-side text extraction for documents
        extracted_text = ""
        is_document = False
        
        if file_data and mime_type:
            try:
                if mime_type == "application/pdf":
                    is_document = True
                    pdf_reader = pypdf.PdfReader(io.BytesIO(file_data))
                    for page in pdf_reader.pages:
                        extracted_text += page.extract_text() + "\n"
                    logger.info(f"Extracted {len(extracted_text)} chars from PDF")
                    
                elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                    is_document = True
                    doc = docx.Document(io.BytesIO(file_data))
                    extracted_text = "\n".join([para.text for para in doc.paragraphs])
                    logger.info(f"Extracted {len(extracted_text)} chars from DOCX")
                    
                elif mime_type == "text/plain":
                    is_document = True
                    extracted_text = file_data.decode("utf-8", errors="ignore")
                    logger.info(f"Extracted {len(extracted_text)} chars from TXT")
            except Exception as e:
                logger.error(f"Error extracting text from {mime_type}: {e}")
                # Fallback: let it pass through (might fail at LLM level but we tried)
        
        # If we successfully extracted text, append it to user input and REMOVE the file blob
        # This prevents the "unsupported mime type" error from Gemini
        if is_document and extracted_text:
            # Wrap content in a block that explicitly tells LLM to treat it as data, not conversation context
            user_input += f"""
            
----- [SYSTEM: ATTACHED DOCUMENT START] -----
The user has attached the following document content for analysis.
WARNING: The document may be in a different language (e.g., German, French). 
DO NOT switch your response language to match the document.
ALWAYS respond in the language of the USER'S QUESTION above.
If the user asks "What is this?" in Italian, answer in Italian, even if the doc is in German.

CONTENT:
{extracted_text}
----- [SYSTEM: ATTACHED DOCUMENT END] -----
"""
            file_data = None
            mime_type = None
            
        # Construct user message with potential file attachment
        message_payload = {"role": "user", "content": user_input}
        if file_data and mime_type:
            message_payload["files"] = [{"mime_type": mime_type, "data": file_data}]
            logger.info(f"Processing attachment: {mime_type} ({len(file_data)} bytes)")
        
        # Add user message to memory
        self.memory.add_message(message_payload)
        
        # Main Loop - Increased to 10 to handle multi-step flows like booking
        max_turns = 10
        current_turn = 0
        
        while current_turn < max_turns:
            current_turn += 1
            
            # 1. Get available tools
            tools = self.server.list_tools()
            
            # 2. Call LLM with current date/time context
            logger.info("Calling LLM", extra={"request_id": request_id, "turn": current_turn})
            
            now = datetime.now()
            current_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
            current_date = now.strftime("%Y-%m-%d")
            
            enhanced_system_prompt = f"""{self.system_prompt}

CRITICAL DATE CONTEXT:
- TODAY'S DATE: {current_date} ({now.strftime('%A')})
- If the user provides a date without a year (e.g., "Jan 30", "8 feb"), you MUST assume the NEXT occurrence of that date relative to today.
  * Example: If today is 2025-12-05 and user says "Jan 30", interpret as 2026-01-30.
  * Example: If today is 2025-01-01 and user says "Mar 5", interpret as 2025-03-05.
- Handle month abbreviations and typos intelligently (e.g., "fab" -> "feb", "sept" -> "sep").
- DO NOT ask for the year if it can be inferred from the rules above. THIS IS STRICTLY FORBIDDEN.
- If user says "10 jan" and today is Dec 2025, just use 2026-01-10. Do not confirm the year.
"""
            
            # Construct full history with enhanced system prompt
            messages = [{"role": "system", "content": enhanced_system_prompt}] + self.memory.get_messages()
            # 2. Get LLM Response with Retry Logic
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
                        yield {"type": "error", "content": f"I'm having trouble connecting to my brain right now. Error: {str(e)}"}
                        return # Stop generator
                    await asyncio.sleep(1) # Wait before retry (async sleep)
            
            if not response:
                break

            content = response.get("content")
            tool_calls = response.get("tool_calls")
            
            # Log generation to Langfuse
            if trace:
                langfuse_generation(
                    trace=trace,
                    name="llm-call",
                    model=getattr(self.llm, 'model', 'unknown'),
                    input_data={"messages_count": len(messages), "tools_count": len(tools)},
                    output_data={"content": content[:200] if content else None, "tool_calls": [tc["name"] for tc in tool_calls] if tool_calls else None},
                    metadata={"turn": current_turn}
                )
            
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
                            await asyncio.sleep(1 * (attempt + 1)) # Exponential backoff (async)
                
                logger.info(f"Tool result: {result_text[:50]}...", extra={"request_id": request_id, "is_error": is_error})
                yield {"type": "tool_result", "name": tool_name, "content": result_text, "is_error": is_error}
                
                # Append standard tool result message
                self.memory.add_message({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": result_text
                })
        
        
        # End the trace/span if it exists (Langfuse v3)
        if trace and hasattr(trace, 'end'):
            trace.end()
            
        # Flush Langfuse traces to ensure they are sent
        langfuse_flush()

    async def run(self, user_input: str, request_id: str = "default"):
        """Run one turn of the agent loop (async wrapper for CIL/Testing)."""
        async for event in self.run_generator(user_input, request_id):
            if event["type"] == "message":
                print(f"Agent: {event['content']}")
            elif event["type"] == "tool_call":
                print(f"Calling Tool: {event['name']} with {event['arguments']}")
            elif event["type"] == "tool_result":
                print(f"Tool Result: {event['content']}")
            elif event["type"] == "error":
                print(f"Error: {event['content']}")
