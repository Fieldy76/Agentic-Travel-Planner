import os
import sys
import json
import logging
import asyncio
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Add project root to path ensuring python can find travel_agent package
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env
load_dotenv()

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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static files to serve HTML/JS/CSS frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS to allow frontend requests (even if served from same origin, good practice)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Agent Global Variable
agent = None

async def initialize_agent():
    """
    Asynchronous Agent Initialization.
    Handles loading credentials, fallback strategies, and tool registration.
    """
    global agent
    
    if not Config.validate(): 
        logger.error("Config validation failed.")
        return False
    
    # Get provider preference (default: Anthropic)
    provider_name = os.getenv("LLM_PROVIDER", "ANTHROPIC").lower()
    api_key = None
    
    provider_map = {
        "anthropic": Config.ANTHROPIC_API_KEY,
        "openai": Config.OPENAI_API_KEY,
        "google": Config.GOOGLE_API_KEY,
    }

    if provider_name in provider_map and provider_map[provider_name]:
        api_key = provider_map[provider_name]
        
    # Fallback Strategy: If preferred provider key is missing, search others
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
        # Initialize LLM Provider (Async)
        llm = get_llm_provider(provider_name, api_key)
    except ImportError as e:
        logger.error(f"Error initializing LLM: {e}")
        return False

    # Initialize MCP Server
    # This server acts as a bridge between the LLM and the Python functions (tools)
    server = MCPServer()
    server.register_tool(search_flights)
    server.register_tool(book_flight)
    server.register_tool(rent_car)
    server.register_tool(get_forecast)
    server.register_tool(process_payment)
    server.register_tool(get_current_datetime)

    # Initialize Orchestrator which manages the thought loop
    agent = AgentOrchestrator(llm, server)
    logger.info(f"Agent initialized successfully with: {provider_name.upper()}")
    return True

@app.on_event("startup")
async def startup_event():
    success = await initialize_agent()
    # Mock Agent Fallback for UI testing without API keys
    if not success:
        logger.warning("Agent initialization failed. Using Mock Agent for UI testing.")
        
        class MockAgent:
            async def run_generator(self, user_input, file_data=None, mime_type=None, request_id="mock"):
                yield {"type": "message", "content": f"I received your message: '{user_input}'. (Mock Agent)"}
                if file_data:
                     yield {"type": "message", "content": f"I also received a file: {len(file_data)} bytes."}
                yield {"type": "tool_call", "name": "mock_tool", "arguments": {"query": "test"}}
                await asyncio.sleep(1)
                yield {"type": "tool_result", "name": "mock_tool", "content": "Mock result", "is_error": False}
                yield {"type": "message", "content": "This is a mock response because API keys are missing."}

        global agent
        agent = MockAgent()

@app.get("/")
async def index():
    # Serve the main Single Page Application (SPA)
    return FileResponse('static/index.html')

@app.post("/api/chat")
async def chat(
    message: str = Form(...),
    file: UploadFile = File(None)
):
    """
    Main Chat Endpoint with File Upload Support.
    Accepts multipart/form-data requests to handle both text messages and file attachments.
    """
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    file_data = None
    mime_type = None
    
    # Handle File Upload
    # We read the file into memory to pass it to the agent/LLM
    if file:
        content = await file.read()
        file_data = content
        mime_type = file.content_type
        logger.info(f"Received file: {file.filename} ({mime_type}, {len(content)} bytes)")

    # Define an async generator to stream events to the client
    # Using Server-Sent Events (SSE) / NDJSON pattern for real-time UI updates
    async def event_generator() -> AsyncGenerator[str, None]:
        # Pass user input and optional file data to the orchestrator
        async for event in agent.run_generator(message, file_data=file_data, mime_type=mime_type):
            # We explicitly format as NDJSON (Newline Delimited JSON)
            # Each line corresponds to a distinct event (thinking, tool call, final answer)
            yield json.dumps(event) + "\n"

    # Return a StreamingResponse to keep the connection open
    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

if __name__ == "__main__":
    uvicorn.run("web_server:app", host="0.0.0.0", port=5000, reload=True)
