import os  # Import the os module to interact with the operating system
from dotenv import load_dotenv  # Import the load_dotenv function from the dotenv module to load environment variables from a .env file

# Load environment variables from .env file
load_dotenv()  # Execute the load_dotenv function to read the .env file and set environment variables

class Config:  # Define the Config class for configuration management
    """Configuration management for the Travel Agent."""  # Docstring for the Config class
    
    # LLM Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Retrieve the OpenAI API key from environment variables
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # Retrieve the Anthropic API key from environment variables
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # Retrieve the Google API key from environment variables
    
    # Service Keys
    FLIGHT_API_KEY = os.getenv("FLIGHT_API_KEY")  # Retrieve the Flight API key from environment variables
    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")  # Retrieve the Weather API key from environment variables
    
    @classmethod  # Decorator to define a class method
    def validate(cls):  # Define the validate method to check for missing keys
        """Check for missing critical keys."""  # Docstring for the validate method
        missing = []  # Initialize an empty list to store missing key names
        if not cls.OPENAI_API_KEY and not cls.ANTHROPIC_API_KEY and not cls.GOOGLE_API_KEY:  # Check if all LLM API keys are missing
            missing.append("At least one LLM API Key (OpenAI, Anthropic, or Google)")  # Add a message to the missing list
            
        if missing:  # Check if there are any missing keys
            print(f"Warning: Missing keys: {', '.join(missing)}")  # Print a warning message with the missing keys
            print("Please create a .env file based on .env.example")  # Print instructions to create a .env file
            return False  # Return False indicating validation failed
        return True  # Return True indicating validation succeeded
