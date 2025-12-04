from datetime import datetime
from typing import Dict, Any

def get_current_datetime() -> Dict[str, Any]:
    """
    Get the current date and time.
    
    Returns the current date, time, day of week, and other time information.
    """
    now = datetime.now()
    
    return {
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day_of_week": now.strftime("%A"),
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "hour": now.hour,
        "minute": now.minute
    }
