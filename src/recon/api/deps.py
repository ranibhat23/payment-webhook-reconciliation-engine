"""FastAPI dependency injection wiring."""

from __future__ import annotations

from typing import Annotated, Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from recon.config import get_settings
from recon.db.session import get_db
from recon.repositories.payments import DiscrepancyRepository, PaymentRepository
from recon.repositories.webhook_events import WebhookEventRepository
from recon.services.signature import SignatureVerifier
from recon.services.webhook_ingestion import WebhookIngestionService


def get_signature_verifier() -> SignatureVerifier:
    settings = get_settings()
    return SignatureVerifier(
        secret=settings.WEBHOOK_SECRET,
        tolerance_seconds=settings.WEBHOOK_TOLERANCE_SECONDS,
    )


def get_webhook_service(
    db: Annotated[Session, Depends(get_db)],
    verifier: Annotated[SignatureVerifier, Depends(get_signature_verifier)],
) -> WebhookIngestionService:
    event_repo = WebhookEventRepository(db)
    payment_repo = PaymentRepository(db)
    discrepancy_repo = DiscrepancyRepository(db)
    return WebhookIngestionService(
        verifier=verifier,
        event_repo=event_repo,
        payment_repo=payment_repo,
        discrepancy_repo=discrepancy_repo,
    )