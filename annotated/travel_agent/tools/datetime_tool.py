"""
================================================================================
DATETIME TOOL - Current Date and Time Information
================================================================================

This module provides a simple tool for getting the current date and time.
While seemingly basic, this tool is essential for the agent to:

1. Understand relative dates ("tomorrow", "next week")
2. Validate user-provided dates
3. Provide accurate time-sensitive information

The agent's system prompt is enhanced with date context at runtime,
but this tool provides a more explicit way to access date/time info.

Use Cases:
----------
- Agent needs to calculate relative dates
- User asks "What day is today?"
- Validating that requested dates are in the future
- Time zone considerations (uses server's local time)

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

from datetime import datetime    # Python's datetime handling
from typing import Dict, Any     # Type hints

# =============================================================================
# DATETIME FUNCTION
# =============================================================================

def get_current_datetime() -> Dict[str, Any]:
    """
    Get the current date and time information.
    
    This tool returns comprehensive date and time information in
    various formats, allowing the agent to work with dates flexibly.
    
    Returns:
        dict: Current date/time information containing:
        
            - datetime: Full timestamp (YYYY-MM-DD HH:MM:SS)
            - date: Date only (YYYY-MM-DD) - ideal for API calls
            - time: Time only (HH:MM:SS)
            - day_of_week: Full day name (e.g., "Monday")
            - year: Year as integer (e.g., 2024)
            - month: Month as integer (1-12)
            - day: Day of month as integer (1-31)
            - hour: Hour in 24-hour format (0-23)
            - minute: Minute (0-59)
    
    Example:
        >>> info = get_current_datetime()
        >>> print(f"Today is {info['day_of_week']}, {info['date']}")
        Today is Monday, 2024-03-15
        >>> print(f"Time: {info['time']}")
        Time: 14:30:45
    
    Note:
        This function uses the server's local time zone.
        For international applications, consider using UTC or
        accepting a timezone parameter.
    
    Why This Tool Exists:
        While the agent's system prompt includes the current date,
        having it as a tool provides:
        1. Explicit access when the agent needs date info mid-conversation
        2. Structured data that's easy to parse
        3. Consistency with other tool-based operations
    """
    # Get current datetime from system
    now = datetime.now()
    
    # Return comprehensive date/time breakdown
    return {
        # Full formats
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),  # Full timestamp
        "date": now.strftime("%Y-%m-%d"),               # ISO date format
        "time": now.strftime("%H:%M:%S"),               # 24-hour time
        
        # Day of week (useful for user-friendly responses)
        "day_of_week": now.strftime("%A"),              # Full day name
        
        # Individual components (for calculations)
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "hour": now.hour,
        "minute": now.minute
    }
