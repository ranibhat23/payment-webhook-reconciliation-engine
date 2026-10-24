"""Orchestrates incoming webhook validation, persistence, and deduplication."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from recon.core.errors import ConflictError, ErrorCode, InvalidPayloadError
from recon.core.logging import get_logger
from recon.core.money import Money
from recon.db.models import Discrepancy, Payment, WebhookEvent
from recon.repositories.payments import DiscrepancyRepository, PaymentRepository
from recon.repositories.webhook_events import WebhookEventRepository
from recon.schemas.common import Currency, DiscrepancyStatus, PaymentStatus, WebhookEventStatus
from recon.schemas.webhook import InboundWebhookPayload
from recon.services.signature import SignatureVerifier

logger = get_logger(__name__)


class WebhookIngestionService:
    def __init__(
        self,
        verifier: SignatureVerifier,
        event_repo: WebhookEventRepository,
        payment_repo: PaymentRepository,
        discrepancy_repo: DiscrepancyRepository,
    ) -> None:
        self._verifier = verifier
        self._event_repo = event_repo
        self._payment_repo = payment_repo
        self._discrepancy_repo = discrepancy_repo

    def ingest(
        self,
        raw_body: bytes,
        signature_header: str | None,
        provider: str = "stripe",
    ) -> dict[str, Any]:
        """Verify, deduplicate, and record an inbound webhook."""
        # 1. Verify cryptographic signature & timestamp tolerance
        self._verifier.verify(raw_body, signature_header)

        # 2. Parse JSON payload
        try:
            payload_dict = json.loads(raw_body.decode("utf-8"))
            parsed_payload = InboundWebhookPayload.model_validate(payload_dict)
        except Exception as exc:
            logger.warning("Malformed webhook payload received", exc_info=exc)
            raise InvalidPayloadError(
                f"Invalid webhook payload: {exc}", code=ErrorCode.MALFORMED_PAYLOAD
            ) from exc

        event_id = parsed_payload.event_id
        idempotency_key = parsed_payload.idempotency_key
        event_type = payload_dict.get("event_type", "payment.succeeded")

        # 3. Check for duplicates / replay attacks via WebhookEvent ledger
        existing_events = self._event_repo.find_existing(provider, event_id, idempotency_key)
        if existing_events:
            first_seen = existing_events[0]
            # Idempotent replay: exact same event_id and idempotency_key
            if (
                first_seen.event_id == event_id
                and first_seen.idempotency_key == idempotency_key
            ):
                logger.info(
                    "Idempotent replay detected for event_id=%s, key=%s",
                    event_id,
                    idempotency_key,
                )
                return {
                    "status": "replayed",
                    "event_id": event_id,
                    "message": "Event already processed",
                }

            # Conflicting event reuse
            raise ConflictError(
                "Idempotency key collision or conflicting event payload",
                code=ErrorCode.IDEMPOTENCY_COLLISION,
            )

        # Convert amount into integer minor units using Money value object
        currency_enum = Currency(parsed_payload.currency)
        money_obj = Money.of(parsed_payload.amount, currency_enum)
        amount_minor = money_obj.to_minor_units()
        now_utc = datetime.now(timezone.utc)

        # 4. Record new WebhookEvent (providing occurred_at, payment_status, event_type)
        webhook_event = WebhookEvent(
            provider=provider,
            event_id=event_id,
            idempotency_key=idempotency_key,
            event_type=event_type,
            provider_payment_id=parsed_payload.payment_reference,
            amount_minor=amount_minor,
            currency=currency_enum,
            payment_status=PaymentStatus.SUCCEEDED,
            occurred_at=parsed_payload.timestamp or now_utc,
            payload=payload_dict,
            status=WebhookEventStatus.PROCESSED,
        )
        stored_event, _ = self._event_repo.add_if_absent(webhook_event)

        # 5. Extract and persist Payment state
        payment = Payment(
            provider=provider,
            provider_payment_id=parsed_payload.payment_reference,
            amount_minor=amount_minor,
            currency=currency_enum,
            status=PaymentStatus.SUCCEEDED,
        )
        stored_payment, payment_created = self._payment_repo.add_if_absent(payment)

        # 6. Flag discrepancy if duplicate payment reference occurred under new event
        if not payment_created:
            fingerprint = f"duplicate_payment:{provider}:{parsed_payload.payment_reference}"
            discrepancy = Discrepancy(
                payment_id=stored_payment.id,
                fingerprint=fingerprint,
                status=DiscrepancyStatus.OPEN,
            )
            self._discrepancy_repo.add_if_absent(discrepancy)

        return {
            "status": "processed",
            "event_id": event_id,
            "payment_id": str(stored_payment.id),
        }