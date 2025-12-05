"""
================================================================================
WEATHER TOOL - Weather Forecast Functionality
================================================================================

This module provides weather forecast functionality for the travel agent.
It supports real API integration with Open-Meteo and falls back to mock
data for development and testing.

API Integration:
----------------
This module uses the Open-Meteo API (https://open-meteo.com/):
- Free for non-commercial use
- No API key required for basic usage
- Requires latitude/longitude for location

Since Open-Meteo requires coordinates, this module includes a simple
coordinate lookup for major cities. Unknown cities fall back to mock data.

Weather Data Structure:
-----------------------
    {
        "location": "London",
        "date": "2024-03-15",
        "condition": "Partly cloudy",
        "temperature_celsius": 15.5,
        "temperature_fahrenheit": 59.9,
        "temp_max_c": 18.0,    # Optional
        "temp_min_c": 13.0     # Optional
    }

Caching:
--------
Weather data is cached using the global_tool_cache with a 5-minute TTL.
This reduces API calls for repeated queries (e.g., checking weather
for the same destination multiple times in a conversation).

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import random                              # For generating mock data
import httpx                               # HTTP client for API calls
from typing import Dict, Any               # Type hints
from ..agent.cache import global_tool_cache  # Caching decorator
from ..config import Config                # API configuration

# =============================================================================
# MAIN FORECAST FUNCTION
# =============================================================================

@global_tool_cache.cached  # Cache results for 5 minutes (default TTL)
def get_forecast(location: str, date: str) -> Dict[str, Any]:
    """
    Get weather forecast for a location on a specific date.
    
    This function attempts to use the real Open-Meteo API if configured,
    otherwise falls back to generating realistic mock weather data.
    
    Args:
        location: City name (e.g., "London", "New York", "Tokyo")
        date: Forecast date in YYYY-MM-DD format
    
    Returns:
        dict: Weather forecast containing:
            - location: The queried location
            - date: The queried date
            - condition: Weather description (e.g., "Sunny", "Cloudy")
            - temperature_celsius: Average temperature in Celsius
            - temperature_fahrenheit: Average temperature in Fahrenheit
    
    Example:
        >>> forecast = get_forecast("London", "2024-03-15")
        >>> print(f"{forecast['location']}: {forecast['condition']}, {forecast['temperature_celsius']}°C")
        London: Partly cloudy, 15.5°C
    
    Note:
        This function is synchronous (not async) and is cached.
        Results are cached by location + date combination.
    """
    # Try to use real API if a weather API key/URL is configured
    if Config.WEATHER_API_KEY:
        try:
            return _get_real_forecast(location, date)
        except Exception as e:
            print(f"[WARNING] Weather API failed: {e}. Falling back to mock data.")
    
    # Fallback to mock data (always works)
    return _get_mock_forecast(location, date)

# =============================================================================
# REAL API IMPLEMENTATION
# =============================================================================

def _get_real_forecast(location: str, date: str) -> Dict[str, Any]:
    """
    Get real weather forecast from Open-Meteo API.
    
    Open-Meteo API Overview:
    - Free weather API with no authentication required
    - Requires latitude/longitude coordinates
    - Returns hourly and daily forecasts
    - Uses WMO weather codes for conditions
    
    Limitations:
    - Requires coordinate lookup (only major cities supported here)
    - Free tier has rate limits
    
    Args:
        location: City name to look up
        date: Forecast date (YYYY-MM-DD)
    
    Returns:
        Weather forecast dictionary
    """
    # =========================================================================
    # COORDINATE LOOKUP
    # =========================================================================
    # Open-Meteo requires lat/lon. We maintain a simple lookup table
    # for common travel destinations. For production, use a geocoding API.
    
    city_coords = {
        "tokyo": (35.6762, 139.6503),
        "new york": (40.7128, -74.0060),
        "london": (51.5074, -0.1278),
        "paris": (48.8566, 2.3522),
        "dallas": (32.7767, -96.7970),
        "rome": (41.9028, 12.4964),
    }
    
    # Try to find coordinates (case-insensitive)
    coords = city_coords.get(location.lower())
    if not coords:
        print(f"[INFO] No coordinates for {location}, using mock data")
        return _get_mock_forecast(location, date)
    
    lat, lon = coords
    
    # =========================================================================
    # API REQUEST
    # =========================================================================
    # The WEATHER_API_KEY config value is actually the API URL for Open-Meteo
    # This is a simplification - in production, it would be a proper API key
    
    url = Config.WEATHER_API_KEY
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,weathercode",  # Daily data fields
        "start_date": date,
        "end_date": date,       # Same day = single day forecast
        "timezone": "auto"      # Use location's timezone
    }
    
    # Make synchronous HTTP request (this function is not async)
    response = httpx.get(url, params=params, timeout=10.0)
    response.raise_for_status()
    data = response.json()
    
    # =========================================================================
    # PARSE RESPONSE
    # =========================================================================
    
    daily = data.get("daily", {})
    temp_max = daily.get("temperature_2m_max", [None])[0]
    temp_min = daily.get("temperature_2m_min", [None])[0]
    weather_code = daily.get("weathercode", [0])[0]
    
    # WMO Weather Codes mapping
    # Reference: https://open-meteo.com/en/docs#weathervariables
    condition_map = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Foggy",
        51: "Light drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        80: "Rain showers",
    }
    condition = condition_map.get(weather_code, "Unknown")
    
    # Calculate average temperature
    avg_temp = (temp_max + temp_min) / 2 if temp_max and temp_min else None
    
    return {
        "location": location,
        "date": date,
        "condition": condition,
        "temperature_celsius": round(avg_temp, 1) if avg_temp else None,
        "temperature_fahrenheit": round(avg_temp * 9/5 + 32, 1) if avg_temp else None,
        "temp_max_c": temp_max,
        "temp_min_c": temp_min,
    }

# =============================================================================
# MOCK DATA IMPLEMENTATION
# =============================================================================

def _get_mock_forecast(location: str, date: str) -> Dict[str, Any]:
    """
    Generate mock weather forecast for development/testing.
    
    Produces randomized but realistic weather data:
    - Temperature between 10-30°C
    - Random condition from common weather types
    
    Args:
        location: Location name (used as-is in response)
        date: Date string (used as-is in response)
    
    Returns:
        Mock weather forecast dictionary
    """
    print(f"[MOCK] Getting weather for {location} on {date}")
    
    # Random weather conditions
    conditions = ["Sunny", "Cloudy", "Rainy", "Partly Cloudy"]
    
    # Random temperature in reasonable range
    temp = random.randint(10, 30)
    
    return {
        "location": location,
        "date": date,
        "condition": random.choice(conditions),
        "temperature_celsius": temp,
        "temperature_fahrenheit": int(temp * 9/5 + 32)  # Convert C to F
    }
