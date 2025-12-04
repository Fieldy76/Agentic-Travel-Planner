import os
from dotenv import load_dotenv
import json
from pathlib import Path

# Load environment variables from .env file in project root
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

class Config:
    """Configuration management for the Travel Agent."""
    
    # LLM Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    
    # Service Keys
    FLIGHT_API_KEY = os.getenv("FLIGHT_API_KEY")
    FLIGHT_API_SECRET = os.getenv("FLIGHT_API_SECRET")  # Required for Amadeus OAuth
    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
    
    # Payment Processing (Stripe)
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
    
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

def setup_logging(level="INFO"):
    """Configure structured JSON logging."""
    import logging
    import sys
    
    # Create a handler that writes to stdout
    handler = logging.StreamHandler(sys.stdout)
    
    # Use a custom formatter for JSON output
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_record = {
                "timestamp": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
            }
            if hasattr(record, "request_id"):
                log_record["request_id"] = record.request_id
            return json.dumps(log_record)

    handler.setFormatter(JsonFormatter())
    
    # Configure root logger
    root = logging.getLogger()
    root.setLevel(level)
    # Remove existing handlers to avoid duplication
    if root.handlers:
        for h in root.handlers:
            root.removeHandler(h)
    root.addHandler(handler)
