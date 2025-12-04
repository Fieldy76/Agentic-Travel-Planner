import os
import sys

# Add project root to path
# This ensures that we can import modules from the project root directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Load environment variables
# This is crucial for loading API keys from the .env file when running from CLI
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
    process_payment
)

def main():
    # 1. Validate Config
    # Ensure that all necessary API keys are present
    if not Config.validate():
        return

    # 2. Select LLM Provider
    # Default to OpenAI, but can be changed via env or args
    provider_name = os.getenv("LLM_PROVIDER", "openai")
    api_key = ""
    
    # Determine which API key to use based on the selected provider
    if provider_name == "openai":
        api_key = Config.OPENAI_API_KEY
    elif provider_name == "anthropic":
        api_key = Config.ANTHROPIC_API_KEY
    elif provider_name == "google":
        api_key = Config.GOOGLE_API_KEY
        
    if not api_key:
        print(f"Error: API Key for {provider_name} is missing.")
        return

    try:
        # Initialize the LLM provider wrapper
        llm = get_llm_provider(provider_name, api_key)
    except ImportError as e:
        print(f"Error initializing LLM: {e}")
        return

    # 3. Setup MCP Server and Register Tools
    # Create the Model Context Protocol server instance
    server = MCPServer()
    # Register all available tools with the server
    server.register_tool(search_flights)
    server.register_tool(book_flight)
    server.register_tool(rent_car)
    server.register_tool(get_forecast)
    server.register_tool(process_payment)

    # 4. Initialize Agent
    # Create the agent orchestrator with the LLM and the tool server
    agent = AgentOrchestrator(llm, server)

    print(f"Travel Agent initialized with {provider_name}. Ready to help!")
    print("Type 'quit' to exit.")

    # 5. Interaction Loop
    # Start the main chat loop
    while True:
        try:
            user_input = input("\nYou: ")
            if user_input.lower() in ["quit", "exit"]:
                break
                
            # Run the agent with the user's input
            agent.run(user_input)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
