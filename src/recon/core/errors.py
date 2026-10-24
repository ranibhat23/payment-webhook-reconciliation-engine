"""Custom domain exceptions and error codes for the reconciliation engine."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    # Signature & Security
    MISSING_SIGNATURE = "MISSING_SIGNATURE"
    MALFORMED_SIGNATURE = "MALFORMED_SIGNATURE"
    TIMESTAMP_OUT_OF_TOLERANCE = "TIMESTAMP_OUT_OF_TOLERANCE"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"

    # Ingestion & Validation
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"
    INVALID_CURRENCY = "INVALID_CURRENCY"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    IDEMPOTENCY_COLLISION = "IDEMPOTENCY_COLLISION"

    # Configuration & Internal
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"


class AppError(Exception):
    """Base application exception."""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.CONFIGURATION_ERROR) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ConfigurationError(AppError):
    """Raised when environment variables or required secrets are unconfigured."""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.CONFIGURATION_ERROR) -> None:
        super().__init__(message, code=code)


class InvalidSignatureError(AppError):
    """Raised when HMAC signature verification fails or header is malformed."""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.INVALID_SIGNATURE) -> None:
        super().__init__(message, code=code)


class InvalidPayloadError(AppError):
    """Raised when incoming JSON fails schema or business rules."""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.MALFORMED_PAYLOAD) -> None:
        super().__init__(message, code=code)


class ConflictError(AppError):
    """Raised on idempotency collisions or conflicting payload replays."""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.IDEMPOTENCY_COLLISION) -> None:
        super().__init__(message, code=code)