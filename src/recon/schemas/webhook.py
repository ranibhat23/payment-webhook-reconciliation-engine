"""Ingestion schemas for incoming payment webhooks.

`PaymentWebhookIn` is the *normalised* shape. Provider adapters (src/recon/providers/)
translate each provider's native payload into this before it reaches the service layer.
"""

from __future__ import annotations

from datetime import timezone
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from recon.core.money import Money
from recon.schemas.common import Currency, PaymentStatus


class PaymentWebhookIn(BaseModel):
    model_config = ConfigDict(
        extra="ignore",  # providers add fields; the raw body is stored separately
        str_strip_whitespace=True,
        frozen=True,
    )

    provider: str = Field(min_length=1, max_length=50)
    event_id: str = Field(min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=100)
    payment_id: str = Field(min_length=1, max_length=255, description="Provider's payment reference")
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: Currency
    status: PaymentStatus
    timestamp: AwareDatetime  # timezone required; naive datetimes are rejected
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider")
    @classmethod
    def _lowercase_provider(cls, value: str) -> str:
        return value.lower()

    @field_validator("timestamp")
    @classmethod
    def _to_utc(cls, value: AwareDatetime) -> AwareDatetime:
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _amount_fits_currency(self) -> Self:
        # Re-checks precision against the specific currency's exponent via Money, so adding
        # a zero-decimal currency later (e.g. JPY) can't let 10.50 JPY through.
        try:
            Money(self.amount, self.currency)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @property
    def money(self) -> Money:
        return Money(self.amount, self.currency)


class WebhookAck(BaseModel):
    """Response body returned to the provider after we accept (or de-duplicate) an event."""

    event_id: str
    status: Literal["accepted", "duplicate"]
    received_at: AwareDatetime