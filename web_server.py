import os
import sys
import json
import logging
from flask import Flask, request, jsonify, Response, send_from_directory
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from travel_agent.config import Config
from travel_agent.agent.llm import get_llm_provider
from travel_agent.mcp.mcp_server import MCPServer
from travel_agent.agent.orchestrator import AgentOrchestrator
from travel_agent.tools import (
    search_flights, 
    book_flight, 
    rent_car, 
    get_forecast, 
    process_payment
)

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Agent Global Variable
agent = None

def initialize_agent():
    global agent
    if not Config.validate():
        logger.error("Config validation failed")
        return False

    provider_name = os.getenv("LLM_PROVIDER", "openai")
    api_key = ""
    
    if provider_name == "openai":
        api_key = Config.OPENAI_API_KEY
    elif provider_name == "anthropic":
        api_key = Config.ANTHROPIC_API_KEY
    elif provider_name == "google":
        api_key = Config.GOOGLE_API_KEY
        
    if not api_key:
        logger.error(f"API Key for {provider_name} is missing.")
        return False

    try:
        llm = get_llm_provider(provider_name, api_key)
    except ImportError as e:
        logger.error(f"Error initializing LLM: {e}")
        return False

    server = MCPServer()
    server.register_tool(search_flights)
    server.register_tool(book_flight)
    server.register_tool(rent_car)
    server.register_tool(get_forecast)
    server.register_tool(process_payment)

    agent = AgentOrchestrator(llm, server)
    logger.info(f"Agent initialized with {provider_name}")
    return True

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

@app.route('/api/chat', methods=['POST'])
def chat():
    if not agent:
        return jsonify({"error": "Agent not initialized"}), 500
    
    data = request.json
    user_input = data.get('message')
    
    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    def generate():
        for event in agent.run_generator(user_input):
            yield json.dumps(event) + "\n"

    return Response(generate(), mimetype='application/x-ndjson')

if __name__ == '__main__':
    if not initialize_agent():
        logger.warning("Agent initialization failed. Using Mock Agent for UI testing.")
        
        class MockAgent:
            def run_generator(self, user_input, request_id="mock"):
                yield {"type": "message", "content": f"I received your message: '{user_input}'. (Mock Agent)"}
                yield {"type": "tool_call", "name": "mock_tool", "arguments": {"query": "test"}}
                import time
                time.sleep(1)
                yield {"type": "tool_result", "name": "mock_tool", "content": "Mock result", "is_error": False}
                yield {"type": "message", "content": "This is a mock response because API keys are missing."}

        agent = MockAgent()

    app.run(debug=True, port=5000)
