import random
import httpx
from typing import List, Dict, Any
from ..agent.cache import global_tool_cache
from ..config import Config

# Global variable to cache Amadeus access token
_amadeus_token_cache = {"token": None, "expires_at": 0}

def _get_amadeus_token() -> str:
    """Get OAuth access token for Amadeus API."""
    import time
    
    # Check if cached token is still valid
    if _amadeus_token_cache["token"] and time.time() < _amadeus_token_cache["expires_at"]:
        return _amadeus_token_cache["token"]
    
    # Get new token
    url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": Config.FLIGHT_API_KEY,
        "client_secret": Config.FLIGHT_API_SECRET
    }
    
    response = httpx.post(url, data=data, timeout=10.0)
    response.raise_for_status()
    
    token_data = response.json()
    _amadeus_token_cache["token"] = token_data["access_token"]
    _amadeus_token_cache["expires_at"] = time.time() + token_data.get("expires_in", 1800) - 60
    
    return _amadeus_token_cache["token"]

@global_tool_cache.cached
def search_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    """
    Search for flights between origin and destination on a specific date.
    
    Args:
        origin: Three-letter airport code (e.g., JFK).
        destination: Three-letter airport code (e.g., LHR).
        date: Date of travel (YYYY-MM-DD).
    """
    # Try to use real API if configured
    if Config.FLIGHT_API_KEY and Config.FLIGHT_API_SECRET:
        try:
            return _search_real_flights(origin, destination, date)
        except Exception as e:
            print(f"[WARNING] Amadeus API failed: {e}. Falling back to mock data.")
    
    # Fallback to mock data
    return _search_mock_flights(origin, destination, date)

def _search_real_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    """Search for real flights using Amadeus API."""
    token = _get_amadeus_token()
    
    url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "originLocationCode": origin.upper(),
        "destinationLocationCode": destination.upper(),
        "departureDate": date,
        "adults": 1,
        "max": 5  # Limit results
    }
    
    response = httpx.get(url, headers=headers, params=params, timeout=15.0)
    response.raise_for_status()
    
    data = response.json()
    offers = data.get("data", [])
    
    # Airline Code Map (Shared with mock)
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

    # Parse and format results
    results = []
    for offer in offers:
        # Get first itinerary and segment
        itinerary = offer.get("itineraries", [{}])[0]
        segment = itinerary.get("segments", [{}])[0]
        price = offer.get("price", {})
        
        carrier_code = segment.get("carrierCode", "Unknown")
        airline_name = airline_map.get(carrier_code, carrier_code)
        
        results.append({
            "flight_id": offer.get("id"),
            "airline": airline_name,
            "airline_code": carrier_code,
            "flight_number": f"{carrier_code}{segment.get('number', '000')}",
            "origin": origin.upper(),
            "destination": destination.upper(),
            "departure_time": segment.get("departure", {}).get("at"),
            "arrival_time": segment.get("arrival", {}).get("at"),
            "price": float(price.get("total", 0)),
            "currency": price.get("currency", "USD"),
            "duration": itinerary.get("duration", "Unknown"),
            "booking_url": f"https://www.google.com/search?q=flight+{carrier_code}+{origin}+{destination}"
        })
    
    return results

def _search_mock_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    """Generate mock flight search results."""
    print(f"[MOCK] Searching flights from {origin} to {destination} on {date}")
    
    # Mock airline data
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
    
    # Localized pricing logic (Mock)
    currency = "USD"
    price_multiplier = 1.0
    
    origin_upper = origin.upper()
    if origin_upper in ["LHR", "LGW", "MAN"]:
        currency = "GBP"
        price_multiplier = 0.8
    elif origin_upper in ["CDG", "FRA", "FCO", "MXP", "AMS", "MAD"]:
        currency = "EUR"
        price_multiplier = 0.92
    elif origin_upper in ["TYO", "HND", "NRT"]:
        currency = "JPY"
        price_multiplier = 150.0
    
    # Simulate "No flights found" for specific date/route to test alternatives
    # For demo purposes, let's say flights on the 25th are sold out if origin is "NOW" (No Way)
    if origin.upper() == "NOW":
        print(f"[MOCK] No flights found for {origin} -> {destination} on {date}. Generating alternatives.")
        # Return empty list to trigger agent's alternative logic, 
        # OR return alternatives directly with a flag. 
        # Let's return alternatives for a different date.
        
        alt_date = f"{date[:-2]}{int(date[-2:]) + 1:02d}" # Next day
        for _ in range(2):
            code = random.choice(airlines_codes)
            airline_name = airline_map[code]
            flight_num = f"{code}{random.randint(100, 999)}"
            base_price = random.randint(300, 1200)
            price = int(base_price * price_multiplier)
            
            results.append({
                "flight_id": flight_num,
                "airline": airline_name,
                "airline_code": code,
                "origin": origin,
                "destination": destination,
                "departure_time": f"{alt_date}T{random.randint(6, 22)}:00:00",
                "price": price,
                "currency": currency,
                "booking_url": f"https://www.google.com/search?q=flight+{code}+{origin}+{destination}",
                "is_alternative": True,
                "alternative_reason": f"No flights on {date}. Showing results for {alt_date}."
            })
        return results

    for _ in range(3):
        code = random.choice(airlines_codes)
        airline_name = airline_map[code]
        flight_num = f"{code}{random.randint(100, 999)}"
        base_price = random.randint(300, 1200)
        price = int(base_price * price_multiplier)
        
        results.append({
            "flight_id": flight_num,
            "airline": airline_name,
            "airline_code": code,
            "origin": origin,
            "destination": destination,
            "departure_time": f"{date}T{random.randint(6, 22)}:00:00",
            "price": price,
            "currency": currency,
            "booking_url": f"https://www.google.com/search?q=flight+{code}+{origin}+{destination}"
        })
        
    return results

def book_flight(flight_id: str, passenger_name: str, passport_number: str) -> Dict[str, Any]:
    """
    Book a specific flight for a passenger.
    
    Args:
        flight_id: The ID of the flight to book.
        passenger_name: Full name of the passenger.
        passport_number: Passport number of the passenger.
    """
    print(f"[MOCK] Booking flight {flight_id} for {passenger_name}")
    
    # Note: Amadeus booking requires more complex flow with pricing confirmation
    # This remains as mock for now
    return {
        "status": "confirmed",
        "booking_reference": f"BK{random.randint(10000, 99999)}",
        "flight_id": flight_id,
        "passenger": passenger_name
    }
