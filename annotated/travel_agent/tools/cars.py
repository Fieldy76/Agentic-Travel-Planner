import random  # Import random module
from typing import List, Dict, Any  # Import typing utilities

def rent_car(location: str, start_date: str, end_date: str, car_type: str = "compact") -> Dict[str, Any]:  # Define rent_car function
    """
    Rent a car at a specific location.
    
    Args:
        location: City or Airport code.
        start_date: Start date of rental (YYYY-MM-DD).
        end_date: End date of rental (YYYY-MM-DD).
        car_type: Type of car (compact, sedan, suv, luxury).
    """
    print(f"[MOCK] Renting {car_type} car at {location} from {start_date} to {end_date}")  # Print mock log
    
    price_per_day = {  # Define price mapping
        "compact": 40,  # Compact price
        "sedan": 60,  # Sedan price
        "suv": 90,  # SUV price
        "luxury": 150  # Luxury price
    }.get(car_type.lower(), 50)  # Get price or default to 50
    
    # Calculate days (mock logic)
    days = 3   # Mock duration
    total_price = price_per_day * days  # Calculate total price
    
    return {  # Return reservation details
        "status": "reserved",  # Set status
        "reservation_id": f"CAR{random.randint(10000, 99999)}",  # Generate reservation ID
        "car_type": car_type,  # Set car type
        "location": location,  # Set location
        "total_price": total_price,  # Set total price
        "currency": "USD"  # Set currency
    }
