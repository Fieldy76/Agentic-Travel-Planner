"""
================================================================================
WEB SERVER - FastAPI-based HTTP Server for the Agentic Travel Planner
================================================================================

This module implements the main web server that exposes the AI Travel Agent 
through a RESTful API. It serves as the entry point for the web-based interface.

Key Features:
-------------
1. FastAPI Framework: High-performance async web framework with automatic 
   OpenAPI documentation.

2. Real-time Streaming: Uses Server-Sent Events (SSE) via StreamingResponse
   to provide real-time updates as the agent "thinks" and executes tools.

3. File Upload Support: Handles multipart/form-data for document uploads
   (PDFs, images, etc.) that the agent can analyze.

4. LLM Provider Flexibility: Supports multiple LLM backends (OpenAI, Anthropic,
   Google) with automatic fallback if the preferred provider's key is missing.

5. CORS Enabled: Allows cross-origin requests for frontend integration.

Architecture Overview:
----------------------
    Browser/Client
          │
          ▼
    ┌─────────────────┐
    │   FastAPI App   │  ← This module
    │   (web_server)  │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ AgentOrchestrator│  ← Coordinates LLM and tools
    └────────┬────────┘
             │
      ┌──────┴───────┐
      ▼              ▼
  ┌───────┐    ┌───────────┐
  │  LLM  │    │ MCP Server│
  └───────┘    │ (Tools)   │
               └───────────┘

Usage:
------
    # Start the server (development mode with auto-reload)
    python web_server.py
    
    # Or using uvicorn directly
    uvicorn web_server:app --host 0.0.0.0 --port 5000 --reload

API Endpoints:
--------------
    GET  /           - Serves the main HTML UI (static/index.html)
    POST /api/chat   - Main chat endpoint with file upload support
                       Request: multipart/form-data with 'message' and optional 'file'
                       Response: NDJSON stream of agent events

Dependencies:
-------------
    - fastapi: Web framework
    - uvicorn: ASGI server
    - python-multipart: For file uploads in FastAPI
    - python-dotenv: Environment variable management

Environment Variables:
----------------------
    LLM_PROVIDER      - Preferred LLM provider: "anthropic", "openai", or "google"
    ANTHROPIC_API_KEY - API key for Claude models
    OPENAI_API_KEY    - API key for GPT models  
    GOOGLE_API_KEY    - API key for Gemini models

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

# Standard library imports
import os          # Operating system interfaces (environment variables, paths)
import sys         # System-specific parameters (path manipulation)
import json        # JSON encoding/decoding for API responses
import logging     # Python's built-in logging facility
import asyncio     # Asynchronous I/O support for async/await patterns

# Type hints for better code documentation and IDE support
from typing import AsyncGenerator  # For typing the streaming response generator

# Third-party imports - Web framework
import uvicorn                                              # ASGI server to run FastAPI
from fastapi import FastAPI, HTTPException, Request, Form, File, UploadFile  # FastAPI components
from fastapi.responses import StreamingResponse, FileResponse  # Response types
from fastapi.staticfiles import StaticFiles                 # Serve static files (CSS, JS)
from fastapi.middleware.cors import CORSMiddleware          # Cross-Origin Resource Sharing

# Environment variable management
from dotenv import load_dotenv  # Load .env file into environment

# =============================================================================
# PATH CONFIGURATION
# =============================================================================

# Add the project root directory to Python's module search path.
# This allows importing from 'travel_agent' package regardless of the 
# current working directory when the script is executed.
# 
# Example: If this file is at /project/annotated/web_server.py
#          Then we add /project/annotated to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# =============================================================================
# ENVIRONMENT CONFIGURATION
# =============================================================================

# Load environment variables from a .env file in the current directory.
# This is essential for loading API keys securely without hardcoding them.
# The load_dotenv() function reads key-value pairs from .env and adds them
# to os.environ, making them accessible via os.getenv().
load_dotenv()

# =============================================================================
# LOCAL IMPORTS (After path configuration)
# =============================================================================

# Configuration module - manages API keys and app settings
from travel_agent.config import Config

# LLM provider factory - creates the appropriate LLM client based on provider name
from travel_agent.agent.llm import get_llm_provider

# MCP (Model Context Protocol) Server - manages tool registration and execution
from travel_agent.mcp.mcp_server import MCPServer

# Agent Orchestrator - the brain that coordinates LLM reasoning with tool usage
from travel_agent.agent.orchestrator import AgentOrchestrator

# Tool functions - the actual capabilities the agent can use
from travel_agent.tools import (
    search_flights,       # Search for available flights
    book_flight,          # Book a specific flight
    rent_car,             # Rent a car at destination
    get_forecast,         # Get weather forecasts
    process_payment,      # Process payments via Stripe
    get_current_datetime  # Get current date/time for context
)

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

# Configure the logging system with INFO level.
# This means DEBUG messages are suppressed, but INFO, WARNING, ERROR, 
# and CRITICAL messages will be displayed.
logging.basicConfig(level=logging.INFO)

# Create a logger specific to this module using __name__.
# This allows filtering logs by module and follows Python best practices.
# The logger name will be the fully qualified module name.
logger = logging.getLogger(__name__)

# =============================================================================
# FASTAPI APPLICATION INITIALIZATION
# =============================================================================

# Create the FastAPI application instance.
# FastAPI automatically generates OpenAPI (Swagger) documentation at /docs
# and ReDoc documentation at /redoc.
app = FastAPI()

# =============================================================================
# STATIC FILE SERVING
# =============================================================================

# Mount the 'static' directory to serve static files like HTML, CSS, and JS.
# Any request to /static/* will serve files from the 'static' directory.
# 
# Example: /static/styles.css serves static/styles.css
# 
# The 'name' parameter is used for URL generation with url_for().
app.mount("/static", StaticFiles(directory="static"), name="static")

# =============================================================================
# CORS (Cross-Origin Resource Sharing) MIDDLEWARE
# =============================================================================

# Add CORS middleware to allow cross-origin requests.
# This is necessary when the frontend is served from a different domain/port
# than the API (e.g., frontend on localhost:3000, API on localhost:5000).
#
# WARNING: allow_origins=["*"] allows ANY origin - this is fine for development
# but should be restricted to specific domains in production for security.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Which origins can access the API
    allow_credentials=True,     # Allow cookies to be included in requests
    allow_methods=["*"],        # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],        # Allow all headers
)

# =============================================================================
# GLOBAL STATE
# =============================================================================

# Global variable to store the initialized agent.
# This is populated during the startup event and used by the chat endpoint.
# Using a global variable here is acceptable because:
# 1. FastAPI runs in a single process for simple deployments
# 2. The agent is stateless (memory per request is handled inside)
# 
# For production with multiple workers, consider using dependency injection
# or a proper state management solution.
agent = None

# =============================================================================
# AGENT INITIALIZATION
# =============================================================================

async def initialize_agent():
    """
    Initialize the AI agent with all its components.
    
    This function performs the following steps:
    1. Validates the configuration (checks for required API keys)
    2. Selects the appropriate LLM provider based on environment settings
    3. Creates an MCP Server and registers all available tools
    4. Creates the AgentOrchestrator that ties everything together
    
    Returns:
        bool: True if initialization succeeded, False otherwise.
    
    Side Effects:
        - Sets the global 'agent' variable on success
        - Logs status messages during initialization
    
    Provider Selection Logic:
    -------------------------
    The function first checks LLM_PROVIDER environment variable for the 
    preferred provider. If its API key is missing, it falls back to any 
    available provider with a valid key. This ensures maximum flexibility
    during development when not all API keys may be configured.
    """
    # Declare we're modifying the global agent variable, not creating a local one
    global agent
    
    # Step 1: Validate configuration
    # This checks if at least one LLM API key is present
    if not Config.validate(): 
        logger.error("Config validation failed.")
        return False
    
    # Step 2: Determine which LLM provider to use
    # Default to Anthropic (Claude) if no preference is specified
    provider_name = os.getenv("LLM_PROVIDER", "ANTHROPIC").lower()
    api_key = None
    
    # Map provider names to their corresponding API keys from config
    provider_map = {
        "anthropic": Config.ANTHROPIC_API_KEY,
        "openai": Config.OPENAI_API_KEY,
        "google": Config.GOOGLE_API_KEY,
    }

    # Try to get the API key for the preferred provider
    if provider_name in provider_map and provider_map[provider_name]:
        api_key = provider_map[provider_name]
        
    # Fallback logic: If preferred provider's key is missing, try others
    if not api_key:
        logger.warning(
            f"API key for preferred provider ({provider_name.upper()}) is missing. searching fallback..."
        )
        # Iterate through all providers to find one with a valid key
        for name, key in provider_map.items():
            if key:
                provider_name = name
                api_key = key
                logger.info(f"Found valid key for fallback provider: {provider_name.upper()}")
                break 

    # If no valid API key found at all, we cannot proceed
    if not api_key:
        logger.error("No valid LLM API key found.")
        return False

    # Step 3: Create the LLM provider instance
    try:
        # The get_llm_provider factory function returns the appropriate 
        # LLM client (OpenAI, Anthropic, or Google) based on provider_name
        llm = get_llm_provider(provider_name, api_key)
    except ImportError as e:
        # This can happen if the SDK for the provider is not installed
        # e.g., 'openai' pip package is missing
        logger.error(f"Error initializing LLM: {e}")
        return False

    # Step 4: Create MCP Server and register tools
    # The MCP Server acts as a tool registry - it knows about all available 
    # tools, their schemas (for LLM function calling), and can execute them.
    server = MCPServer()
    
    # Register each tool function with the server
    # The server introspects the function signature to generate tool schemas
    server.register_tool(search_flights)     # Search for flights between airports
    server.register_tool(book_flight)        # Book a selected flight
    server.register_tool(rent_car)           # Rent a car at a location
    server.register_tool(get_forecast)       # Get weather forecast
    server.register_tool(process_payment)    # Process payment via Stripe
    server.register_tool(get_current_datetime)  # Get current date/time

    # Step 5: Create the Agent Orchestrator
    # The orchestrator ties together the LLM and tools, managing the 
    # conversation loop where the LLM can reason and call tools as needed.
    agent = AgentOrchestrator(llm, server)
    
    logger.info(f"Agent initialized successfully with: {provider_name.upper()}")
    return True

# =============================================================================
# APPLICATION LIFECYCLE EVENTS
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """
    FastAPI startup event handler.
    
    This function is called automatically when the FastAPI application starts.
    It attempts to initialize the real agent, and if that fails (e.g., due to
    missing API keys), it creates a mock agent for UI development/testing.
    
    The mock agent:
    - Echoes back the user's message
    - Acknowledges file uploads
    - Simulates a tool call
    - Returns a message explaining API keys are missing
    
    This allows developers to work on the UI without valid API keys.
    """
    success = await initialize_agent()
    
    if not success:
        logger.warning("Agent initialization failed. Using Mock Agent for UI testing.")
        
        # Define a lightweight mock agent class for development
        class MockAgent:
            """
            Mock agent that simulates the real agent's behavior.
            
            Useful for:
            - UI development without API keys
            - Testing the frontend/backend communication
            - Demonstrating the streaming response format
            """
            async def run_generator(self, user_input, file_data=None, mime_type=None, request_id="mock"):
                """
                Simulates the agent's response generator.
                
                Yields events in the same format as the real agent:
                - message: Text responses from the agent
                - tool_call: Tool invocations
                - tool_result: Results from tool execution
                """
                # First response: Echo the user's message
                yield {"type": "message", "content": f"I received your message: '{user_input}'. (Mock Agent)"}
                
                # If a file was uploaded, acknowledge it
                if file_data:
                    yield {"type": "message", "content": f"I also received a file: {len(file_data)} bytes."}
                
                # Simulate a tool call
                yield {"type": "tool_call", "name": "mock_tool", "arguments": {"query": "test"}}
                
                # Simulate tool execution delay
                await asyncio.sleep(1)
                
                # Simulate tool result
                yield {"type": "tool_result", "name": "mock_tool", "content": "Mock result", "is_error": False}
                
                # Final message explaining the mock mode
                yield {"type": "message", "content": "This is a mock response because API keys are missing."}

        # Replace the global agent with our mock
        global agent
        agent = MockAgent()

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
async def index():
    """
    Root endpoint - serves the main HTML page.
    
    Returns the static index.html file which contains the chat interface.
    FileResponse efficiently serves the file with proper caching headers.
    
    Returns:
        FileResponse: The main HTML page
    """
    return FileResponse('static/index.html')


@app.post("/api/chat")
async def chat(
    message: str = Form(...),           # Required form field for the chat message
    file: UploadFile = File(None)       # Optional file upload
):
    """
    Main chat endpoint with file upload support.
    
    This endpoint accepts multipart/form-data requests containing:
    - message: The user's text message (required)
    - file: An optional file attachment (images, PDFs, etc.)
    
    The response is a streaming NDJSON (Newline Delimited JSON) format,
    where each line is a complete JSON object representing an event:
    
    Event Types:
    ------------
    {"type": "message", "content": "..."} 
        - Text response from the agent
        
    {"type": "tool_call", "name": "...", "arguments": {...}}
        - The agent is calling a tool
        
    {"type": "tool_result", "name": "...", "content": "...", "is_error": bool}
        - Result from tool execution
        
    {"type": "error", "content": "..."}
        - An error occurred
    
    Args:
        message: The user's chat message text
        file: Optional uploaded file (UploadFile from FastAPI)
    
    Returns:
        StreamingResponse: NDJSON stream of agent events
    
    Raises:
        HTTPException: 500 if the agent is not initialized
    
    Example Request:
    ---------------
        curl -X POST "http://localhost:5000/api/chat" \
             -F "message=Find flights from NYC to London" \
             -F "file=@document.pdf"
    
    Example Response (NDJSON stream):
    ---------------------------------
        {"type": "message", "content": "I'll search for flights..."}
        {"type": "tool_call", "name": "search_flights", "arguments": {"origin": "NYC", "destination": "LHR", "date": "2024-03-15"}}
        {"type": "tool_result", "name": "search_flights", "content": "[{flight data}]", "is_error": false}
        {"type": "message", "content": "I found 3 flights..."}
    """
    # Ensure the agent is initialized
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    # Process file upload if present
    file_data = None
    mime_type = None
    
    if file:
        # Read the entire file content into memory
        # Note: For large files, consider streaming to disk
        content = await file.read()
        file_data = content
        mime_type = file.content_type
        logger.info(f"Received file: {file.filename} ({mime_type}, {len(content)} bytes)")

    # Define an async generator to stream events to the client
    # This allows the UI to update in real-time as the agent thinks and acts
    async def event_generator() -> AsyncGenerator[str, None]:
        """
        Async generator that yields NDJSON events from the agent.
        
        Each event is JSON-encoded and terminated with a newline,
        following the NDJSON (Newline Delimited JSON) format.
        This format is easy to parse incrementally on the client side.
        """
        # Pass file data to run_generator for analysis
        async for event in agent.run_generator(message, file_data=file_data, mime_type=mime_type):
            # Format each event as a JSON line (NDJSON format)
            # The \n newline allows clients to easily split the stream
            yield json.dumps(event) + "\n"

    # Return a StreamingResponse to keep the connection open
    # media_type="application/x-ndjson" indicates NDJSON format to clients
    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    # Start the uvicorn ASGI server when running the script directly.
    # 
    # Parameters:
    # - "web_server:app": Module:app format for uvicorn to find the FastAPI app
    # - host="0.0.0.0": Listen on all network interfaces (not just localhost)
    # - port=5000: Port to listen on
    # - reload=True: Auto-reload on code changes (development mode)
    #
    # In production, run with:
    #   uvicorn web_server:app --host 0.0.0.0 --port 5000 --workers 4
    uvicorn.run("web_server:app", host="0.0.0.0", port=5000, reload=True)
