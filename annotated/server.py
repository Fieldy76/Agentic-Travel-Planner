import os  # Import the os module for operating system dependent functionality
import sys  # Import the sys module for system-specific parameters and functions
import json  # Import the json module for JSON serialization and deserialization
import logging  # Import the logging module for tracking events
from flask import Flask, request, jsonify, Response, send_from_directory  # Import Flask components for web server creation
from dotenv import load_dotenv  # Import load_dotenv to load environment variables from a .env file

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))  # Append the current directory to sys.path to ensure local modules can be imported

from travel_agent.config import Config  # Import the Config class for application configuration
from travel_agent.agent.llm import get_llm_provider  # Import helper to get the LLM provider instance
from travel_agent.mcp.server import MCPServer  # Import the MCPServer class for tool management
from travel_agent.agent.orchestrator import AgentOrchestrator  # Import the AgentOrchestrator class for managing the agent loop
from travel_agent.tools import (  # Import the available tools for the agent
    search_flights, 
    book_flight, 
    rent_car, 
    get_forecast, 
    process_payment
)

# Load environment variables
load_dotenv()  # Load environment variables from the .env file into os.environ

app = Flask(__name__, static_folder='static')  # Initialize the Flask application, specifying the static folder
logging.basicConfig(level=logging.INFO)  # Configure the logging system to show INFO level logs
logger = logging.getLogger(__name__)  # Get a logger instance for this module

# Initialize Agent Global Variable
agent = None  # Define a global variable to hold the initialized agent instance

def initialize_agent():
    """
    Initializes the agent, LLM provider, and MCP server.
    Returns True if successful, False otherwise.
    """
    global agent  # Access the global agent variable
    if not Config.validate():  # Validate the configuration (check for required API keys)
        logger.error("Config validation failed")  # Log an error if validation fails
        return False  # Return False to indicate failure

    provider_name = os.getenv("LLM_PROVIDER", "openai")  # Get the LLM provider name from env, default to 'openai'
    api_key = ""  # Initialize api_key variable
    
    # Select the appropriate API key based on the provider
    if provider_name == "openai":
        api_key = Config.OPENAI_API_KEY
    elif provider_name == "anthropic":
        api_key = Config.ANTHROPIC_API_KEY
    elif provider_name == "google":
        api_key = Config.GOOGLE_API_KEY
        
    if not api_key:  # Check if the API key was found
        logger.error(f"API Key for {provider_name} is missing.")  # Log an error if missing
        return False  # Return False to indicate failure

    try:
        llm = get_llm_provider(provider_name, api_key)  # Initialize the LLM provider with the key
    except ImportError as e:  # Catch ImportError if the provider's library is missing
        logger.error(f"Error initializing LLM: {e}")  # Log the error
        return False  # Return False to indicate failure

    server = MCPServer()  # Initialize the MCP Server
    # Register the available tools with the server
    server.register_tool(search_flights)
    server.register_tool(book_flight)
    server.register_tool(rent_car)
    server.register_tool(get_forecast)
    server.register_tool(process_payment)

    agent = AgentOrchestrator(llm, server)  # Initialize the AgentOrchestrator with the LLM and Server
    logger.info(f"Agent initialized with {provider_name}")  # Log success message
    return True  # Return True to indicate success

@app.route('/')
def index():
    """
    Route handler for the root URL ('/').
    Serves the index.html file from the static directory.
    """
    return send_from_directory('static', 'index.html')  # Send the index.html file to the client

@app.route('/<path:path>')
def serve_static(path):
    """
    Route handler for static files.
    Serves any file requested from the static directory.
    """
    return send_from_directory('static', path)  # Send the requested file from the static directory

@app.route('/api/chat', methods=['POST'])
def chat():
    """
    API endpoint for chat interactions.
    Expects a JSON payload with a 'message' key.
    Streams the agent's response as NDJSON (Newline Delimited JSON).
    """
    if not agent:  # Check if the agent is initialized
        return jsonify({"error": "Agent not initialized"}), 500  # Return 500 error if not initialized
    
    data = request.json  # Get the JSON data from the request
    user_input = data.get('message')  # Extract the user's message
    
    if not user_input:  # Check if the message is empty
        return jsonify({"error": "No message provided"}), 400  # Return 400 error if message is missing

    def generate():
        """
        Generator function to stream events from the agent.
        """
        # Iterate over events yielded by the agent's run_generator method
        for event in agent.run_generator(user_input):
            yield json.dumps(event) + "\n"  # Yield each event as a JSON string followed by a newline

    # Return a streaming response with the correct MIME type for NDJSON
    return Response(generate(), mimetype='application/x-ndjson')

if __name__ == '__main__':
    # Main execution block
    if not initialize_agent():  # Attempt to initialize the agent
        logger.warning("Agent initialization failed. Using Mock Agent for UI testing.")  # Log warning if initialization fails
        
        # Define a MockAgent class for testing UI without API keys
        class MockAgent:
            def run_generator(self, user_input, request_id="mock"):
                # Simulate receiving a message
                yield {"type": "message", "content": f"I received your message: '{user_input}'. (Mock Agent)"}
                # Simulate a tool call
                yield {"type": "tool_call", "name": "mock_tool", "arguments": {"query": "test"}}
                import time
                time.sleep(1)  # Simulate processing time
                # Simulate a tool result
                yield {"type": "tool_result", "name": "mock_tool", "content": "Mock result", "is_error": False}
                # Simulate a final response
                yield {"type": "message", "content": "This is a mock response because API keys are missing."}

        agent = MockAgent()  # Use the MockAgent instance

    app.run(debug=True, port=5000)  # Start the Flask development server on port 5000
