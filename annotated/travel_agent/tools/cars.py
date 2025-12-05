"""
================================================================================
CAR RENTAL TOOL - Car Rental Reservation Functionality
================================================================================

This module provides car rental functionality for the travel agent.
Currently implemented with mock data only - real integration would
require partnership with a car rental API provider like:
- Amadeus Car Search API
- Rental Cars API
- Enterprise/National/Hertz APIs

Mock Data Features:
-------------------
- Supports multiple car types with different pricing
- Generates realistic reservation IDs
- Calculates estimated pricing based on car type

Car Types and Pricing:
----------------------
    compact: $40/day - Economy option for city driving
    sedan:   $60/day - Mid-range comfort
    suv:     $90/day - Family/group travel
    luxury: $150/day - Premium experience

Future Integration Points:
--------------------------
For production implementation, consider:
1. Amadeus Car Search API (https://developers.amadeus.com)
2. Integration with major rental companies
3. Insurance options
4. Pick-up/drop-off location flexibility
5. Driver requirements (age, license)

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import random                    # For generating mock data
from typing import List, Dict, Any  # Type hints

# =============================================================================
# CAR RENTAL FUNCTION
# =============================================================================

def rent_car(location: str, start_date: str, end_date: str, car_type: str = "compact") -> Dict[str, Any]:
    """
    Rent a car at a specific location.
    
    This function creates a car rental reservation. Currently implemented
    as mock data only for development and demonstration purposes.
    
    Args:
        location: City or Airport code where car will be picked up.
                 Can be city name ("New York") or airport code ("JFK").
        
        start_date: Start date of rental in YYYY-MM-DD format.
                   This is also the pick-up date.
        
        end_date: End date of rental in YYYY-MM-DD format.
                 This is also the drop-off date.
        
        car_type: Type of car to rent. Options are:
                 - "compact": Economy car ($40/day)
                 - "sedan": Mid-size car ($60/day)
                 - "suv": Sport utility vehicle ($90/day)
                 - "luxury": Premium/luxury car ($150/day)
                 Default is "compact".
    
    Returns:
        dict: Reservation confirmation containing:
            - status: "reserved" for successful reservation
            - reservation_id: Unique ID for the booking (e.g., "CAR12345")
            - car_type: The type of car reserved
            - location: Pick-up/drop-off location
            - total_price: Estimated total cost
            - currency: Currency code (currently always USD)
    
    Example:
        >>> rental = rent_car("JFK", "2024-03-15", "2024-03-18", "sedan")
        >>> print(f"Reserved {rental['car_type']} at {rental['location']}")
        Reserved sedan at JFK
        >>> print(f"Total: ${rental['total_price']} {rental['currency']}")
        Total: $180 USD
    
    Note:
        This is currently a mock implementation. The actual rental duration
        is hardcoded to 3 days for simplification. In production, this would
        calculate the actual days between start_date and end_date.
    """
    print(f"[MOCK] Renting {car_type} car at {location} from {start_date} to {end_date}")
    
    # =========================================================================
    # PRICING LOGIC
    # =========================================================================
    # Define daily rates for each car type
    # In production, these would come from the rental API
    
    price_per_day = {
        "compact": 40,   # Economy - cheapest option
        "sedan": 60,     # Standard - most popular
        "suv": 90,       # Larger vehicle - for families/groups
        "luxury": 150    # Premium - business/leisure upgrade
    }.get(car_type.lower(), 50)  # Default to $50/day for unknown types
    
    # =========================================================================
    # MOCK CALCULATION
    # =========================================================================
    # TODO: Calculate actual days between start_date and end_date
    # For now, using a hardcoded 3-day rental period
    
    days = 3  # Mock: always 3 days
    total_price = price_per_day * days
    
    # Generate mock reservation
    return {
        "status": "reserved",
        "reservation_id": f"CAR{random.randint(10000, 99999)}",  # Unique ID
        "car_type": car_type,
        "location": location,
        "total_price": total_price,
        "currency": "USD"  # Currently hardcoded to USD
    }
