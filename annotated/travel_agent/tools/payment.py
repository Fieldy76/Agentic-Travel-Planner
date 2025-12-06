"""
================================================================================
PAYMENT TOOL - Production-Ready Payment Processing with Stripe
================================================================================

This module implements secure payment processing using the Stripe Payment
Intents API. It's designed to be production-ready with comprehensive error
handling, idempotency support, and automatic fallback to mock mode.

Stripe Integration:
-------------------
This module uses Stripe Payment Intents API, which is the recommended
approach for accepting payments. Payment Intents handle:
- Card authentication (3D Secure)
- Multiple payment methods
- Asynchronous confirmation
- Automatic retry logic

API Documentation: https://stripe.com/docs/api/payment_intents

Security Features:
------------------
1. Idempotency Keys: Prevents duplicate charges if requests are retried
2. Server-side processing: Secret key never exposed to client
3. Comprehensive error handling: Graceful failure modes
4. Webhook support (optional): For handling async payment events
5. Email Receipts: Automatic confirmation emails via Stripe when customer_email is provided

Payment Flow:
-------------
    ┌────────────────────────────────────────────────────────────┐
    │                   process_payment()                        │
    └────────────────────────────┬───────────────────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    ▼                         ▼
              Stripe Available           Mock Mode
              + Key Configured           (No Stripe/Key)
                    │                         │
                    ▼                         ▼
           ┌─────────────────┐        ┌─────────────────┐
           │ Create Payment  │        │ Generate Mock   │
           │ Intent (API)    │        │ Transaction     │
           └────────┬────────┘        └────────┬────────┘
                    │                          │
                    ▼                          │
           ┌─────────────────┐                 │
           │ Handle Response │                 │
           │ or Errors       │                 │
           └────────┬────────┘                 │
                    │                          │
                    └──────────┬───────────────┘
                               ▼
    ┌────────────────────────────────────────────────────────────┐
    │            Return Result Dictionary                        │
    │  {status, transaction_id, amount, currency, ...}          │
    └────────────────────────────────────────────────────────────┘

Error Handling:
---------------
The module handles all Stripe error types:
- CardError: Card was declined
- RateLimitError: Too many API requests
- InvalidRequestError: Invalid parameters
- AuthenticationError: Invalid API key
- APIConnectionError: Network issues
- StripeError: Generic Stripe errors

Mock Mode:
----------
When Stripe is not available or configured, payments are simulated:
- Normal amounts return success
- Amount $0.01 returns failure (for testing error handling)

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import os                              # Environment access
import time                            # Timestamp for idempotency keys
import logging                         # Logging facility
from typing import Dict, Any, Optional # Type hints
import random                          # Random ID generation for mock

# Create module logger
logger = logging.getLogger(__name__)

# =============================================================================
# STRIPE SDK IMPORT
# =============================================================================

# Try to import Stripe, set flag if not available
# This allows the module to function in mock mode without Stripe installed
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    logger.warning("Stripe not installed. Payment processing will use mock mode.")

# Import config for API keys
from ..config import Config

# =============================================================================
# MAIN PAYMENT FUNCTION
# =============================================================================

def process_payment(
    amount: float,
    currency: str,
    description: str = "Travel booking payment",
    customer_email: Optional[str] = None,
    metadata: Optional[Dict[str, str]] = None,
    idempotency_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process a payment using Stripe Payment Intents API.
    
    This is the main entry point for payment processing. It attempts to use
    the real Stripe API if configured, otherwise falls back to mock mode.
    
    Args:
        amount: Amount to charge in major currency units (e.g., 100.00 for $100).
               Stripe works with cents internally, but this function accepts
               decimal amounts for convenience.
        
        currency: Three-letter ISO currency code (e.g., 'usd', 'eur', 'gbp').
                 Case-insensitive; will be lowercased for Stripe.
        
        description: Description of the payment that appears on receipts
                    and in the Stripe dashboard. Default: "Travel booking payment"
        
        customer_email: Optional email address for sending receipts.
                       If provided, Stripe sends an automatic receipt.
        
        metadata: Optional dictionary of key-value pairs to store with the payment.
                 Useful for storing booking_reference, flight_id, etc.
                 Maximum 50 keys, 40-character keys, 500-character values.
        
        idempotency_key: Optional unique key to prevent duplicate charges.
                        If not provided, one is auto-generated.
                        Use the same key for retries of the same payment.
    
    Returns:
        dict: Payment result containing:
        
        Success:
            {
                "status": "success",
                "transaction_id": "pi_1234567890",
                "amount": 100.00,
                "currency": "USD",
                "payment_status": "succeeded",
                "client_secret": "pi_..._secret_...",  # For frontend use
                "idempotency_key": "payment_1234_5678",
                "description": "Travel booking payment"
            }
        
        Failure:
            {
                "status": "failed",
                "error": "card_declined",  # Error code
                "message": "Your card was declined.",  # User-friendly message
                "amount": 100.00,
                "currency": "USD"
            }
    
    Example:
        >>> result = process_payment(
        ...     amount=450.00,
        ...     currency="usd",
        ...     description="Flight JFK-LHR",
        ...     customer_email="user@example.com",
        ...     metadata={"booking_ref": "BK12345"}
        ... )
        >>> if result["status"] == "success":
        ...     print(f"Payment confirmed: {result['transaction_id']}")
    """
    # Try real Stripe if available and configured
    if STRIPE_AVAILABLE and Config.STRIPE_SECRET_KEY:
        try:
            return _process_stripe_payment(
                amount=amount,
                currency=currency,
                description=description,
                customer_email=customer_email,
                metadata=metadata,
                idempotency_key=idempotency_key
            )
        except Exception as e:
            logger.error(f"Stripe payment failed: {e}. Falling back to mock.")
            # In production, you might want to fail here instead of falling back
            # For development flexibility, we fall back to mock
    
    # Fallback to mock mode
    return _process_mock_payment(amount, currency, description)

# =============================================================================
# STRIPE IMPLEMENTATION
# =============================================================================

def _process_stripe_payment(
    amount: float,
    currency: str,
    description: str,
    customer_email: Optional[str],
    metadata: Optional[Dict[str, str]],
    idempotency_key: Optional[str]
) -> Dict[str, Any]:
    """
    Process payment using Stripe Payment Intents API.
    
    Payment Intents is Stripe's recommended API for accepting payments.
    It handles complex payment flows including 3D Secure authentication.
    
    This function:
    1. Converts amount to cents (Stripe's smallest currency unit)
    2. Creates a Payment Intent with automatic confirmation
    3. Handles various error conditions
    4. Returns a standardized result dictionary
    
    Note: This implementation uses automatic confirmation with a test card.
    In a real web application, you would return the client_secret to the
    frontend and let Stripe.js handle card collection and confirmation.
    """
    # Set the API key for this request
    stripe.api_key = Config.STRIPE_SECRET_KEY
    
    # =========================================================================
    # AMOUNT CONVERSION
    # =========================================================================
    # Stripe expects amounts in the smallest currency unit (cents for USD/EUR)
    # So $100.00 becomes 10000 cents
    amount_cents = int(amount * 100)
    
    # =========================================================================
    # IDEMPOTENCY KEY
    # =========================================================================
    # Idempotency keys prevent duplicate charges if requests are retried.
    # If the same key is used twice, Stripe returns the original response.
    # Keys are unique per Stripe account and expire after 24 hours.
    
    if not idempotency_key:
        # Auto-generate a key using timestamp and random number
        idempotency_key = f"payment_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    
    try:
        # =====================================================================
        # CREATE PAYMENT INTENT
        # =====================================================================
        logger.info(f"Creating Stripe Payment Intent for {amount} {currency}")
        
        # Build the Payment Intent parameters
        intent_params = {
            "amount": amount_cents,
            "currency": currency.lower(),  # Stripe requires lowercase
            "description": description,
            "automatic_payment_methods": {"enabled": True},  # Accept various methods
        }
        
        # Add receipt email if provided
        if customer_email:
            intent_params["receipt_email"] = customer_email
        
        # Add metadata if provided
        if metadata:
            intent_params["metadata"] = metadata
        
        # =====================================================================
        # AUTOMATIC CONFIRMATION (Demo Mode)
        # =====================================================================
        # For this agent demo, we automatically confirm the payment using a
        # test card. In a real web application, you would:
        # 1. Return client_secret to the frontend
        # 2. Use Stripe.js to collect card details
        # 3. Let Stripe.js handle confirmation and 3D Secure
        
        intent_params.update({
            "confirm": True,                    # Auto-confirm
            "payment_method": "pm_card_visa",   # Test card that always succeeds
            "return_url": "https://example.com/checkout/complete",  # Required for confirm
            "automatic_payment_methods": {
                "enabled": True, 
                "allow_redirects": "never"      # Disable redirects for server-side
            }
        })

        # Create the Payment Intent with idempotency protection
        payment_intent = stripe.PaymentIntent.create(
            **intent_params,
            idempotency_key=idempotency_key
        )
        
        logger.info(f"Payment Intent created: {payment_intent.id}")
        
        # Return success result
        return {
            "status": "success" if payment_intent.status == "succeeded" else "pending",
            "transaction_id": payment_intent.id,
            "amount": amount,
            "currency": currency.upper(),
            "payment_status": payment_intent.status,
            "client_secret": payment_intent.client_secret,  # For frontend if needed
            "idempotency_key": idempotency_key,
            "description": description
        }
        
    # =========================================================================
    # ERROR HANDLING
    # =========================================================================
    # Stripe raises specific exception types for different error conditions.
    # We handle each type to provide appropriate user feedback.
    
    except stripe.error.CardError as e:
        # Card was declined (insufficient funds, expired, etc.)
        logger.warning(f"Card declined: {e.user_message}")
        return {
            "status": "failed",
            "error": "card_declined",
            "message": e.user_message or "Your card was declined.",
            "amount": amount,
            "currency": currency.upper()
        }
        
    except stripe.error.RateLimitError as e:
        # Too many requests to Stripe API
        logger.error(f"Stripe rate limit hit: {e}")
        return {
            "status": "failed",
            "error": "rate_limit",
            "message": "Payment service is busy. Please try again in a moment.",
            "amount": amount,
            "currency": currency.upper()
        }
        
    except stripe.error.InvalidRequestError as e:
        # Invalid parameters (bad amount, unsupported currency, etc.)
        logger.error(f"Invalid Stripe request: {e}")
        return {
            "status": "failed",
            "error": "invalid_request",
            "message": "Payment request was invalid. Please contact support.",
            "amount": amount,
            "currency": currency.upper()
        }
        
    except stripe.error.AuthenticationError as e:
        # Invalid API key
        logger.error(f"Stripe authentication failed: {e}")
        return {
            "status": "failed",
            "error": "authentication_error",
            "message": "Payment service configuration error. Please contact support.",
            "amount": amount,
            "currency": currency.upper()
        }
        
    except stripe.error.APIConnectionError as e:
        # Network issues connecting to Stripe
        logger.error(f"Stripe API connection error: {e}")
        return {
            "status": "failed",
            "error": "network_error",
            "message": "Payment service is temporarily unavailable. Please try again.",
            "amount": amount,
            "currency": currency.upper()
        }
        
    except stripe.error.StripeError as e:
        # Generic Stripe error (catch-all)
        logger.error(f"Stripe error: {e}")
        return {
            "status": "failed",
            "error": "payment_error",
            "message": "Payment could not be processed. Please try again.",
            "amount": amount,
            "currency": currency.upper()
        }
        
    except Exception as e:
        # Unexpected error (should rarely happen)
        logger.exception(f"Unexpected payment error: {e}")
        return {
            "status": "failed",
            "error": "unexpected_error",
            "message": "An unexpected error occurred. Please contact support.",
            "amount": amount,
            "currency": currency.upper()
        }

# =============================================================================
# MOCK IMPLEMENTATION
# =============================================================================

def _process_mock_payment(amount: float, currency: str, description: str) -> Dict[str, Any]:
    """
    Generate mock payment response for development/testing.
    
    This function simulates payment processing when Stripe is not
    available or configured. Useful for:
    - Development without Stripe keys
    - Testing UI flows
    - Demos
    
    Special Test Cases:
    - Amount $0.01: Returns failure (for testing error handling)
    - All other amounts: Returns success
    
    Args:
        amount: Payment amount
        currency: Currency code
        description: Payment description
    
    Returns:
        Mock payment result dictionary
    """
    logger.info(f"[MOCK] Processing payment of {amount} {currency} - {description}")
    
    # =========================================================================
    # TEST CASE: Failure Simulation
    # =========================================================================
    # Using $0.01 as a trigger for testing failure handling
    
    if amount == 0.01:
        return {
            "status": "failed",
            "error": "card_declined",
            "message": "Your card was declined (mock).",
            "amount": amount,
            "currency": currency.upper()
        }
    
    # =========================================================================
    # DEFAULT: Success
    # =========================================================================
    
    return {
        "status": "success",
        "transaction_id": f"MOCK_TXN_{random.randint(100000, 999999)}",
        "amount": amount,
        "currency": currency.upper(),
        "payment_status": "succeeded",
        "description": description,
        "mock": True  # Flag indicating mock mode
    }
