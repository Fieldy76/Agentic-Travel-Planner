import random
from typing import List, Dict, Any
from ..agent.cache import global_tool_cache

@global_tool_cache.cached
def search_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    """
    Search for flights between origin and destination on a specific date.
    
    Args:
        origin: Three-letter airport code (e.g., JFK).
        destination: Three-letter airport code (e.g., LHR).
        date: Date of travel (YYYY-MM-DD).
    """
    print(f"[MOCK] Searching flights from {origin} to {destination} on {date}")
    
    # Mock data generation
    airlines = ["Delta", "United", "British Airways", "Lufthansa"]
    results = []
    
    for _ in range(3):
        airline = random.choice(airlines)
        flight_num = f"{airline[:2].upper()}{random.randint(100, 999)}"
        price = random.randint(300, 1200)
        results.append({
            "flight_id": flight_num,
            "airline": airline,
            "origin": origin,
            "destination": destination,
            "departure_time": f"{date}T{random.randint(6, 22)}:00:00",
            "price": price,
            "currency": "USD"
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
    
    return {
        "status": "confirmed",
        "booking_reference": f"BK{random.randint(10000, 99999)}",
        "flight_id": flight_id,
        "passenger": passenger_name
    }
