"""
================================================================================
CLI - Command Line Interface for the Agentic Travel Planner
================================================================================

This module provides a command-line interface (CLI) for interacting with the
Travel Agent. It's designed for development, testing, and demonstrations where
a web browser interface is not needed or desired.

Features:
---------
1. Direct Terminal Interaction: Chat with the agent directly from your terminal.
2. Multi-Provider Support: Works with OpenAI, Anthropic, or Google LLMs.
3. Same Agent Logic: Uses the exact same AgentOrchestrator as the web interface.
4. Simple REPL: Read-Eval-Print Loop for continuous conversation.

Usage:
------
    # Set your preferred LLM provider (optional, defaults to OpenAI)
    export LLM_PROVIDER=anthropic
    
    # Run the CLI
    python -m travel_agent.cli
    
    # Or directly
    python travel_agent/cli.py

Commands:
---------
    Type your travel-related queries naturally:
    > Find flights from NYC to London on March 15
    > Book the first flight
    > What's the weather like in London?
    
    To exit:
    > quit
    > exit
    (or press Ctrl+C)

Architecture:
-------------
The CLI follows the same architecture as the web server:

    Terminal (stdin/stdout)
           │
           ▼
    ┌──────────────┐
    │   CLI Main   │  ← This module
    │   (REPL)     │
    └──────┬───────┘
           │
           ▼
    ┌─────────────────┐
    │ AgentOrchestrator│
    └────────┬────────┘
             │
      ┌──────┴───────┐
      ▼              ▼
  ┌───────┐    ┌───────────┐
  │  LLM  │    │ MCP Server│
  └───────┘    │ (Tools)   │
               └───────────┘

Differences from Web Server:
----------------------------
- No streaming: CLI waits for complete responses
- Blocking I/O: Uses standard input() which blocks the event loop
- Direct output: Prints directly to console instead of JSON streaming

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import os      # Environment variable access
import sys     # System path manipulation for imports
import asyncio # Async/await support for running the agent

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

# Add the parent directory (project root) to Python's module search path.
# This ensures 'travel_agent' package can be imported regardless of how
# the script is invoked.
#
# Path calculation:
#   __file__ = /project/travel_agent/cli.py
#   abspath = /project/travel_agent/cli.py  
#   dirname = /project/travel_agent/
#   dirname again = /project/  <- This is added to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# =============================================================================
# ENVIRONMENT LOADING
# =============================================================================

from dotenv import load_dotenv

# Load environment variables from .env file.
# This must happen BEFORE importing Config which reads these variables.
load_dotenv()

# =============================================================================
# LOCAL IMPORTS
# =============================================================================

# Configuration class for API key management
from travel_agent.config import Config

# LLM provider factory function
from travel_agent.agent.llm import get_llm_provider

# MCP Server for tool management
from travel_agent.mcp.mcp_server import MCPServer

# Main agent orchestrator
from travel_agent.agent.orchestrator import AgentOrchestrator

# Tool functions to register with the agent
from travel_agent.tools import (
    search_flights,       # Search available flights
    book_flight,          # Book a flight
    rent_car,             # Rent a car
    get_forecast,         # Get weather forecast
    process_payment,      # Process payment
    get_current_datetime  # Get current date/time
)

# =============================================================================
# MAIN FUNCTION
# =============================================================================

async def main():
    """
    Main entry point for the CLI application.
    
    This async function:
    1. Validates configuration (API keys)
    2. Initializes the LLM provider
    3. Sets up the MCP Server with tools
    4. Creates the AgentOrchestrator
    5. Runs an interactive REPL loop
    
    The function is async because the AgentOrchestrator.run() method
    is async, allowing the LLM and tools to use non-blocking I/O.
    
    Returns:
        None. The function runs until the user exits.
    
    Raises:
        No exceptions are raised externally; errors are caught and printed.
    """
    
    # -------------------------------------------------------------------------
    # Step 1: Validate Configuration
    # -------------------------------------------------------------------------
    # Ensure at least one LLM API key is configured.
    # Without this, the agent cannot function.
    if not Config.validate():
        return  # validate() already prints the error message

    # -------------------------------------------------------------------------
    # Step 2: Select and Initialize LLM Provider
    # -------------------------------------------------------------------------
    
    # Get the preferred LLM provider from environment.
    # Default to OpenAI if not specified.
    provider_name = os.getenv("LLM_PROVIDER", "openai").lower()
    api_key = ""
    
    # Map provider name to its API key
    if provider_name == "openai":
        api_key = Config.OPENAI_API_KEY
    elif provider_name == "anthropic":
        api_key = Config.ANTHROPIC_API_KEY
    elif provider_name == "google":
        api_key = Config.GOOGLE_API_KEY
        
    # Verify we have an API key for the selected provider
    if not api_key:
        print(f"Error: API Key for {provider_name} is missing.")
        return

    # Create the LLM provider instance
    try:
        # get_llm_provider returns an async-capable LLM client
        llm = get_llm_provider(provider_name, api_key)
    except ImportError as e:
        # This happens if the provider's SDK is not installed
        print(f"Error initializing LLM: {e}")
        return

    # -------------------------------------------------------------------------
    # Step 3: Setup MCP Server and Register Tools
    # -------------------------------------------------------------------------
    
    # Create a new MCP Server instance
    server = MCPServer()
    
    # Register all available tools with the server.
    # Each tool is introspected to generate its JSON schema for the LLM.
    server.register_tool(search_flights)      # Search for flights
    server.register_tool(book_flight)         # Book a selected flight
    server.register_tool(rent_car)            # Rent a car
    server.register_tool(get_forecast)        # Weather forecast
    server.register_tool(process_payment)     # Payment processing
    server.register_tool(get_current_datetime) # Current date/time

    # -------------------------------------------------------------------------
    # Step 4: Initialize Agent Orchestrator
    # -------------------------------------------------------------------------
    
    # The AgentOrchestrator ties together:
    # - The LLM (for reasoning and generating responses)
    # - The MCP Server (for tool discovery and execution)
    # - Memory (for conversation history - using default InMemoryMemory)
    agent = AgentOrchestrator(llm, server)

    # -------------------------------------------------------------------------
    # Step 5: Welcome Message
    # -------------------------------------------------------------------------
    
    print(f"Travel Agent initialized with {provider_name}. Ready to help!")
    print("Type 'quit' to exit.")

    # -------------------------------------------------------------------------
    # Step 6: Interactive REPL Loop
    # -------------------------------------------------------------------------
    
    while True:
        try:
            # Read user input from the terminal.
            # Note: input() is blocking, which is fine for a CLI demo.
            # For a truly non-blocking CLI, you would use aioconsole or similar.
            user_input = input("\nYou: ")
            
            # Check for exit commands
            if user_input.lower() in ["quit", "exit"]:
                break
                
            # Run the agent asynchronously.
            # This processes the user's message, potentially calling tools,
            # and prints the results to the console.
            await agent.run(user_input)
            
        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            break
        except Exception as e:
            # Catch any unexpected errors and continue the loop
            print(f"An error occurred: {e}")

# =============================================================================
# SCRIPT ENTRY POINT  
# =============================================================================

if __name__ == "__main__":
    # Run the async main function using asyncio.run().
    # This creates an event loop, runs main() until completion,
    # then closes the event loop.
    asyncio.run(main())
