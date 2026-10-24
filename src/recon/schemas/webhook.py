"""Pydantic schemas for inbound webhook event payloads."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from recon.schemas.common import CurrencyEnum


class InboundWebhookPayload(BaseModel):
    event_id: str = Field(..., description="Unique event identifier from the provider")
    idempotency_key: str = Field(..., min_length=8, description="Client idempotency key")
    payment_reference: str = Field(..., description="Business reference for the payment")
    amount: Decimal = Field(..., gt=0, description="Transaction amount, strictly greater than 0")
    currency: str = Field(..., description="Currency code (AUD, EUR, USD, GBP)")
    source_account: Optional[str] = None
    destination_account: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        code = v.upper()
        # Verify currency against standard supported codes
        allowed = {c.value for c in CurrencyEnum} if hasattr(CurrencyEnum, "__iter__") else {"AUD", "EUR", "USD", "GBP"}
        if code not in allowed:
            raise ValueError(f"Currency '{v}' is not supported. Must be one of {allowed}")
        return code