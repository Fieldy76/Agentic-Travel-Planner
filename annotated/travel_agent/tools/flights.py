# Import random for generating mock data
import random
# Import type hints for better code documentation
from typing import List, Dict, Any
# Import the global cache instance for performance optimization
from ..agent.cache import global_tool_cache

# Apply caching decorator to avoid redundant flight searches
# If the same origin/destination/date is searched within 5 minutes,
# we'll return the cached result instead of regenerating mock data
@global_tool_cache.cached
def search_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
    """
    Search for flights between origin and destination on a specific date.
    
    This is a MOCK implementation that generates random flight data.
    In production, this would call a real flight search API (e.g., Amadeus, Skyscanner).
    
    Args:
        origin: Three-letter airport code (e.g., JFK for New York).
        destination: Three-letter airport code (e.g., LHR for London).
        date: Date of travel in YYYY-MM-DD format.
        
    Returns:
        List of flight dictionaries, each containing:
        - flight_id: Unique flight identifier
        - airline: Airline name
        - origin: Departure airport
        - destination: Arrival airport
        - departure_time: ISO format timestamp
        - price: Ticket price in USD
        - currency: Price currency (always USD in this mock)
    """
    # Print to show this is mock data (helps with debugging/demo)
    print(f"[MOCK] Searching flights from {origin} to {destination} on {date}")
    
    # Mock data: List of sample airlines
    airlines = ["Delta", "United", "British Airways", "Lufthansa"]
    # Initialize results list
    results = []
    
    # Generate 3 random flight options
    for _ in range(3):
        # Pick a random airline
        airline = random.choice(airlines)
        # Generate a flight number (e.g., "DE324", "UN759")
        # Take first 2 letters of airline name + random 3-digit number
        flight_num = f"{airline[:2].upper()}{random.randint(100, 999)}"
        # Generate a random price between $300 and $1200
        price = random.randint(300, 1200)
        
        # Add this flight to results
        results.append({
            "flight_id": flight_num,
            "airline": airline,
            "origin": origin,
            "destination": destination,
            # Random departure hour between 6 AM and 10 PM
            "departure_time": f"{date}T{random.randint(6, 22)}:00:00",
            "price": price,
            "currency": "USD"
        })
    
    # Return the list of flight options
    return results

def book_flight(flight_id: str, passenger_name: str, passport_number: str) -> Dict[str, Any]:
    """
    Book a specific flight for a passenger.
    
    This is a MOCK implementation. In production, this would:
    1. Validate the flight still has availability
    2. Process payment
    3. Reserve the seat
    4. Send confirmation email
    
    Args:
        flight_id: The ID of the flight to book (from search_flights results).
        passenger_name: Full name of the passenger as it appears on passport.
        passport_number: Passport number of the passenger.
        
    Returns:
        Dictionary containing booking confirmation:
        - status: "confirmed" or "failed"
        - booking_reference: Unique booking ID
        - flight_id: The booked flight ID
        - passenger: Passenger name
    """
    # Print to show booking is happening (for demo purposes)
    print(f"[MOCK] Booking flight {flight_id} for {passenger_name}")
    
    # Return a mock booking confirmation
    return {
        "status": "confirmed",
        # Generate a random 5-digit booking reference (e.g., "BK12345")
        "booking_reference": f"BK{random.randint(10000, 99999)}",
        "flight_id": flight_id,
        "passenger": passenger_name
    }
