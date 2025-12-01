import random  # Import random module for mock data generation
from typing import List, Dict, Any  # Import typing utilities

def search_flights(origin: str, destination: str, date: str) -> List[Dict[str, Any]]:  # Define search_flights function
    """
    Search for flights between origin and destination on a specific date.
    
    Args:
        origin: Three-letter airport code (e.g., JFK).
        destination: Three-letter airport code (e.g., LHR).
        date: Date of travel (YYYY-MM-DD).
    """
    print(f"[MOCK] Searching flights from {origin} to {destination} on {date}")  # Print mock log
    
    # Mock data generation
    airlines = ["Delta", "United", "British Airways", "Lufthansa"]  # List of airlines
    results = []  # Initialize results list
    
    for _ in range(3):  # Generate 3 mock flights
        airline = random.choice(airlines)  # Pick random airline
        flight_num = f"{airline[:2].upper()}{random.randint(100, 999)}"  # Generate flight number
        price = random.randint(300, 1200)  # Generate random price
        results.append({  # Add flight details to results
            "flight_id": flight_num,  # Set flight ID
            "airline": airline,  # Set airline
            "origin": origin,  # Set origin
            "destination": destination,  # Set destination
            "departure_time": f"{date}T{random.randint(6, 22)}:00:00",  # Set departure time
            "price": price,  # Set price
            "currency": "USD"  # Set currency
        })
        
    return results  # Return list of flights

def book_flight(flight_id: str, passenger_name: str, passport_number: str) -> Dict[str, Any]:  # Define book_flight function
    """
    Book a specific flight for a passenger.
    
    Args:
        flight_id: The ID of the flight to book.
        passenger_name: Full name of the passenger.
        passport_number: Passport number of the passenger.
    """
    print(f"[MOCK] Booking flight {flight_id} for {passenger_name}")  # Print mock log
    
    return {  # Return booking confirmation
        "status": "confirmed",  # Set status
        "booking_reference": f"BK{random.randint(10000, 99999)}",  # Generate booking reference
        "flight_id": flight_id,  # Set flight ID
        "passenger": passenger_name  # Set passenger name
    }
