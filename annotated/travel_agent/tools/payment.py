import random  # Import random module
from typing import Dict, Any  # Import typing utilities

def process_payment(amount: float, currency: str, method: str = "credit_card") -> Dict[str, Any]:  # Define process_payment function
    """
    Process a payment.
    
    Args:
        amount: Amount to pay.
        currency: Currency code (e.g., USD).
        method: Payment method (credit_card, paypal).
    """
    print(f"[MOCK] Processing payment of {amount} {currency} via {method}")  # Print mock log
    
    return {  # Return payment result
        "status": "success",  # Set status
        "transaction_id": f"TXN{random.randint(100000, 999999)}",  # Generate transaction ID
        "amount": amount,  # Set amount
        "currency": currency  # Set currency
    }
