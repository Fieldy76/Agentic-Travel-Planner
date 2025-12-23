"""
================================================================================
AGENT ORCHESTRATOR - The Brain of the Agentic Travel Planner
================================================================================

This module implements the AgentOrchestrator, the central component that 
coordinates interactions between the LLM (language model) and tools. It 
manages the agentic loop where the LLM reasons about user input, decides
which tools to use, executes them, and formulates responses.

Core Responsibilities:
----------------------
1. Conversation Management: Maintains message history using AgentMemory
2. Document Processing: Extracts text from PDFs, DOCX, and text files
3. Tool Orchestration: Executes tools and feeds results back to the LLM
4. Error Handling: Retries failed LLM/tool calls with exponential backoff
5. Date Context: Injects current date/time into system prompts

Agentic Loop Architecture:
--------------------------
The orchestrator implements a ReAct-style (Reasoning + Acting) loop:

    ┌───────────────────────────────────────────────────┐
    │                   User Input                      │
    └────────────────────┬──────────────────────────────┘
                         │
                         ▼
    ┌───────────────────────────────────────────────────┐
    │              Add to Memory                        │
    │        (Store user message in history)            │
    └────────────────────┬──────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          │              ▼              │
          │  ┌───────────────────────┐  │
          │  │     LLM Reasoning     │  │
          │  │   (What should I do?) │  │
          │  └──────────┬────────────┘  │
          │             │               │
          │      ┌──────┴──────┐       │
          │      ▼             ▼       │
          │   TEXT          TOOL       │
          │  RESPONSE       CALLS      │
          │      │             │       │
          │      │      ┌──────┴─────┐ │
          │      │      ▼            │ │
          │      │  ┌────────────┐   │ │
          │      │  │  Execute   │   │ │
          │      │  │   Tools    │   │ │
          │      │  └─────┬──────┘   │ │
          │      │        │          │ │
          │      │        ▼          │ │
          │      │  Store Results   └─┤ (Loop back to LLM)
          │      │   in Memory        │
          │      │                    │
          └──────┴────────────────────┘
                         │
                         ▼
    ┌───────────────────────────────────────────────────┐
    │              Final Response                       │
    │         (No more tool calls needed)               │
    └───────────────────────────────────────────────────┘

Streaming Architecture:
-----------------------
The run_generator() method is an async generator that yields events:
- {"type": "message", "content": "..."}: Text from LLM
- {"type": "tool_call", "name": "...", "arguments": {...}}: Tool invocation
- {"type": "tool_result", "name": "...", "content": "..."}: Tool output
- {"type": "error", "content": "..."}: Error condition

This allows real-time UI updates as the agent "thinks" and acts.

System Prompt Design:
---------------------
The system prompt is extensive and includes:
- Language consistency rules (respond in user's language)
- Date handling instructions
- Booking workflow rules
- Email collection for booking confirmation receipts
- Formatting requirements (no bold, use numbered lists)
- Multi-passenger pricing logic
- Flight selection validation

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

from typing import List, Dict, Any, Optional  # Type hints
import json                                   # JSON serialization
import logging                                # Logging facility
import asyncio                                # Async/await support
from datetime import datetime                 # Date/time handling
import io                                     # In-memory file handling

# Document parsing libraries
import pypdf   # PDF text extraction
import docx    # DOCX (Word) document parsing

# Local imports
from .llm import LLMProvider, LANGFUSE_ENABLED, langfuse_trace, langfuse_generation, langfuse_flush  # LLM provider interface + observability with manual tracing
from ..mcp.mcp_server import MCPServer        # Tool server
from .memory import AgentMemory, InMemoryMemory  # Conversation memory
from ..config import setup_logging            # JSON logging configuration

# =============================================================================
# LOGGING SETUP
# =============================================================================

# Ensure structured JSON logging is configured
setup_logging()

# Create a module-specific logger
logger = logging.getLogger(__name__)

# =============================================================================
# AGENT ORCHESTRATOR CLASS
# =============================================================================

class AgentOrchestrator:
    """
    The central orchestrator that coordinates LLM reasoning with tool execution.
    
    This class implements the agentic loop pattern where the LLM can:
    1. Reason about the user's request
    2. Decide which tools to call (if any)
    3. Execute tools and observe results
    4. Continue reasoning based on tool outputs
    5. Provide a final response
    
    The orchestrator manages:
    - LLM calls with retry logic
    - Tool execution with error handling
    - Conversation memory for context
    - Document processing for file uploads
    
    Attributes:
        llm (LLMProvider): The language model provider
        server (MCPServer): The tool server with registered tools
        memory (AgentMemory): Conversation history storage
        system_prompt (str): The system instructions for the LLM
    
    Example:
        >>> llm = get_llm_provider("openai", "sk-...")
        >>> server = MCPServer()
        >>> server.register_tool(search_flights)
        >>> 
        >>> agent = AgentOrchestrator(llm, server)
        >>> 
        >>> async for event in agent.run_generator("Find flights to NYC"):
        ...     print(event)
    """
    
    def __init__(self, llm: LLMProvider, server: MCPServer, memory: Optional[AgentMemory] = None):
        """
        Initialize the AgentOrchestrator.
        
        Args:
            llm: LLM provider instance (OpenAI, Anthropic, or Google)
            server: MCP Server with registered tools
            memory: Optional memory implementation. Defaults to InMemoryMemory.
                   Can be replaced with persistent storage for production.
        """
        self.llm = llm
        self.server = server
        # Use provided memory or default to in-memory storage
        self.memory = memory or InMemoryMemory()
        
        # =====================================================================
        # SYSTEM PROMPT - The Agent's "Personality" and Rules
        # =====================================================================
        # This comprehensive prompt guides the LLM's behavior as a travel agent.
        # It includes:
        # - Language handling rules
        # - Date format requirements
        # - Booking workflow steps
        # - Formatting guidelines
        # - Multi-passenger pricing logic
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

    # @langfuse_observe(name="agent-turn") <-- DECORATOR REMOVED in favor of manual tracing
    async def run_generator(self, user_input: str, file_data: Optional[bytes] = None, mime_type: Optional[str] = None, request_id: str = "default"):
        """
        Run one turn of the agent loop, yielding events (Async Generator).
        
        This is the core execution logic. It processes input, iterates on tool
        calls, and yields periodic updates to the UI.
        
        Args:
            user_input: The user's message
            file_data: Optional bytes of an uploaded file
            mime_type: Optional MIME type of the file
            request_id: Request ID for tracing
            
        Yields:
            - Retries tool calls up to 3 times with exponential backoff
            - Documents (PDF, DOCX, TXT) are extracted server-side
            - Images are passed directly to the LLM for multimodal processing
        """
        logger.info(f"Starting agent turn", extra={"request_id": request_id})
        
        # =====================================================================
        # STEP 1: Document Processing (Server-Side Text Extraction)
        # =====================================================================
        # For documents like PDFs and Word files, we extract the text content
        # server-side and append it to the user's message. This is more reliable
        # than relying on the LLM to process raw document bytes.
        
        extracted_text = ""
        is_document = False
        
        if file_data and mime_type:
            try:
                if mime_type == "application/pdf":
                    # Extract text from PDF using pypdf
                    is_document = True
                    pdf_reader = pypdf.PdfReader(io.BytesIO(file_data))
                    for page in pdf_reader.pages:
                        extracted_text += page.extract_text() + "\n"
                    logger.info(f"Extracted {len(extracted_text)} chars from PDF")
                    
                elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                    # Extract text from DOCX using python-docx
                    is_document = True
                    doc = docx.Document(io.BytesIO(file_data))
                    extracted_text = "\n".join([para.text for para in doc.paragraphs])
                    logger.info(f"Extracted {len(extracted_text)} chars from DOCX")
                    
                elif mime_type == "text/plain":
                    # Plain text files - just decode
                    is_document = True
                    extracted_text = file_data.decode("utf-8", errors="ignore")
                    logger.info(f"Extracted {len(extracted_text)} chars from TXT")
                    
            except Exception as e:
                logger.error(f"Error extracting text from {mime_type}: {e}")
                # Fallback: let it pass through (might fail at LLM level)
        
        # If we extracted text, append it to the user input with clear markers
        # This helps the LLM understand that this is attached document content
        if is_document and extracted_text:
            # Wrap content with clear delimiters and instructions
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
            # Clear file data since we've extracted the text
            file_data = None
            mime_type = None
            
        # =====================================================================
        # STEP 2: Construct User Message and Add to Memory
        # =====================================================================
        
        # Build the message payload
        message_payload = {"role": "user", "content": user_input}
        
        # For non-document files (images), attach the raw data
        # The LLM provider will handle multimodal processing
        if file_data and mime_type:
            message_payload["files"] = [{"mime_type": mime_type, "data": file_data}]
            logger.info(f"Processing attachment: {mime_type} ({len(file_data)} bytes)")
        
        # Add the user message to conversation history
        self.memory.add_message(message_payload)
        
        # =====================================================================
        # STEP 3: Main Agent Loop
        # =====================================================================
        # The agent can make multiple tool calls before providing a final response.
        # We limit this to 10 turns to prevent infinite loops.
        
        max_turns = 10  # Safety limit to prevent runaway loops
        current_turn = 0
        
        while current_turn < max_turns:
            current_turn += 1
            
            # -----------------------------------------------------------------
            # 3.1: Get available tools from the MCP Server
            # -----------------------------------------------------------------
            tools = self.server.list_tools()
            
            # -----------------------------------------------------------------
            # 3.2: Build messages with enhanced system prompt
            # -----------------------------------------------------------------
            logger.info("Calling LLM", extra={"request_id": request_id, "turn": current_turn})
            
            # Get current date/time for context
            now = datetime.now()
            current_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
            current_date = now.strftime("%Y-%m-%d")
            
            # Enhance system prompt with current date context
            # This helps the LLM handle relative dates ("tomorrow", "next week")
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
            
            # Construct full message history with system prompt
            messages = [{"role": "system", "content": enhanced_system_prompt}] + self.memory.get_messages()
            
            # -----------------------------------------------------------------
            # 3.3: Call LLM with retry logic
            # -----------------------------------------------------------------
            response = None
            max_llm_retries = 3
            
            for attempt in range(max_llm_retries):
                try:
                    response = await self.llm.call_tool(messages, tools)
                    break  # Success - exit retry loop
                except Exception as e:
                    logger.warning(f"LLM call failed (attempt {attempt+1}/{max_llm_retries}): {e}", extra={"request_id": request_id})
                    if attempt == max_llm_retries - 1:
                        # All retries exhausted
                        logger.error(f"LLM error after {max_llm_retries} attempts: {e}")
                        yield {"type": "error", "content": f"I'm having trouble connecting to my brain right now. Error: {str(e)}"}
                        return  # Stop generator
                    await asyncio.sleep(1)  # Wait before retry
            
            if not response:
                break  # Safety check
            
            # -----------------------------------------------------------------
            # 3.4: Process LLM response
            # -----------------------------------------------------------------
            content = response.get("content")
            tool_calls = response.get("tool_calls")
            
            # Add assistant message to memory if there's content or tool calls
            if content or tool_calls:
                # Log response summary
                if content:
                    logger.info(f"Agent response: {content[:50]}...", extra={"request_id": request_id})
                
                # Store in memory for context in subsequent turns
                self.memory.add_message({
                    "role": "assistant", 
                    "content": content,
                    "tool_calls": tool_calls
                })
                
                # Yield text content to the client (only if present)
                if content:
                    yield {"type": "message", "content": content}

            # Log generation to Langfuse (v3 compatible)
            if trace:
                langfuse_generation(
                    trace=trace,
                    name="llm-call",
                    model=self.llm.model,
                    input=messages,
                    output=response,
                    metadata={"turn": current_turn, "request_id": request_id}
                )

                
            # Check if we're done (no more tool calls)
            if not tool_calls:
                logger.info("No tool calls, turn complete", extra={"request_id": request_id})
                break
                
            # -----------------------------------------------------------------
            # 3.5: Execute tool calls
            # -----------------------------------------------------------------
            for tool_call in tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["arguments"]
                tool_id = tool_call["id"]
                
                logger.info(f"Executing tool: {tool_name}", extra={"request_id": request_id, "tool_args": tool_args})
                
                # Notify client that we're calling a tool
                yield {"type": "tool_call", "name": tool_name, "arguments": tool_args}
                
                # Execute tool with retry logic and exponential backoff
                max_retries = 3
                result_text = ""
                is_error = False
                
                for attempt in range(max_retries):
                    try:
                        result = await self.server.call_tool(tool_name, tool_args)
                        result_text = result.content[0]["text"]
                        is_error = result.isError
                        break  # Success
                    except Exception as e:
                        logger.warning(f"Tool execution failed (attempt {attempt+1}/{max_retries}): {e}", extra={"request_id": request_id})
                        if attempt == max_retries - 1:
                            result_text = f"Error executing tool {tool_name}: {str(e)}"
                            is_error = True
                        else:
                            # Exponential backoff: 1s, 2s, 3s
                            await asyncio.sleep(1 * (attempt + 1))
                
                logger.info(f"Tool result: {result_text[:50]}...", extra={"request_id": request_id, "is_error": is_error})
                
                # Yield tool result to client
                yield {"type": "tool_result", "name": tool_name, "content": result_text, "is_error": is_error}
                
                # Add tool result to memory for LLM context
                self.memory.add_message({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": result_text
                })
        
        # End the trace/span if it exists (Langfuse v3)
        if trace and hasattr(trace, 'end'):
            trace.end()
            
        # Flush Langfuse traces to ensure they are sent (important for async)
        langfuse_flush()

    async def run(self, user_input: str, request_id: str = "default"):
        """
        Run one turn of the agent loop with console output.
        
        This is a convenience wrapper around run_generator() for CLI usage.
        It consumes all events and prints them to the console.
        
        Args:
            user_input: The user's message text
            request_id: Unique identifier for request tracing
        
        Example:
            >>> agent = AgentOrchestrator(llm, server)
            >>> await agent.run("Find flights to NYC")
            Agent: I'll search for flights to NYC...
            Calling Tool: search_flights with {'origin': '...', 'destination': 'NYC'}
            Tool Result: [flight data]
            Agent: I found 3 flights...
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
