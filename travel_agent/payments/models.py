from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


_ISO_4217_WHITELIST = {
    "usd", "eur", "gbp", "jpy", "cad", "aud", "chf", "cny", "sek", "nok", "dkk", "nzd", "sgd",
    "hkd", "krw", "inr", "mxn", "brl", "zar", "pln", "czk", "huf", "thb", "ils", "myr", "rub",
}


class CheckoutRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Amount in major currency units (e.g. 100.00 for $100).")
    currency: str = Field(..., min_length=3, max_length=3)
    description: str = Field(..., min_length=1, max_length=300)
    customer_email: EmailStr
    booking_id: str = Field(..., min_length=1, max_length=128)
    metadata: Dict[str, str] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def _currency_lower_and_valid(cls, v: str) -> str:
        lc = v.lower()
        if lc not in _ISO_4217_WHITELIST:
            raise ValueError(f"currency must be a supported ISO 4217 code, got {v!r}")
        return lc


class CheckoutResponse(BaseModel):
    session_id: str
    booking_id: str
    url: str
    expires_at: Optional[int] = None
    status: PaymentStatus = PaymentStatus.PENDING


@dataclass
class PaymentRecord:
    """Server-side record of a payment session."""
    session_id: str
    booking_id: str
    amount: float
    currency: str
    status: PaymentStatus
    customer_email: str
    metadata: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    payment_intent_id: Optional[str] = None
    amount_paid: Optional[float] = None
    created_at: float = 0.0
    updated_at: float = 0.0
