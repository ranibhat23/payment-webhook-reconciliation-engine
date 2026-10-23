"""Shared enums and base schema classes.

This module is deliberately a *leaf*: it imports nothing from the rest of `recon`, so
`core`, `db` and `schemas` can all depend on it without creating import cycles.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Currency(StrEnum):
    AUD = "AUD"
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class WebhookEventStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class DiscrepancyType(StrEnum):
    MISSING_PAYMENT = "missing_payment"  # webhook references a payment we don't have
    MISSING_WEBHOOK = "missing_webhook"  # payment exists but no webhook ever arrived
    AMOUNT_MISMATCH = "amount_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    STATUS_MISMATCH = "status_mismatch"
    INVALID_TRANSITION = "invalid_transition"  # e.g. FAILED -> SUCCEEDED
    DUPLICATE_EVENT = "duplicate_event"


class DiscrepancyStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ORMSchema(BaseModel):
    """Base for response schemas that are built straight from ORM objects."""

    model_config = ConfigDict(from_attributes=True)