"""
================================================================================
FLIGHTS TOOL - Flight Search and Booking
================================================================================

This module provides flight search and booking functionality for the travel
agent. It supports both real API integration (Amadeus) and mock data fallback
for development and testing.

API Integration:
----------------
This module integrates with the Amadeus Flight Offers Search API:
https://developers.amadeus.com/self-service/category/flights

Amadeus API requires OAuth2 authentication:
1. Client credentials (API key and secret)
2. Token request to /v1/security/oauth2/token
3. Bearer token for subsequent API calls

The token is cached globally to avoid repeated auth requests.

Mock Data Fallback:
-------------------
If Amadeus credentials are not configured, or if the API fails, the module
falls back to generating realistic mock flight data. This allows:
- Development without API keys
- Testing without network dependencies
- Demonstrations without burning API quota

Flight Data Structure:
----------------------
Search results return a list of flight offers:
    {
        "flight_id": "DL123",           # Unique identifier for booking
        "airline": "Delta Air Lines (DL)",
        "airline_code": "DL",
        "flight_number": "DL123",
        "origin": "JFK",
        "destination": "LHR",
        "departure_time": "2024-03-15T10:00:00",
        "arrival_time": "2024-03-15T22:00:00",
        "price": 450.00,
        "currency": "USD",
        "duration": "PT12H00M",
        "booking_url": "https://..."
    }

Booking results:
    {
        "status": "confirmed",
        "booking_reference": "BK12345",
        "flight_id": "DL123",
        "passenger": "John Doe"
    }

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import random                              # For generating mock data
import httpx                               # Async HTTP client for API calls
from typing import List, Dict, Any, Optional  # Type hints
from pydantic import BaseModel, Field      # Data validation models
from ..agent.cache import global_tool_cache  # Caching decorator
from ..config import Config                # API key configuration

# =============================================================================
# GLOBAL STATE
# =============================================================================

# Cache for Amadeus OAuth access token
# Format: {"token": str, "expires_at": float (unix timestamp)}
# Tokens are cached until near expiration to avoid repeated auth requests
_amadeus_token_cache = {"token": None, "expires_at": 0}

# =============================================================================
# PYDANTIC MODELS FOR INPUT VALIDATION
# =============================================================================

class FlightSearchArgs(BaseModel):
    """
    Validation model for flight search parameters.
    
    While the actual tool function uses simple parameters (for compatibility
    with the MCP schema generator), this model can be used for explicit
    validation when needed.
    
    Attributes:
        origin: Three-letter IATA airport code (e.g., JFK, LHR, CDG)
        destination: Three-letter IATA airport code for arrival airport
        date: Travel date in ISO format (YYYY-MM-DD)
    
    Example:
        >>> args = FlightSearchArgs(origin="JFK", destination="LHR", date="2024-03-15")
        >>> args.origin
        'JFK'
    """
    origin: str = Field(..., description="Three-letter airport code (e.g., JFK).")
    destination: str = Field(..., description="Three-letter airport code (e.g., LHR).")
    date: str = Field(..., description="Date of travel (YYYY-MM-DD).")


class BookFlightArgs(BaseModel):
    """
    Validation model for flight booking parameters.
    
    Attributes:
        flight_id: The unique identifier of the flight to book
                  (as returned from search_flights)
        passenger_name: Full legal name of the passenger
                       (as it appears on passport)
        passport_number: Passport number for the passenger
    """
    flight_id: str = Field(..., description="The ID of the flight to book.")
    passenger_name: str = Field(..., description="Full name of the passenger.")
    passport_number: str = Field(..., description="Passport number of the passenger.")

# =============================================================================
# AMADEUS API AUTHENTICATION
# =============================================================================

async def _get_amadeus_token() -> str:
    """
    Get OAuth access token for Amadeus API.
    
    Amadeus uses OAuth 2.0 Client Credentials flow:
    1. Post client_id and client_secret to token endpoint
    2. Receive access_token with expires_in
    3. Use token in Authorization header for API calls
    
    Token caching:
    - Tokens are cached globally with their expiration time
    - We refresh 60 seconds before expiration for safety
    - Invalid/expired tokens trigger re-authentication
    
    Returns:
        str: Bearer access token for API authorization
    
    Raises:
        httpx.HTTPError: If token request fails
    """
    import time
    
    # Check if cached token is still valid
    # We check 60 seconds before expiration for safety margin
    if _amadeus_token_cache["token"] and time.time() < _amadeus_token_cache["expires_at"]:
        return _amadeus_token_cache["token"]
    
    # Request new token from Amadeus
    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": Config.FLIGHT_API_KEY,
        "client_secret": Config.FLIGHT_API_SECRET
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=data, timeout=10.0)
        response.raise_for_status()  # Raise on HTTP errors
        
        token_data = response.json()
        
        # Cache the new token
        _amadeus_token_cache["token"] = token_data["access_token"]
        # Subtract 60 seconds from expiry for safety margin
        _amadeus_token_cache["expires_at"] = time.time() + token_data.get("expires_in", 1800) - 60
        
        return _amadeus_token_cache["token"]

# =============================================================================
# MAIN SEARCH FUNCTION
# =============================================================================

# Note: Cache decorator removed for async functions
# TODO: Implement async-compatible caching if needed
async def search_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    """
    Search for flights between origin and destination on a specific date.
    
    This is the main entry point for flight search. It attempts to use the
    real Amadeus API if credentials are configured, otherwise falls back
    to mock data.
    
    Args:
        origin: Three-letter IATA airport code (e.g., "JFK", "LHR")
        destination: Three-letter IATA airport code
        date: Date of travel in YYYY-MM-DD format
    
    Returns:
        List of flight offer dictionaries. Each contains:
        - flight_id: Unique identifier for booking
        - airline: Airline name with code
        - flight_number: Flight number (e.g., "AA123")
        - origin/destination: Airport codes
        - departure_time/arrival_time: ISO datetime strings
        - price: Numeric price value
        - currency: Currency code (USD, EUR, etc.)
        - booking_url: Google search URL for the flight
    
    Example:
        >>> flights = await search_flights("JFK", "LHR", "2024-03-15")
        >>> for f in flights:
        ...     print(f"{f['airline']} at ${f['price']}")
        Delta Air Lines (DL) at $450.00
        British Airways (BA) at $520.00
    """
    # Try real API if credentials are configured
    if Config.FLIGHT_API_KEY and Config.FLIGHT_API_SECRET:
        try:
            return await _search_real_flights(origin, destination, date)
        except Exception as e:
            # Log warning and fall back to mock data
            print(f"[WARNING] Amadeus API failed: {e}. Falling back to mock data.")
    
    # Fallback to mock data (always works)
    return await _search_mock_flights(origin, destination, date)

# =============================================================================
# REAL API IMPLEMENTATION
# =============================================================================

async def _search_real_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    """
    Search for real flights using Amadeus API.
    
    This function calls the Amadeus Flight Offers Search API:
    GET /v2/shopping/flight-offers
    
    API Documentation:
    https://developers.amadeus.com/self-service/category/flights/api-doc/flight-offers-search
    
    Args:
        origin: IATA origin airport code
        destination: IATA destination airport code  
        date: Departure date (YYYY-MM-DD)
    
    Returns:
        List of normalized flight offers
    
    Raises:
        httpx.HTTPError: If API request fails
    """
    # Get OAuth token (may be cached)
    token = await _get_amadeus_token()
    
    # Call the Flight Offers Search endpoint
    url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "originLocationCode": origin.upper(),
        "destinationLocationCode": destination.upper(),
        "departureDate": date,
        "adults": 1,      # Number of passengers
        "max": 5          # Limit results to avoid overwhelming the user
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params, timeout=15.0)
        response.raise_for_status()
        data = response.json()

    # Parse API response into our standard format
    offers = data.get("data", [])
    
    # Airline code to name mapping (for display)
    airline_map = {
        "DL": "Delta Air Lines",
        "UA": "United Airlines",
        "BA": "British Airways",
        "LH": "Lufthansa",
        "AF": "Air France",
        "AA": "American Airlines",
        "EK": "Emirates",
        "RY": "Ryanair",
        "AZ": "ITA Airways",
        "TP": "TAP Air Portugal",
        "VS": "Virgin Atlantic"
    }

    # Transform API response to normalized format
    results = []
    for offer in offers:
        # Get first itinerary and segment (simplification)
        # Full implementation would handle multi-segment flights
        itinerary = offer.get("itineraries", [{}])[0]
        segment = itinerary.get("segments", [{}])[0]
        price = offer.get("price", {})
        
        # Get airline info
        carrier_code = segment.get("carrierCode", "Unknown")
        airline_name = airline_map.get(carrier_code, carrier_code)
        
        results.append({
            "flight_id": offer.get("id"),
            "airline": f"{airline_name} ({carrier_code})",
            "airline_code": carrier_code,
            "flight_number": f"{carrier_code}{segment.get('number', '000')}",
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_time": segment.get("departure", {}).get("at"),
            "arrival_time": segment.get("arrival", {}).get("at"),
            "price": float(price.get("total", 0)),
            "currency": price.get("currency", "USD"),
            "duration": itinerary.get("duration", "Unknown"),
            # Google search as booking URL (mock booking destination)
            "booking_url": f"https://www.google.com/search?q=flight+{carrier_code}+{origin}+{destination}"
        })
    
    return results

# =============================================================================
# MOCK DATA IMPLEMENTATION
# =============================================================================

async def _search_mock_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    """
    Generate mock flight search results for development/testing.
    
    This function produces realistic-looking flight data without
    making any external API calls. Useful for:
    - Development without API keys
    - Testing
    - Demos
    - Offline usage
    
    Features:
    - Random airlines and prices
    - Currency based on origin airport
    - Handles "no flights" scenario for testing alternative date logic
    
    Args:
        origin: Origin airport code
        destination: Destination airport code
        date: Requested travel date
    
    Returns:
        List of mock flight offers
    """
    print(f"[MOCK] Searching flights from {origin} to {destination} on {date}")
    
    # Airline data for generating realistic results
    airline_map = {
        "DL": "Delta Air Lines",
        "UA": "United Airlines",
        "BA": "British Airways",
        "LH": "Lufthansa",
        "AF": "Air France",
        "AA": "American Airlines",
        "EK": "Emirates",
        "RY": "Ryanair",
        "AZ": "ITA Airways"
    }
    
    airlines_codes = list(airline_map.keys())
    results = []
    
    # =========================================================================
    # LOCALIZED PRICING LOGIC
    # =========================================================================
    # Determine currency and price adjustment based on origin airport
    # This makes mock data more realistic for international users
    
    currency = "USD"
    price_multiplier = 1.0
    
    origin_upper = origin.upper()
    
    # UK airports -> British Pounds
    if origin_upper in ["LHR", "LGW", "MAN"]:
        currency = "GBP"
        price_multiplier = 0.8  # GBP is typically worth more than USD
    # European airports -> Euros
    elif origin_upper in ["CDG", "FRA", "FCO", "MXP", "AMS", "MAD"]:
        currency = "EUR"
        price_multiplier = 0.92
    # Japanese airports -> Yen
    elif origin_upper in ["TYO", "HND", "NRT"]:
        currency = "JPY"
        price_multiplier = 150.0  # Many yen per dollar
    
    # =========================================================================
    # SPECIAL CASE: "NO FLIGHTS" SCENARIO
    # =========================================================================
    # The agent's system prompt instructs it to try alternative dates
    # if no flights are found. This trigger word allows testing that logic.
    
    if origin.upper() == "NOW":
        print(f"[MOCK] No flights found for {origin} -> {destination} on {date}. Generating alternatives.")
        
        # Generate flights for the next day instead
        alt_date = f"{date[:-2]}{int(date[-2:]) + 1:02d}"
        
        for _ in range(2):
            code = random.choice(airlines_codes)
            airline_name = airline_map[code]
            flight_num = f"{code}{random.randint(100, 999)}"
            base_price = random.randint(300, 1200)
            price = int(base_price * price_multiplier)
            
            results.append({
                "flight_id": flight_num,
                "airline": f"{airline_name} ({code})",
                "airline_code": code,
                "origin": origin,
                "destination": destination,
                "departure_time": f"{alt_date}T{random.randint(6, 22)}:00:00",
                "price": price,
                "currency": currency,
                "booking_url": f"https://www.google.com/search?q=flight+{code}+{origin}+{destination}",
                # Flag these as alternative date results
                "is_alternative": True,
                "alternative_reason": f"No flights on {date}. Showing results for {alt_date}."
            })
        return results

    # =========================================================================
    # STANDARD MOCK RESULTS
    # =========================================================================
    # Generate 3 random flights for normal searches
    
    for _ in range(3):
        code = random.choice(airlines_codes)
        airline_name = airline_map[code]
        flight_num = f"{code}{random.randint(100, 999)}"
        base_price = random.randint(300, 1200)
        price = int(base_price * price_multiplier)
        
        results.append({
            "flight_id": flight_num,
            "airline": f"{airline_name} ({code})",
            "airline_code": code,
            "origin": origin,
            "destination": destination,
            "departure_time": f"{date}T{random.randint(6, 22)}:00:00",
            "price": price,
            "currency": currency,
            "booking_url": f"https://www.google.com/search?q=flight+{code}+{origin}+{destination}"
        })
        
    return results

# =============================================================================
# BOOKING FUNCTION
# =============================================================================

async def book_flight(flight_id: str, passenger_name: str, passport_number: str) -> Dict[str, Any]:
    """
    Book a specific flight for a passenger.
    
    This function simulates the booking process. In a production system,
    this would:
    1. Lock the seat
    2. Collect passenger details
    3. Process payment
    4. Issue confirmation
    
    Currently implemented as mock data only - real booking would require
    additional Amadeus API integration and airline partnerships.
    
    Args:
        flight_id: The flight identifier from search results
        passenger_name: Full legal name matching passport
        passport_number: Passport document number
    
    Returns:
        Booking confirmation with:
        - status: "confirmed" or "failed"
        - booking_reference: Alphanumeric confirmation code
        - flight_id: Echo of the booked flight
        - passenger: Passenger name
    
    Example:
        >>> booking = await book_flight("DL123", "John Doe", "AB1234567")
        >>> print(f"Booked! Reference: {booking['booking_reference']}")
        Booked! Reference: BK54321
    """
    print(f"[MOCK] Booking flight {flight_id} for {passenger_name}")
    
    # Generate mock booking confirmation
    return {
        "status": "confirmed",
        "booking_reference": f"BK{random.randint(10000, 99999)}",
        "flight_id": flight_id,
        "passenger": passenger_name
    }
