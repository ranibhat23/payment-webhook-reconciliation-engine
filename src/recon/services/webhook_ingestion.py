"""Orchestrates incoming webhook validation, persistence, and deduplication."""

from __future__ import annotations

import json
import uuid
from typing import Any

from recon.core.errors import ConflictError, ErrorCode, InvalidPayloadError
from recon.core.logging import get_logger
from recon.db.models import Discrepancy, Payment, WebhookEvent
from recon.repositories.payments import DiscrepancyRepository, PaymentRepository
from recon.repositories.webhook_events import WebhookEventRepository
from recon.schemas.common import DiscrepancyStatus, PaymentStatus, WebhookEventStatus
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

        # 4. Record new WebhookEvent
        webhook_event = WebhookEvent(
            event_id=event_id,
            idempotency_key=idempotency_key,
            provider=provider,
            payload=payload_dict,
            status=WebhookEventStatus.PROCESSED,
        )
        stored_event, _ = self._event_repo.add_if_absent(webhook_event)

        # 5. Extract and persist Payment state
        payment = Payment(
            provider=provider,
            provider_payment_id=parsed_payload.payment_reference,
            amount=parsed_payload.amount,
            currency=parsed_payload.currency,
            status=PaymentStatus.SETTLED,
            source_account=parsed_payload.source_account,
            destination_account=parsed_payload.destination_account,
        )
        stored_payment, payment_created = self._payment_repo.add_if_absent(payment)

        # 6. Flag discrepancy if duplicate payment reference occurred under new event
        if not payment_created:
            fingerprint = f"duplicate_payment:{provider}:{parsed_payload.payment_reference}"
            discrepancy = Discrepancy(
                payment_id=stored_payment.id,
                fingerprint=fingerprint,
                code="DUPLICATE_PAYMENT_REF",
                description=f"Payment ref {parsed_payload.payment_reference} already exists",
                status=DiscrepancyStatus.OPEN,
            )
            self._discrepancy_repo.add_if_absent(discrepancy)

        return {
            "status": "processed",
            "event_id": event_id,
            "payment_id": str(stored_payment.id),
        }