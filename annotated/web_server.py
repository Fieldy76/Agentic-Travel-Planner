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

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables
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

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS
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
    global agent
    
    if not Config.validate(): 
        logger.error("Config validation failed.")
        return False
    
    provider_name = os.getenv("LLM_PROVIDER", "ANTHROPIC").lower()
    api_key = None
    
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
        # LLM Provider is now Async
        llm = get_llm_provider(provider_name, api_key)
    except ImportError as e:
        logger.error(f"Error initializing LLM: {e}")
        return False

    # MCP Server (now supports async tools)
    server = MCPServer()
    server.register_tool(search_flights)
    server.register_tool(book_flight)
    server.register_tool(rent_car)
    server.register_tool(get_forecast)
    server.register_tool(process_payment)
    server.register_tool(get_current_datetime)

    agent = AgentOrchestrator(llm, server)
    logger.info(f"Agent initialized successfully with: {provider_name.upper()}")
    return True

@app.on_event("startup")
async def startup_event():
    success = await initialize_agent()
    if not success:
        logger.warning("Agent initialization failed. Using Mock Agent for UI testing.")
        
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
    return FileResponse('static/index.html')

@app.post("/api/chat")
async def chat(request: Request):
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        data = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
        
    user_input = data.get('message')
    
    if not user_input:
        raise HTTPException(status_code=400, detail="No message provided")

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in agent.run_generator(user_input):
            # Format as Server-Sent Event (SSE) or just NDJSON
            # The current frontend expects NDJSON (json line by line)
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

if __name__ == "__main__":
    uvicorn.run("web_server:app", host="0.0.0.0", port=5000, reload=True)
