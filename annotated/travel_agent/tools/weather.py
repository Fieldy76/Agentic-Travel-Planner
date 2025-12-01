import random  # Import random module
from typing import Dict, Any  # Import typing utilities

def get_forecast(location: str, date: str) -> Dict[str, Any]:  # Define get_forecast function
    """
    Get weather forecast for a location on a specific date.
    
    Args:
        location: City name.
        date: Date of forecast (YYYY-MM-DD).
    """
    print(f"[MOCK] Getting weather for {location} on {date}")  # Print mock log
    
    conditions = ["Sunny", "Cloudy", "Rainy", "Partly Cloudy"]  # List of weather conditions
    temp = random.randint(10, 30)  # Generate random temperature
    
    return {  # Return forecast data
        "location": location,  # Set location
        "date": date,  # Set date
        "condition": random.choice(conditions),  # Pick random condition
        "temperature_celsius": temp,  # Set celsius temp
        "temperature_fahrenheit": int(temp * 9/5 + 32)  # Calculate and set fahrenheit temp
    }
