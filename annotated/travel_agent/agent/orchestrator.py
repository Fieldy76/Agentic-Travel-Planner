# Import type hints for better code safety and documentation
from typing import List, Dict, Any, Optional
# Import json for potential serialization needs
import json
# Import logging for observability
import logging
# Import time for retry delays
import time
# Import our LLM provider wrapper
from .llm import LLMProvider
# Import the MCP server that manages our tools
from ..mcp.server import MCPServer
# Import memory abstraction for conversation state management
from .memory import AgentMemory, InMemoryMemory
# Import logging setup from config
from ..config import setup_logging

# Configure structured logging when this module is imported
# This ensures all log messages use our JSON formatter
setup_logging()
# Create a logger specific to this module
# Logs will show "module": "orchestrator" in the JSON output
logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """
    The 'brain' of the travel agent.
    
    Orchestrates the interaction between:
    - The LLM (for decision-making)
    - The MCP server (for tool execution)
    - The memory system (for conversation state)
    """
    
    def __init__(self, llm: LLMProvider, server: MCPServer, memory: Optional[AgentMemory] = None):
        """
        Initialize the orchestrator.
        
        Args:
            llm: The language model provider (OpenAI, Anthropic, or Google)
            server: MCP server instance with registered tools
            memory: Optional memory system (defaults to InMemoryMemory)
        """
        self.llm = llm  # The LLM that makes decisions
        self.server = server  # The tool server that executes actions
        # Use provided memory or create a new in-memory instance
        self.memory = memory or InMemoryMemory()
        
        # System prompt defines the agent's personality and capabilities
        # This is sent with every LLM request to maintain consistent behavior
        self.system_prompt = """You are a helpful travel assistant. 
        You have access to tools to search flights, book flights, rent cars, check weather, and process payments.
        
        When a user asks for a travel plan:
        1. Search for options (flights, cars, weather).
        2. Present options to the user.
        3. If the user confirms, proceed to booking and payment.
        
        Always check the weather before finalizing a plan.
        """

    def run(self, user_input: str, request_id: str = "default"):
        """
        Execute one turn of the agent conversation loop.
        
        This is the main entry point for processing user requests.
        
        Args:
            user_input: The user's message or request
            request_id: Unique identifier for request tracing across logs
        """
        # Log the start of the agent turn with the request ID for tracing
        logger.info(f"Starting agent turn", extra={"request_id": request_id})
        
        # Add the user's message to conversation memory
        self.memory.add_message({"role": "user", "content": user_input})
        
        # Main agent loop - continues until the LLM decides no more actions are needed
        max_turns = 10  # Safety limit to prevent infinite loops
        current_turn = 0
        
        while current_turn < max_turns:
            current_turn += 1
            
            # STEP 1: Get the list of available tools from the MCP server
            # This tells the LLM what actions it can perform
            tools = self.server.list_tools()
            
            # STEP 2: Call the LLM to decide what to do next
            logger.info("Calling LLM", extra={"request_id": request_id, "turn": current_turn})
            
            # Construct the full message history
            # System prompt + conversation history from memory
            messages = [{"role": "system", "content": self.system_prompt}] + self.memory.get_messages()
            
            # Call the LLM with error handling
            try:
                response = self.llm.call_tool(messages, tools)
            except Exception as e:
                # Log LLM failures and exit gracefully
                logger.error(f"LLM call failed: {e}", extra={"request_id": request_id})
                break
            
            # Extract the LLM's response components
            content = response.get("content")  # Text response to the user
            tool_calls = response.get("tool_calls")  # Tools the LLM wants to invoke
            
            # If the LLM provided a text response, show it and save to memory
            if content:
                logger.info(f"Agent response: {content[:50]}...", extra={"request_id": request_id})
                self.memory.add_message({"role": "assistant", "content": content})
                print(f"Agent: {content}")
                
            # If there are no tool calls, the LLM is done - exit the loop
            if not tool_calls:
                logger.info("No tool calls, turn complete", extra={"request_id": request_id})
                break
                
            # STEP 3: Execute each tool the LLM requested
            for tool_call in tool_calls:
                tool_name = tool_call["name"]  # Which tool to call
                tool_args = tool_call["arguments"]  # Arguments for the tool
                tool_id = tool_call["id"]  # Unique ID to match result with call
                
                logger.info(f"Executing tool: {tool_name}", extra={"request_id": request_id, "tool_args": tool_args})
                print(f"Calling Tool: {tool_name} with {tool_args}")
                
                # RELIABILITY: Implement retry logic with exponential backoff
                max_retries = 3  # Try up to 3 times
                result_text = ""
                is_error = False
                
                # Retry loop for resilient tool execution
                for attempt in range(max_retries):
                    try:
                        # Attempt to execute the tool
                        result = self.server.call_tool(tool_name, tool_args)
                        result_text = result.content[0]["text"]
                        is_error = result.isError
                        break  # Success - exit retry loop
                    except Exception as e:
                        # Log the failure
                        logger.warning(f"Tool execution failed (attempt {attempt+1}/{max_retries}): {e}", 
                                     extra={"request_id": request_id})
                        
                        # If this was the last attempt, record the error
                        if attempt == max_retries - 1:
                            result_text = f"Error executing tool {tool_name}: {str(e)}"
                            is_error = True
                        else:
                            # Exponential backoff: wait longer before each retry
                            # First retry: 1s, second: 2s, third: 3s
                            time.sleep(1 * (attempt + 1))
                
                # Log the result (first 50 chars to avoid log bloat)
                logger.info(f"Tool result: {result_text[:50]}...", 
                          extra={"request_id": request_id, "is_error": is_error})
                print(f"Tool Result: {result_text}")
                
                # Add the tool result to conversation memory
                # The LLM will see this result in the next iteration
                self.memory.add_message({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "name": tool_name,
                    "content": result_text
                })
