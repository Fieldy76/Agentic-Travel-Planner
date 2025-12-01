import random
from typing import Dict, Any

def get_forecast(location: str, date: str) -> Dict[str, Any]:
    """
    Get weather forecast for a location on a specific date.
    
    Args:
        location: City name.
        date: Date of forecast (YYYY-MM-DD).
    """
    print(f"[MOCK] Getting weather for {location} on {date}")
    
    conditions = ["Sunny", "Cloudy", "Rainy", "Partly Cloudy"]
    temp = random.randint(10, 30)
    
    return {
        "location": location,
        "date": date,
        "condition": random.choice(conditions),
        "temperature_celsius": temp,
        "temperature_fahrenheit": int(temp * 9/5 + 32)
    }
