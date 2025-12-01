import os  # Import the os module to interact with the operating system
import sys  # Import the sys module to access system-specific parameters and functions

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # Add the parent directory of the current file to the system path to allow importing modules from the project root

from travel_agent.config import Config  # Import the Config class from the travel_agent.config module
from travel_agent.agent.llm import get_llm_provider  # Import the get_llm_provider function from the travel_agent.agent.llm module
from travel_agent.mcp.server import MCPServer  # Import the MCPServer class from the travel_agent.mcp.server module
from travel_agent.agent.orchestrator import AgentOrchestrator  # Import the AgentOrchestrator class from the travel_agent.agent.orchestrator module
from travel_agent.tools import (  # Import specific tool functions from the travel_agent.tools module
    search_flights,  # Import the search_flights function
    book_flight,  # Import the book_flight function
    rent_car,  # Import the rent_car function
    get_forecast,  # Import the get_forecast function
    process_payment  # Import the process_payment function
)

def main():  # Define the main function of the script
    # 1. Validate Config
    if not Config.validate():  # Check if the configuration is valid using the validate method of the Config class
        return  # Exit the function if configuration is invalid

    # 2. Select LLM Provider
    # Default to OpenAI, but can be changed via env or args
    provider_name = os.getenv("LLM_PROVIDER", "openai")  # Get the LLM provider name from environment variables, defaulting to "openai"
    api_key = ""  # Initialize the api_key variable
    
    if provider_name == "openai":  # Check if the provider is OpenAI
        api_key = Config.OPENAI_API_KEY  # Set the API key from the Config class for OpenAI
    elif provider_name == "anthropic":  # Check if the provider is Anthropic
        api_key = Config.ANTHROPIC_API_KEY  # Set the API key from the Config class for Anthropic
    elif provider_name == "google":  # Check if the provider is Google
        api_key = Config.GOOGLE_API_KEY  # Set the API key from the Config class for Google
        
    if not api_key:  # Check if the API key is missing
        print(f"Error: API Key for {provider_name} is missing.")  # Print an error message indicating the missing API key
        return  # Exit the function

    try:  # Start a try block to handle potential errors during LLM initialization
        llm = get_llm_provider(provider_name, api_key)  # Initialize the LLM provider using the factory function
    except ImportError as e:  # Catch ImportError if the SDK is not installed
        print(f"Error initializing LLM: {e}")  # Print the error message
        return  # Exit the function

    # 3. Setup MCP Server and Register Tools
    server = MCPServer()  # Create an instance of the MCPServer
    server.register_tool(search_flights)  # Register the search_flights tool with the server
    server.register_tool(book_flight)  # Register the book_flight tool with the server
    server.register_tool(rent_car)  # Register the rent_car tool with the server
    server.register_tool(get_forecast)  # Register the get_forecast tool with the server
    server.register_tool(process_payment)  # Register the process_payment tool with the server

    # 4. Initialize Agent
    agent = AgentOrchestrator(llm, server)  # Create an instance of the AgentOrchestrator with the LLM and server

    print(f"Travel Agent initialized with {provider_name}. Ready to help!")  # Print a success message indicating the agent is ready
    print("Type 'quit' to exit.")  # Print instructions on how to exit the application

    # 5. Interaction Loop
    while True:  # Start an infinite loop to handle user interaction
        try:  # Start a try block to handle potential errors during execution
            user_input = input("\nYou: ")  # Prompt the user for input
            if user_input.lower() in ["quit", "exit"]:  # Check if the user wants to quit or exit
                break  # Break the loop to exit the application
                
            agent.run(user_input)  # Run the agent with the user's input
            
        except KeyboardInterrupt:  # Catch KeyboardInterrupt (Ctrl+C)
            break  # Break the loop to exit
        except Exception as e:  # Catch any other exceptions
            print(f"An error occurred: {e}")  # Print the error message

if __name__ == "__main__":  # Check if the script is being run directly
    main()  # Call the main function
