import random
from typing import List, Dict, Any

def rent_car(location: str, start_date: str, end_date: str, car_type: str = "compact") -> Dict[str, Any]:
    """
    Rent a car at a specific location.
    
    Args:
        location: City or Airport code.
        start_date: Start date of rental (YYYY-MM-DD).
        end_date: End date of rental (YYYY-MM-DD).
        car_type: Type of car (compact, sedan, suv, luxury).
    """
    print(f"[MOCK] Renting {car_type} car at {location} from {start_date} to {end_date}")
    
    price_per_day = {
        "compact": 40,
        "sedan": 60,
        "suv": 90,
        "luxury": 150
    }.get(car_type.lower(), 50)
    
    # Calculate days (mock logic)
    days = 3 
    total_price = price_per_day * days
    
    return {
        "status": "reserved",
        "reservation_id": f"CAR{random.randint(10000, 99999)}",
        "car_type": car_type,
        "location": location,
        "total_price": total_price,
        "currency": "USD"
    }
