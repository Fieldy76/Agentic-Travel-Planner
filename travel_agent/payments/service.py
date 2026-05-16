"""Business layer on top of StripeClient.

Owns:
  - in-memory PaymentRecord store (booking_id -> record, session_id -> record)
  - idempotency: same booking_id -> reuses existing Stripe Checkout session
  - webhook deduplication: each event.id is processed at most once
  - asyncio.Lock around the store for race-free updates

Persistence note: state is in-memory only for v1. A persistent backend would
implement the same interface; the surrounding code talks to PaymentService,
not the store directly.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Set

from .models import CheckoutRequest, CheckoutResponse, PaymentRecord, PaymentStatus
from .stripe_client import PaymentProviderError, StripeClientProtocol

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, stripe_client: StripeClientProtocol, *, app_url: str):
        self._stripe = stripe_client
        self._app_url = app_url.rstrip("/")
        self._by_booking: Dict[str, PaymentRecord] = {}
        self._by_session: Dict[str, PaymentRecord] = {}
        self._processed_events: Set[str] = set()
        self._lock = asyncio.Lock()

    def verify_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Verify Stripe signature on a raw webhook payload. Raises on failure."""
        return self._stripe.verify_webhook(payload, sig_header)

    async def create_checkout(self, request: CheckoutRequest) -> CheckoutResponse:
        async with self._lock:
            existing = self._by_booking.get(request.booking_id)
            if existing and existing.status in {PaymentStatus.PENDING, PaymentStatus.SUCCEEDED}:
                logger.info("Reusing payment session for booking_id=%s", request.booking_id)
                return CheckoutResponse(
                    session_id=existing.session_id,
                    booking_id=existing.booking_id,
                    url=existing.url or "",
                    status=existing.status,
                )

        success_url = f"{self._app_url}/payment/success?sid={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{self._app_url}/payment/cancel?sid={{CHECKOUT_SESSION_ID}}"
        metadata = {**request.metadata, "booking_id": request.booking_id}
        amount_cents = int(round(request.amount * 100))

        session = self._stripe.create_checkout_session(
            amount_cents=amount_cents,
            currency=request.currency,
            description=request.description,
            customer_email=str(request.customer_email),
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
            idempotency_key=request.booking_id,
        )

        now = time.time()
        record = PaymentRecord(
            session_id=session["id"],
            booking_id=request.booking_id,
            amount=request.amount,
            currency=request.currency,
            status=PaymentStatus.PENDING,
            customer_email=str(request.customer_email),
            metadata=metadata,
            url=session["url"],
            payment_intent_id=session.get("payment_intent"),
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            self._by_booking[request.booking_id] = record
            self._by_session[session["id"]] = record

        return CheckoutResponse(
            session_id=session["id"],
            booking_id=request.booking_id,
            url=session["url"],
            expires_at=session.get("expires_at"),
            status=PaymentStatus.PENDING,
        )

    async def get_status(self, session_id: str) -> Dict[str, Any]:
        async with self._lock:
            local = self._by_session.get(session_id)
        if local is None:
            return {"session_id": session_id, "status": "unknown", "error": "no such session"}

        # Refresh from Stripe so caller sees newest payment_status even if webhook hasn't arrived.
        try:
            remote = self._stripe.retrieve_session(session_id)
        except PaymentProviderError as e:
            return {
                "session_id": session_id,
                "booking_id": local.booking_id,
                "status": local.status.value,
                "amount": local.amount,
                "currency": local.currency,
                "warning": str(e),
            }

        new_status = _stripe_session_to_status(remote)
        if new_status != local.status:
            async with self._lock:
                local.status = new_status
                local.amount_paid = (remote.get("amount_total") or 0) / 100.0 if new_status == PaymentStatus.SUCCEEDED else local.amount_paid
                local.updated_at = time.time()

        return {
            "session_id": session_id,
            "booking_id": local.booking_id,
            "status": local.status.value,
            "amount": local.amount,
            "currency": local.currency,
            "amount_paid": local.amount_paid,
        }

    async def handle_webhook(self, event: Dict[str, Any]) -> None:
        event_id = event.get("id")
        event_type = event.get("type", "")
        if not event_id:
            logger.warning("Webhook event missing id; ignoring")
            return

        async with self._lock:
            if event_id in self._processed_events:
                logger.info("Skipping already-processed webhook event %s", event_id)
                return
            self._processed_events.add(event_id)

        obj = (event.get("data") or {}).get("object") or {}
        session_id = obj.get("id") or obj.get("payment_intent")
        if not session_id:
            logger.warning("Webhook %s has no session id; ignoring", event_id)
            return

        async with self._lock:
            record = self._by_session.get(session_id)
            if record is None:
                # Could happen if the server restarted; nothing to update.
                logger.info("Webhook for unknown session %s (event=%s)", session_id, event_id)
                return

            if event_type == "checkout.session.completed":
                record.status = PaymentStatus.SUCCEEDED
                record.amount_paid = (obj.get("amount_total") or int(record.amount * 100)) / 100.0
            elif event_type == "checkout.session.async_payment_failed":
                record.status = PaymentStatus.FAILED
            elif event_type == "checkout.session.expired":
                record.status = PaymentStatus.EXPIRED
            elif event_type == "payment_intent.payment_failed":
                record.status = PaymentStatus.FAILED
            else:
                logger.debug("Webhook %s of type %s — no state change", event_id, event_type)
                return

            record.updated_at = time.time()
            logger.info(
                "Webhook %s -> booking %s now %s",
                event_id, record.booking_id, record.status.value,
            )


def _stripe_session_to_status(remote: Dict[str, Any]) -> PaymentStatus:
    status = (remote.get("status") or "").lower()
    payment_status = (remote.get("payment_status") or "").lower()
    if status == "complete" and payment_status == "paid":
        return PaymentStatus.SUCCEEDED
    if status == "expired":
        return PaymentStatus.EXPIRED
    if payment_status in {"unpaid", "no_payment_required"}:
        return PaymentStatus.PENDING
    if payment_status == "failed":
        return PaymentStatus.FAILED
    return PaymentStatus.PENDING
