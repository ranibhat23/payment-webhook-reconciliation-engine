"""Inbound payment provider webhook endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from recon.api.deps import get_webhook_service
from recon.services.signature import SIGNATURE_HEADER
from recon.services.webhook_ingestion import WebhookIngestionService

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("/payments", status_code=status.HTTP_200_OK)
async def ingest_payment_webhook(
    request: Request,
    service: Annotated[WebhookIngestionService, Depends(get_webhook_service)],
    x_webhook_signature: Annotated[str | None, Header(alias=SIGNATURE_HEADER)] = None,
) -> dict[str, str]:
    """Ingest, verify, and reconcile external payment webhooks."""
    raw_body = await request.body()
    result = service.ingest(raw_body=raw_body, signature_header=x_webhook_signature)
    return result