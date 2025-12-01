# Import random for generating mock weather data
import random
# Import type hints for better code documentation
from typing import Dict, Any
# Import the global cache instance for performance optimization
from ..agent.cache import global_tool_cache

# Apply caching decorator to avoid redundant weather API calls
# Weather doesn't change every second, so caching for 5 minutes is reasonable
@global_tool_cache.cached
def get_forecast(location: str, date: str) -> Dict[str, Any]:
    """
    Get weather forecast for a location on a specific date.
    
    This is a MOCK implementation that generates random weather data.
    In production, this would call a real weather API (e.g., OpenWeatherMap, WeatherAPI).
    
    Args:
        location: City name or location identifier (e.g., "Tokyo", "New York").
        date: Date for the forecast in YYYY-MM-DD format.
        
    Returns:
        Dictionary containing weather information:
        - location: The requested location
        - date: The forecast date
        - condition: Weather condition (e.g., "Sunny", "Rainy")
        - temperature_celsius: Temperature in Celsius
        - temperature_fahrenheit: Temperature in Fahrenheit
    """
    # Print to show this is mock data (helps with debugging/demo)
    print(f"[MOCK] Getting weather for {location} on {date}")
    
    # Mock data: Possible weather conditions
    conditions = ["Sunny", "Cloudy", "Rainy", "Partly Cloudy"]
    # Generate a random temperature between 10°C and 30°C
    temp = random.randint(10, 30)
    
    # Return a mock weather forecast
    return {
        "location": location,
        "date": date,
        # Randomly choose a weather condition
        "condition": random.choice(conditions),
        "temperature_celsius": temp,
        # Convert Celsius to Fahrenheit: (C × 9/5) + 32
        "temperature_fahrenheit": int(temp * 9/5 + 32)
    }
