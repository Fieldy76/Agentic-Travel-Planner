"""Stripe SDK adapter.

Two implementations:
  - StripeClient: real Stripe Checkout sessions + webhook verification.
  - StripeMockClient: in-memory, no network — used when STRIPE_MODE=mock and in tests.

Public surface:
  - create_checkout_session(...)
  - retrieve_session(session_id)
  - verify_webhook(payload, sig_header) -> dict-like event

Errors are mapped to a small set of user-safe messages; raw stripe.error.*
never leaks past this module.
"""

from __future__ import annotations

import logging
import secrets
import time
from typing import Any, Dict, Optional, Protocol

try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:  # pragma: no cover - import guard
    stripe = None
    STRIPE_AVAILABLE = False

from ..config import Config

logger = logging.getLogger(__name__)


class PaymentProviderError(RuntimeError):
    """User-safe payment error. Original cause logged separately."""


class StripeClientProtocol(Protocol):
    def create_checkout_session(
        self,
        *,
        amount_cents: int,
        currency: str,
        description: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        metadata: Dict[str, str],
        idempotency_key: str,
    ) -> Dict[str, Any]: ...

    def retrieve_session(self, session_id: str) -> Dict[str, Any]: ...

    def verify_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]: ...


class StripeClient:
    """Real Stripe Checkout + webhook adapter."""

    def __init__(self, api_key: str, webhook_secret: str):
        if not STRIPE_AVAILABLE:
            raise RuntimeError("stripe SDK not installed")
        if not api_key:
            raise RuntimeError("Stripe api_key is required")
        stripe.api_key = api_key
        self._webhook_secret = webhook_secret

    def create_checkout_session(
        self,
        *,
        amount_cents: int,
        currency: str,
        description: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        metadata: Dict[str, str],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{
                    "price_data": {
                        "currency": currency,
                        "product_data": {"name": description},
                        "unit_amount": amount_cents,
                    },
                    "quantity": 1,
                }],
                success_url=success_url,
                cancel_url=cancel_url,
                customer_email=customer_email,
                metadata=metadata,
                payment_intent_data={"metadata": metadata},
                idempotency_key=idempotency_key,
            )
        except stripe.error.IdempotencyError as e:
            # Same idempotency key with different params — log and re-raise as user-safe error.
            logger.error("Stripe idempotency conflict for key=%s: %s", idempotency_key, e)
            raise PaymentProviderError("Duplicate payment request with different parameters.") from e
        except stripe.error.CardError as e:
            logger.warning("Stripe card error: %s", e)
            raise PaymentProviderError(e.user_message or "Card was declined.") from e
        except stripe.error.RateLimitError as e:
            logger.error("Stripe rate limit: %s", e)
            raise PaymentProviderError("Payment service is busy. Please retry in a moment.") from e
        except stripe.error.InvalidRequestError as e:
            logger.error("Stripe invalid request: %s", e)
            raise PaymentProviderError("Invalid payment request.") from e
        except stripe.error.AuthenticationError as e:
            logger.error("Stripe auth error: %s", e)
            raise PaymentProviderError("Payment provider misconfigured.") from e
        except stripe.error.APIConnectionError as e:
            logger.error("Stripe network error: %s", e)
            raise PaymentProviderError("Payment service unreachable. Please retry.") from e
        except stripe.error.StripeError as e:
            logger.exception("Stripe error")
            raise PaymentProviderError("Payment could not be initiated.") from e

        return {
            "id": session.id,
            "url": session.url,
            "expires_at": session.expires_at,
            "status": session.status,
            "payment_intent": session.payment_intent,
        }

    def retrieve_session(self, session_id: str) -> Dict[str, Any]:
        try:
            session = stripe.checkout.Session.retrieve(session_id)
        except stripe.error.InvalidRequestError as e:
            raise PaymentProviderError("Unknown payment session.") from e
        except stripe.error.StripeError as e:
            logger.exception("Stripe retrieve error")
            raise PaymentProviderError("Payment service unavailable.") from e
        return {
            "id": session.id,
            "status": session.status,
            "payment_status": session.payment_status,
            "amount_total": session.amount_total,
            "currency": session.currency,
            "metadata": dict(session.metadata or {}),
            "payment_intent": session.payment_intent,
        }

    def verify_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, self._webhook_secret)
        except stripe.error.SignatureVerificationError as e:
            logger.warning("Webhook signature verification failed")
            raise PaymentProviderError("Invalid webhook signature.") from e
        except ValueError as e:
            raise PaymentProviderError("Malformed webhook payload.") from e
        return event


class StripeMockClient:
    """In-memory Stripe stand-in. Use when STRIPE_MODE=mock or in tests.

    Sessions are created with synthetic IDs and never auto-complete; tests
    (or scripted demos) drive state changes by calling `simulate_completion`
    which builds a webhook-style event payload that PaymentService can handle.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def create_checkout_session(
        self,
        *,
        amount_cents: int,
        currency: str,
        description: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        metadata: Dict[str, str],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        existing_id = next(
            (sid for sid, s in self._sessions.items() if s["idempotency_key"] == idempotency_key),
            None,
        )
        if existing_id is not None:
            return self._sessions[existing_id]

        sid = f"cs_mock_{secrets.token_urlsafe(12)}"
        pi = f"pi_mock_{secrets.token_urlsafe(12)}"
        session = {
            "id": sid,
            "url": f"https://mock.stripe.test/checkout/{sid}",
            "expires_at": int(time.time()) + 1800,
            "status": "open",
            "payment_status": "unpaid",
            "amount_total": amount_cents,
            "currency": currency,
            "metadata": dict(metadata),
            "payment_intent": pi,
            "idempotency_key": idempotency_key,
            "customer_email": customer_email,
            "description": description,
        }
        self._sessions[sid] = session
        return session

    def retrieve_session(self, session_id: str) -> Dict[str, Any]:
        if session_id not in self._sessions:
            raise PaymentProviderError("Unknown payment session.")
        return self._sessions[session_id]

    def verify_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:  # noqa: ARG002 — mock
        import json
        try:
            return json.loads(payload)
        except json.JSONDecodeError as e:
            raise PaymentProviderError("Malformed mock webhook payload.") from e

    # Test helper
    def simulate_completion(self, session_id: str, *, status: str = "complete", payment_status: str = "paid") -> Dict[str, Any]:
        if session_id not in self._sessions:
            raise PaymentProviderError("Unknown session")
        self._sessions[session_id]["status"] = status
        self._sessions[session_id]["payment_status"] = payment_status
        return {
            "id": f"evt_mock_{secrets.token_urlsafe(8)}",
            "type": "checkout.session.completed" if payment_status == "paid" else "checkout.session.async_payment_failed",
            "data": {"object": self._sessions[session_id]},
        }


def build_stripe_client() -> StripeClientProtocol:
    """Factory based on Config.STRIPE_MODE."""
    if Config.STRIPE_MODE == "mock":
        logger.info("Stripe in MOCK mode (no network calls).")
        return StripeMockClient()
    if not STRIPE_AVAILABLE:
        raise RuntimeError("stripe SDK is not installed but STRIPE_MODE != mock")
    if not Config.STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY is required when STRIPE_MODE != mock")
    return StripeClient(Config.STRIPE_SECRET_KEY, Config.STRIPE_WEBHOOK_SECRET or "")
