import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration management for the Travel Agent."""
    
    # LLM Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    
    # Service Keys
    FLIGHT_API_KEY = os.getenv("FLIGHT_API_KEY")
    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
    
    @classmethod
    def validate(cls):
        """Check for missing critical keys."""
        missing = []
        if not cls.OPENAI_API_KEY and not cls.ANTHROPIC_API_KEY and not cls.GOOGLE_API_KEY:
            missing.append("At least one LLM API Key (OpenAI, Anthropic, or Google)")
            
        if missing:
            print(f"Warning: Missing keys: {', '.join(missing)}")
            print("Please create a .env file based on .env.example")
            return False
        return True
