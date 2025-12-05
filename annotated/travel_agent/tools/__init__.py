"""
================================================================================
TOOLS PACKAGE - Tool Functions for the Agentic Travel Planner
================================================================================

This package contains all the tool functions that the AI agent can use to
interact with external services and perform actions. Each tool is registered
with the MCP Server and becomes available for the LLM to call.

Available Tools:
----------------
1. search_flights - Search for flights between airports
2. book_flight - Book a specific flight for a passenger
3. rent_car - Reserve a car rental at a location
4. get_forecast - Get weather forecast for a destination
5. process_payment - Process payments via Stripe
6. get_current_datetime - Get the current date and time

Tool Design Principles:
-----------------------
1. Single Responsibility: Each tool does one thing well
2. Clear Documentation: Docstrings describe purpose and parameters
3. Graceful Fallback: Real API calls fall back to mock data if needed
4. Async Support: Tools can be async for non-blocking I/O
5. Type Hints: Clear parameter types for schema generation

Usage:
------
Tools are imported and registered with the MCP Server:

    from travel_agent.tools import search_flights, book_flight, ...
    
    server = MCPServer()
    server.register_tool(search_flights)
    server.register_tool(book_flight)
    # ... etc.

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# PUBLIC EXPORTS
# =============================================================================

# Import all tool functions from their respective modules
# These are the core capabilities of the travel agent

from .flights import search_flights, book_flight   # Flight search and booking
from .cars import rent_car                         # Car rental
from .weather import get_forecast                  # Weather forecasting
from .payment import process_payment               # Payment processing
from .datetime_tool import get_current_datetime    # Date/time utility
