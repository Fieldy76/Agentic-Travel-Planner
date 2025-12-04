import random
import httpx
from typing import Dict, Any
from ..agent.cache import global_tool_cache
from ..config import Config

@global_tool_cache.cached
def get_forecast(location: str, date: str) -> Dict[str, Any]:
    """
    Get weather forecast for a location on a specific date.
    
    Args:
        location: City name.
        date: Date of forecast (YYYY-MM-DD).
    """
    # Try to use real API if configured
    if Config.WEATHER_API_KEY:
        try:
            return _get_real_forecast(location, date)
        except Exception as e:
            print(f"[WARNING] Weather API failed: {e}. Falling back to mock data.")
    
    # Fallback to mock data
    return _get_mock_forecast(location, date)

def _get_real_forecast(location: str, date: str) -> Dict[str, Any]:
    """Get real weather forecast from Open-Meteo API."""
    # For simplicity, use geocoding to get coordinates (or hardcode major cities)
    # Open-Meteo requires latitude/longitude
    # This is a simplified implementation - in production, you'd geocode the location first
    
    # Hardcoded coordinates for common cities (fallback to mock if not found)
    city_coords = {
        "tokyo": (35.6762, 139.6503),
        "new york": (40.7128, -74.0060),
        "london": (51.5074, -0.1278),
        "paris": (48.8566, 2.3522),
        "dallas": (32.7767, -96.7970),
        "rome": (41.9028, 12.4964),
    }
    
    coords = city_coords.get(location.lower())
    if not coords:
        print(f"[INFO] No coordinates for {location}, using mock data")
        return _get_mock_forecast(location, date)
    
    lat, lon = coords
    
    # Call Open-Meteo API
    url = Config.WEATHER_API_KEY
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,weathercode",
        "start_date": date,
        "end_date": date,
        "timezone": "auto"
    }
    
    response = httpx.get(url, params=params, timeout=10.0)
    response.raise_for_status()
    data = response.json()
    
    # Parse response
    daily = data.get("daily", {})
    temp_max = daily.get("temperature_2m_max", [None])[0]
    temp_min = daily.get("temperature_2m_min", [None])[0]
    weather_code = daily.get("weathercode", [0])[0]
    
    # Map weather codes to conditions
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

def _get_mock_forecast(location: str, date: str) -> Dict[str, Any]:
    """Generate mock weather forecast."""
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
