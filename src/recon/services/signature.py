"""HMAC-SHA256 webhook signature verification.

Simulates the scheme popularised by Stripe. The provider sends one header:

    X-Webhook-Signature: t=<unix seconds>,v1=<hex hmac>[,v1=<hex hmac>...]

where the HMAC is SHA-256 over  b"<t>." + <raw request body>  keyed with the shared secret.
Binding the timestamp into the signed bytes plus a tolerance window defeats replay of a
captured request; several `v1` values allow zero-downtime secret rotation. Unknown schemes
(e.g. `v0=`) are ignored for forward compatibility.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable
from dataclasses import dataclass

from recon.core.errors import ConfigurationError, ErrorCode, InvalidSignatureError

SIGNATURE_HEADER = "X-Webhook-Signature"
SIGNATURE_SCHEME = "v1"
MAX_HEADER_LENGTH = 1024
MAX_CANDIDATE_SIGNATURES = 5


def compute_signature(secret: str, timestamp: int, payload: bytes) -> str:
    signed_payload = f"{timestamp}.".encode("ascii") + payload
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def build_signature_header(secret: str, payload: bytes, *, timestamp: int | None = None) -> str:
    """Produce a valid header. Used by tests and by anyone simulating a provider."""
    ts = int(time.time()) if timestamp is None else timestamp
    return f"t={ts},{SIGNATURE_SCHEME}={compute_signature(secret, ts, payload)}"


@dataclass(frozen=True, slots=True)
class ParsedSignature:
    timestamp: int
    signatures: tuple[str, ...]


def _malformed(reason: str) -> InvalidSignatureError:
    return InvalidSignatureError(
        f"Malformed signature header: {reason}", code=ErrorCode.MALFORMED_SIGNATURE
    )


def parse_signature_header(header: str) -> ParsedSignature:
    if len(header) > MAX_HEADER_LENGTH:
        raise _malformed("header too long")

    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        key, separator, value = part.strip().partition("=")
        if not separator:
            raise _malformed("expected key=value pairs")
        if key == "t":
            if timestamp is not None:
                raise _malformed("duplicate timestamp")
            # isascii() first: str.isdigit() also accepts characters int() cannot parse.
            if not (value.isascii() and value.isdigit()):
                raise _malformed("timestamp must be an integer")
            timestamp = int(value)
        elif key == SIGNATURE_SCHEME:
            signatures.append(value)

    if timestamp is None:
        raise _malformed("missing timestamp")
    if not signatures:
        raise _malformed(f"no {SIGNATURE_SCHEME} signature")
    if len(signatures) > MAX_CANDIDATE_SIGNATURES:
        raise _malformed("too many signatures")
    return ParsedSignature(timestamp=timestamp, signatures=tuple(signatures))


class SignatureVerifier:
    def __init__(
        self,
        secret: str | None,
        *,
        tolerance_seconds: int = 300,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret = secret
        self._tolerance_seconds = tolerance_seconds
        self._clock = clock

    def verify(self, payload: bytes, header: str | None) -> int:
        """Verify `payload` against the signature header; return the signed timestamp.

        Raises InvalidSignatureError (HTTP 401) with a specific code on any failure, and
        ConfigurationError (HTTP 500) if no secret is configured. We fail *closed*: a
        missing secret never degrades into accepting unsigned traffic.
        """
        if not self._secret:
            raise ConfigurationError("Webhook signing secret is not configured")
        if not header:
            raise InvalidSignatureError(
                f"Missing {SIGNATURE_HEADER} header", code=ErrorCode.MISSING_SIGNATURE
            )

        parsed = parse_signature_header(header)

        if abs(self._clock() - parsed.timestamp) > self._tolerance_seconds:
            raise InvalidSignatureError(
                "Signature timestamp is outside the allowed tolerance",
                code=ErrorCode.TIMESTAMP_OUT_OF_TOLERANCE,
            )

        expected = compute_signature(self._secret, parsed.timestamp, payload).encode("ascii")
        matched = False
        for candidate in parsed.signatures:
            # compare_digest is constant-time; `|=` avoids short-circuiting on a match.
            matched |= hmac.compare_digest(expected, candidate.encode("utf-8"))
        if not matched:
            raise InvalidSignatureError("Signature does not match payload")
        return parsed.timestamp