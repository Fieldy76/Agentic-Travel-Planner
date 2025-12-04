"""
Test script to verify weather and flight API integrations.
Run this after adding FLIGHT_API_SECRET to your .env file.
"""
import sys
import os
from dotenv import load_dotenv

# Add the project root to sys.path
sys.path.append('/home/fabio/Desktop/Antigravity/Agentic Travel Planner')
load_dotenv()

from travel_agent.tools.weather import get_forecast
from travel_agent.tools.flights import search_flights

print("=== Testing Weather API Integration ===\n")
try:
    weather = get_forecast("Dallas", "2025-12-15")
    print(f"✓ Weather API test successful!")
    print(f"  Location: {weather.get('location')}")
    print(f"  Condition: {weather.get('condition')}")
    print(f"  Temperature: {weather.get('temperature_celsius')}°C / {weather.get('temperature_fahrenheit')}°F")
except Exception as e:
    print(f"✗ Weather API test failed: {e}")

print("\n=== Testing Flight API Integration ===\n")
try:
    flights = search_flights("DFW", "JFK", "2025-12-15")
    print(f"✓ Flight API test successful!")
    print(f"  Found {len(flights)} flight(s)")
    if flights:
        flight = flights[0]
        print(f"  First flight: {flight.get('airline')} {flight.get('flight_number')}")
        print(f"  Price: {flight.get('price')} {flight.get('currency')}")
        print(f"  Departure: {flight.get('departure_time')}")
except Exception as e:
    print(f"✗ Flight API test failed: {e}")

print("\n=== Configuration Check ===\n")
from travel_agent.config import Config

print(f"FLIGHT_API_KEY: {'✓ Set' if Config.FLIGHT_API_KEY else '✗ Not set'}")
print(f"FLIGHT_API_SECRET: {'✓ Set' if Config.FLIGHT_API_SECRET else '✗ Not set (REQUIRED for real API)'}")
print(f"WEATHER_API_KEY: {'✓ Set' if Config.WEATHER_API_KEY else '✗ Not set'}")

if not Config.FLIGHT_API_SECRET:
    print("\n⚠️  Warning: FLIGHT_API_SECRET not found. Add it to your .env file:")
    print("   FLIGHT_API_SECRET=your_amadeus_api_secret_here")
