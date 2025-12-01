# Import the os module to access environment variables
import os
# Import load_dotenv to load variables from .env file
from dotenv import load_dotenv
# Import json for use in logging formatter
import json

# Load environment variables from .env file into os.environ
# This allows us to keep sensitive API keys out of version control
load_dotenv()

# Configuration class to centralize all application settings
class Config:
    """Configuration management for the Travel Agent."""
    
    # LLM API Keys - we support multiple providers for flexibility
    # Users need at least one of these to use the agent
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    
    # Service API Keys for external tool integrations
    # These are optional - if missing, tools will use mock data
    FLIGHT_API_KEY = os.getenv("FLIGHT_API_KEY")
    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
    
    @classmethod
    def validate(cls):
        """Check for missing critical keys."""
        # Initialize list to track missing required keys
        missing = []
        
        # Check if at least ONE LLM provider key exists
        # The agent needs an LLM to function, but can use any of the three providers
        if not cls.OPENAI_API_KEY and not cls.ANTHROPIC_API_KEY and not cls.GOOGLE_API_KEY:
            missing.append("At least one LLM API Key (OpenAI, Anthropic, or Google)")
        
        # If any critical keys are missing, warn the user    
        if missing:
            print(f"Warning: Missing keys: {', '.join(missing)}")
            print("Please create a .env file based on .env.example")
            return False
        return True

def setup_logging(level="INFO"):
    """Configure structured JSON logging for production observability."""
    # Import logging library for application logging
    import logging
    # Import sys to get stdout stream
    import sys
    
    # Create a handler that writes log records to stdout
    # This allows container orchestrators (Docker, Kubernetes) to capture logs
    handler = logging.StreamHandler(sys.stdout)
    
    # Define custom formatter to output logs as JSON
    # JSON logs are machine-readable and easier to parse in log aggregation systems
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            # Build a structured log record dictionary
            log_record = {
                "timestamp": self.formatTime(record, self.datefmt),  # When the event occurred
                "level": record.levelname,  # Severity: DEBUG, INFO, WARNING, ERROR, CRITICAL
                "message": record.getMessage(),  # The log message
                "module": record.module,  # Which Python module generated the log
                "function": record.funcName,  # Which function generated the log
            }
            # If a request_id was set (for request tracing), include it
            # This allows correlating all logs from a single user request
            if hasattr(record, "request_id"):
                log_record["request_id"] = record.request_id
            # Return the log record as a JSON string
            return json.dumps(log_record)

    # Attach our custom JSON formatter to the handler
    handler.setFormatter(JsonFormatter())
    
    # Get the root logger (affects all loggers in the application)
    root = logging.getLogger()
    # Set the logging level (e.g., INFO means DEBUG messages won't be shown)
    root.setLevel(level)
    
    # Remove existing handlers to avoid duplicate log entries
    # This is important if setup_logging() is called multiple times
    if root.handlers:
        for h in root.handlers:
            root.removeHandler(h)
    
    # Add our configured handler to the root logger
    root.addHandler(handler)
