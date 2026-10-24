"""Common enums and schemas for the reconciliation service."""

from __future__ import annotations

from enum import Enum


class Currency(str, Enum):
    AUD = "AUD"
    EUR = "EUR"
    USD = "USD"
    GBP = "GBP"


# Alias CurrencyEnum to Currency so both import conventions work seamlessly
CurrencyEnum = Currency


class WebhookEventStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    DISPUTED = "DISPUTED"
    REJECTED = "REJECTED"


class DiscrepancyStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


class DiscrepancyType(str, Enum):
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    STATUS_MISMATCH = "STATUS_MISMATCH"
    DUPLICATE_PAYMENT_REF = "DUPLICATE_PAYMENT_REF"
    MISSING_RECORD = "MISSING_RECORD"
    TIMING_MISMATCH = "TIMING_MISMATCH"
    OTHER = "OTHER"