import random
from typing import Dict, Any

def process_payment(amount: float, currency: str, method: str = "credit_card") -> Dict[str, Any]:
    """
    Process a payment.
    
    Args:
        amount: Amount to pay.
        currency: Currency code (e.g., USD).
        method: Payment method (credit_card, paypal).
    """
    print(f"[MOCK] Processing payment of {amount} {currency} via {method}")
    
    return {
        "status": "success",
        "transaction_id": f"TXN{random.randint(100000, 999999)}",
        "amount": amount,
        "currency": currency
    }
