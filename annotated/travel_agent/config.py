"""
================================================================================
CONFIGURATION MODULE - Centralized Configuration Management
================================================================================

This module provides centralized configuration management for the Agentic 
Travel Planner application. It handles loading environment variables, 
validating required API keys, and configuring structured JSON logging.

Design Philosophy:
------------------
1. Single Source of Truth: All configuration values are accessed through 
   the Config class, avoiding scattered os.getenv() calls throughout the code.

2. Early Validation: The validate() method can be called at startup to 
   ensure all required API keys are present before processing requests.

3. Fail-Fast: Missing critical configuration is detected early, with clear
   error messages to guide developers.

4. Structured Logging: The setup_logging() function configures JSON-formatted
   logs for easy parsing in production log aggregation systems.

Environment Variables:
----------------------
LLM API Keys (at least one required):
    OPENAI_API_KEY      - OpenAI API key for GPT models
    ANTHROPIC_API_KEY   - Anthropic API key for Claude models  
    GOOGLE_API_KEY      - Google API key for Gemini models

Service API Keys (optional, will use mock data if missing):
    FLIGHT_API_KEY      - Amadeus API key for flight search
    FLIGHT_API_SECRET   - Amadeus API secret (required for OAuth)
    WEATHER_API_KEY     - Open-Meteo API URL or key

Payment Processing (optional, will use mock if missing):
    STRIPE_SECRET_KEY       - Stripe secret key for server-side operations
    STRIPE_PUBLISHABLE_KEY  - Stripe publishable key for client-side
    STRIPE_WEBHOOK_SECRET   - Stripe webhook signing secret

Configuration Files:
--------------------
    .env         - Local environment variables (git-ignored)
    .env.example - Template showing required variables (committed)

Usage:
------
    from travel_agent.config import Config, setup_logging
    
    # Setup logging at application start
    setup_logging(level="INFO")
    
    # Validate configuration
    if not Config.validate():
        print("Missing required configuration!")
        sys.exit(1)
    
    # Access configuration values
    api_key = Config.OPENAI_API_KEY

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import os                  # Operating system interface for environment variables
from dotenv import load_dotenv  # Load .env files into environment
import json                # JSON serialization for structured logging
from pathlib import Path   # Modern path handling (cross-platform)

# =============================================================================
# ENVIRONMENT LOADING
# =============================================================================

# Calculate the project root directory.
# __file__ is the path to this config.py file.
# .resolve() converts to absolute path, .parent.parent goes up two levels:
#   travel_agent/config.py -> travel_agent/ -> project_root/
_project_root = Path(__file__).resolve().parent.parent

# Load environment variables from the .env file in the project root.
# This makes all variables in .env available via os.getenv().
# If .env doesn't exist, this silently does nothing (no error).
load_dotenv(_project_root / ".env")

# =============================================================================
# CONFIGURATION CLASS
# =============================================================================

class Config:
    """
    Configuration management class for the Travel Agent application.
    
    This class uses class-level attributes to store configuration values,
    making them accessible without instantiation (Config.OPENAI_API_KEY).
    
    All values are loaded at class definition time from environment variables.
    This happens once when the module is imported.
    
    Attributes:
    -----------
    LLM API Keys:
        OPENAI_API_KEY (str | None): OpenAI API key for GPT models
        ANTHROPIC_API_KEY (str | None): Anthropic API key for Claude
        GOOGLE_API_KEY (str | None): Google API key for Gemini
    
    Service API Keys:
        FLIGHT_API_KEY (str | None): Amadeus client ID
        FLIGHT_API_SECRET (str | None): Amadeus client secret
        WEATHER_API_KEY (str | None): Weather API endpoint/key
    
    Payment Keys:
        STRIPE_SECRET_KEY (str | None): Stripe server-side key
        STRIPE_PUBLISHABLE_KEY (str | None): Stripe client-side key
        STRIPE_WEBHOOK_SECRET (str | None): Stripe webhook verification
    
    Methods:
    --------
    validate(): Check for required configuration and report missing items.
    
    Example:
    --------
        >>> Config.validate()
        True  # All required keys present
        
        >>> Config.OPENAI_API_KEY
        'sk-...'  # The actual API key value
    """
    
    # -------------------------------------------------------------------------
    # LLM Provider API Keys
    # -------------------------------------------------------------------------
    # At least ONE of these is required for the agent to function.
    # The application will try the preferred provider first, then fall back.
    
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    """OpenAI API key - Required for GPT-4o and other OpenAI models."""
    
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    """Anthropic API key - Required for Claude models."""
    
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    """Google API key - Required for Gemini models."""
    
    # -------------------------------------------------------------------------
    # External Service API Keys
    # -------------------------------------------------------------------------
    # These are optional - if missing, the tools will use mock/simulated data.
    # This allows development and testing without requiring all API keys.
    
    FLIGHT_API_KEY = os.getenv("FLIGHT_API_KEY")
    """Amadeus API client ID - For real flight search functionality."""
    
    FLIGHT_API_SECRET = os.getenv("FLIGHT_API_SECRET")
    """Amadeus API client secret - Required for OAuth2 token generation."""
    
    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
    """Weather API URL/key - For real weather forecasts (Open-Meteo)."""
    
    # -------------------------------------------------------------------------
    # Payment Processing (Stripe)
    # -------------------------------------------------------------------------
    # Optional - if missing, payments will be simulated in mock mode.
    # For production, all three Stripe keys should be configured.
    
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    """
    Stripe secret key (starts with 'sk_').
    Used for server-side API calls to create Payment Intents, charge cards, etc.
    NEVER expose this key to the client/frontend.
    """
    
    STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
    """
    Stripe publishable key (starts with 'pk_').
    Safe to include in client-side code for Stripe.js integration.
    """
    
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
    """
    Stripe webhook signing secret (starts with 'whsec_').
    Used to verify that webhook events actually came from Stripe.
    """
    
    # -------------------------------------------------------------------------
    # Langfuse Observability (Optional)
    # -------------------------------------------------------------------------
    # Langfuse provides LLM observability, tracing, and analytics.
    # These keys are optional - if missing, tracing is disabled silently.
    
    LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
    """Langfuse secret key for server-side operations."""
    
    LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
    """Langfuse public key for trace identification."""
    
    LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    """Langfuse host URL. Defaults to cloud.langfuse.com."""
    
    # -------------------------------------------------------------------------
    # Validation Method
    # -------------------------------------------------------------------------
    
    @classmethod
    def validate(cls):
        """
        Validate that required configuration values are present.
        
        Currently, the only hard requirement is that at least one LLM API key
        is configured. Other services (flights, weather, payments) can fall 
        back to mock data if their keys are missing.
        
        Returns:
            bool: True if all required configuration is present, False otherwise.
        
        Side Effects:
            Prints warning messages listing any missing keys.
        
        Example:
            >>> Config.OPENAI_API_KEY = None
            >>> Config.ANTHROPIC_API_KEY = None  
            >>> Config.GOOGLE_API_KEY = None
            >>> Config.validate()
            Warning: Missing keys: At least one LLM API Key (OpenAI, Anthropic, or Google)
            Please create a .env file based on .env.example
            False
        """
        missing = []
        
        # Check that at least one LLM provider is configured
        # Without any LLM, the agent cannot function at all
        if not cls.OPENAI_API_KEY and not cls.ANTHROPIC_API_KEY and not cls.GOOGLE_API_KEY:
            missing.append("At least one LLM API Key (OpenAI, Anthropic, or Google)")
            
        # Report any missing required configuration
        if missing:
            print(f"Warning: Missing keys: {', '.join(missing)}")
            print("Please create a .env file based on .env.example")
            return False
        
        return True

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

def setup_logging(level="INFO"):
    """
    Configure structured JSON logging for the application.
    
    This function sets up logging to output JSON-formatted log messages,
    which is ideal for log aggregation systems like ELK Stack, Splunk,
    or cloud logging services (AWS CloudWatch, GCP Logging).
    
    JSON Format Benefits:
    ---------------------
    1. Machine Parseable: Easy to query and filter in log aggregation systems
    2. Structured Data: Consistent fields across all log entries
    3. Request Tracking: Includes request_id when available for tracing
    4. Rich Context: Captures module, function, timestamp automatically
    
    Args:
        level (str): Logging level - "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL".
                     Default is "INFO".
    
    Log Format:
    -----------
    Each log entry is a JSON object with these fields:
    {
        "timestamp": "2024-03-15 10:30:45,123",
        "level": "INFO",
        "message": "Agent initialized",
        "module": "web_server",
        "function": "initialize_agent",
        "request_id": "abc123"  // Optional, when tracking requests
    }
    
    Example:
        >>> setup_logging("DEBUG")  # Enable debug messages
        >>> import logging
        >>> logger = logging.getLogger(__name__)
        >>> logger.info("Server started", extra={"request_id": "req_123"})
        {"timestamp": "...", "level": "INFO", "message": "Server started", ...}
    """
    import logging
    import sys
    
    # Create a handler that writes to stdout (standard output)
    # This is appropriate for containerized environments where logs
    # are captured from stdout/stderr
    handler = logging.StreamHandler(sys.stdout)
    
    # Custom JSON formatter for structured logging
    class JsonFormatter(logging.Formatter):
        """
        Custom log formatter that outputs JSON.
        
        Extends the standard Formatter to output structured JSON instead of
        plain text. This makes logs easier to parse and query in log
        aggregation systems.
        """
        
        def format(self, record):
            """
            Format a log record as a JSON string.
            
            Args:
                record (LogRecord): The log record to format
            
            Returns:
                str: JSON-formatted log entry
            """
            # Build the log record dictionary with standard fields
            log_record = {
                "timestamp": self.formatTime(record, self.datefmt),  # Formatted timestamp
                "level": record.levelname,                           # INFO, ERROR, etc.
                "message": record.getMessage(),                      # The log message
                "module": record.module,                             # Module name (file)
                "function": record.funcName,                         # Function name
            }
            
            # Include request_id if it was passed via extra={}
            # This allows tracing logs across an entire request lifecycle
            if hasattr(record, "request_id"):
                log_record["request_id"] = record.request_id
            
            # Serialize to JSON string
            return json.dumps(log_record)

    # Apply our JSON formatter to the handler
    handler.setFormatter(JsonFormatter())
    
    # Get the root logger (affects all loggers in the application)
    root = logging.getLogger()
    
    # Set the logging level
    root.setLevel(level)
    
    # Remove any existing handlers to avoid duplicate log entries
    # This is important if setup_logging() is called multiple times
    # (e.g., in tests or during hot-reload)
    if root.handlers:
        for h in root.handlers:
            root.removeHandler(h)
    
    # Add our configured handler
    root.addHandler(handler)
