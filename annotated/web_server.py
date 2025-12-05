import os
import sys
import json
import logging
import asyncio
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Add project root to path so we can import modules from 'travel_agent'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env file
load_dotenv()

# Import our custom modules
from travel_agent.config import Config
from travel_agent.agent.llm import get_llm_provider
from travel_agent.mcp.mcp_server import MCPServer
from travel_agent.agent.orchestrator import AgentOrchestrator
from travel_agent.tools import (
    search_flights, 
    book_flight, 
    rent_car, 
    get_forecast, 
    process_payment,
    get_current_datetime
)

# Configure Logging
# We use standard logging to track the server's lifecycle and errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Mount static files
# This serves the HTML/CSS/JS files from the 'static' directory at the /static URL path
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS (Cross-Origin Resource Sharing) middleware
# This is permissive by default ("*") to allow development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variable to store the initialized AgentOrchestrator instance
# This allows us to reuse the same agent (and its memory/state) across requests if needed,
# though currently we create a new conversation context per request logically,
# the tools and configuration are loaded once.
agent = None

async def initialize_agent():
    """
    Asynchronous initialization of the Agent.
    This handles loading API keys, connecting to the LLM provider,
    and registering all available tools with the MCP server.
    """
    global agent
    
    # 1. Validate critical configuration (like presence of .env)
    if not Config.validate(): 
        logger.error("Config validation failed.")
        return False
    
    # 2. Determine LLM Provider from environment variables (default to Anthropic)
    provider_name = os.getenv("LLM_PROVIDER", "ANTHROPIC").lower()
    api_key = None
    
    # Logic to find the first valid API key if the preferred one is missing
    provider_map = {
        "anthropic": Config.ANTHROPIC_API_KEY,
        "openai": Config.OPENAI_API_KEY,
        "google": Config.GOOGLE_API_KEY,
    }

    if provider_name in provider_map and provider_map[provider_name]:
        api_key = provider_map[provider_name]
        
    if not api_key:
        logger.warning(
            f"API key for preferred provider ({provider_name.upper()}) is missing. searching fallback..."
        )
        for name, key in provider_map.items():
            if key:
                provider_name = name
                api_key = key
                logger.info(f"Found valid key for fallback provider: {provider_name.upper()}")
                break 

    if not api_key:
        logger.error("No valid LLM API key found.")
        return False

    try:
        # 3. Initialize the Low-Level Model (LLM) Provider
        # get_llm_provider returns an async wrapper around the specific vendor's SDK
        llm = get_llm_provider(provider_name, api_key)
    except ImportError as e:
        logger.error(f"Error initializing LLM: {e}")
        return False

    # 4. Initialize MCP (Model Context Protocol) Server
    # The server manages the tools and helps the LLM understand how to call them.
    server = MCPServer()
    
    # Register all tools using the simple function-based registration
    # The MCPServer inspects these functions' type hints to generate JSON schemas automatically
    server.register_tool(search_flights)
    server.register_tool(book_flight)
    server.register_tool(rent_car)
    server.register_tool(get_forecast)
    server.register_tool(process_payment)
    server.register_tool(get_current_datetime)

    # 5. Create the Orchestrator
    # The orchestrator binds the LLM and the Tools together, managing the thought loop
    agent = AgentOrchestrator(llm, server)
    logger.info(f"Agent initialized successfully with: {provider_name.upper()}")
    return True

@app.on_event("startup")
async def startup_event():
    """
    FastAPI startup event.
    Runs once when the server starts. We use this to initialize the agent asynchronously.
    If initialization fails (e.g., no API keys), we set up a Mock Agent for UI testing purposes.
    """
    success = await initialize_agent()
    if not success:
        logger.warning("Agent initialization failed. Using Mock Agent for UI testing.")
        
        # Define a simpler Mock Agent that just echoes messages
        class MockAgent:
            async def run_generator(self, user_input, request_id="mock"):
                yield {"type": "message", "content": f"I received your message: '{user_input}'. (Mock Agent)"}
                yield {"type": "tool_call", "name": "mock_tool", "arguments": {"query": "test"}}
                await asyncio.sleep(1)
                yield {"type": "tool_result", "name": "mock_tool", "content": "Mock result", "is_error": False}
                yield {"type": "message", "content": "This is a mock response because API keys are missing."}

        global agent
        agent = MockAgent()

@app.get("/")
async def index():
    """Serve the single-page application entry point."""
    return FileResponse('static/index.html')

@app.post("/api/chat")
async def chat(request: Request):
    """
    Main Chat Endpoint.
    Receives a JSON payload with the user's message, and streams back the agent's events.
    """
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
        
    user_input = data.get('message')
    
    if not user_input:
        raise HTTPException(status_code=400, detail="No message provided")

    # Define an async generator to stream events to the client
    # This allows the UI to update in real-time as the agent thinks and acts
    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in agent.run_generator(user_input):
            # We explicitly format as NDJSON (Newline Delimited JSON)
            # Each line is a complete JSON object representing an event (message, tool_call, etc.)
            yield json.dumps(event) + "\n"

    # Return a StreamingResponse to keep the connection open
    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

if __name__ == "__main__":
    # Start the server using Uvicorn
    # 'web_server:app' refers to the 'app' object in this file ('web_server.py')
    uvicorn.run("web_server:app", host="0.0.0.0", port=5000, reload=True)
