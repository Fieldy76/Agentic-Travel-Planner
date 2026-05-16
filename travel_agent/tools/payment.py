"""LLM-facing payment tools backed by PaymentService + Stripe Checkout.

Two tools:
  - create_payment_session: create a Stripe Checkout session, return the hosted URL
    for the user to complete payment on Stripe's page.
  - get_payment_status: query the current status of a previously created session.

The agent must hand the URL to the user. There is no server-side card
collection and no automatic confirmation — actual payment happens on
Stripe's hosted page (SCA/3DS handled).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from pydantic import ValidationError

from ..config import Config
from ..payments import (
    CheckoutRequest,
    PaymentService,
    build_stripe_client,
)

logger = logging.getLogger(__name__)


_service: Optional[PaymentService] = None


def get_payment_service() -> PaymentService:
    """Lazily build the singleton PaymentService."""
    global _service
    if _service is None:
        client = build_stripe_client()
        _service = PaymentService(client, app_url=Config.APP_URL)
    return _service


def reset_payment_service() -> None:
    """Reset the singleton (test helper)."""
    global _service
    _service = None


async def create_payment_session(
    amount: float,
    currency: str,
    description: str,
    customer_email: str,
    booking_id: str,
) -> Dict[str, Any]:
    """Create a Stripe Checkout session for a charge YOU collect directly.

    NOTE: Most bookings in this app go through partner deeplinks (Aviasales,
    Hotellook, RentalCars). Only call this tool when the user explicitly wants
    to be charged directly through this app (e.g. a concierge/service fee).

    Args:
        amount: Amount in major currency units (e.g. 25.00 for $25).
        currency: 3-letter ISO 4217 (e.g. usd, eur, gbp).
        description: Short human-readable description (shown on the receipt).
        customer_email: Customer email for receipt + Stripe Checkout prefill.
        booking_id: Stable identifier used as Stripe idempotency key. Re-calling
            with the same booking_id returns the same session, never double-charging.

    Returns:
        {session_id, booking_id, url, expires_at, status}
        The agent MUST present `url` to the user.
    """
    try:
        request = CheckoutRequest(
            amount=amount,
            currency=currency,
            description=description,
            customer_email=customer_email,
            booking_id=booking_id,
        )
    except ValidationError as e:
        return {"error": "validation_error", "details": e.errors()}

    response = await get_payment_service().create_checkout(request)
    return {
        "session_id": response.session_id,
        "booking_id": response.booking_id,
        "url": response.url,
        "expires_at": response.expires_at,
        "status": response.status.value,
        "note": "Present `url` to the user. Payment is completed on Stripe's hosted page.",
    }


async def get_payment_status(session_id: str) -> Dict[str, Any]:
    """Look up the current status of a previously created payment session.

    Returns {session_id, booking_id, status, amount, currency, amount_paid?}.
    status is one of: pending, succeeded, failed, cancelled, expired, unknown.
    """
    return await get_payment_service().get_status(session_id)
