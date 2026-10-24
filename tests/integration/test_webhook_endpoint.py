"""Integration tests for inbound payment webhook verification and idempotency."""

from __future__ import annotations

import time
from decimal import Decimal
from fastapi.testclient import TestClient
from recon.main import app
from recon.config import get_settings
from recon.services.signature import build_signature_header

client = TestClient(app)
settings = get_settings()


def test_health_check() -> None:
    """Ensure /health endpoint returns 200 and reports database connected."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}


def test_webhook_ingestion_success() -> None:
    """Test valid signed payment event is ingested and settled."""
    payload_dict = {
        "event_id": f"evt_success_{int(time.time())}",
        "idempotency_key": f"idemp_{int(time.time())}_key123",
        "payment_reference": f"pay_{int(time.time())}",
        "amount": 250.75,
        "currency": "AUD",
        "source_account": "ACC_AUD_1234",
        "destination_account": "ACC_AUD_5678",
    }
    raw_body = str(payload_dict).replace("'", '"').encode("utf-8")
    sig_header = build_signature_header(secret=settings.WEBHOOK_SECRET, payload=raw_body)

    response = client.post(
        "/api/v1/webhooks/payments",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": sig_header,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["event_id"] == payload_dict["event_id"]


def test_webhook_missing_signature_fails() -> None:
    """Ingestion without X-Webhook-Signature header must return 401."""
    raw_body = b'{"event_id": "test_1", "idempotency_key": "12345678"}'
    response = client.post(
        "/api/v1/webhooks/payments",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 401
    assert "MISSING_SIGNATURE" in response.json().get("error_code", "")


def test_webhook_invalid_signature_fails() -> None:
    """Ingestion with forged/mismatched signature must return 401."""
    raw_body = b'{"event_id": "test_2", "idempotency_key": "12345678"}'
    response = client.post(
        "/api/v1/webhooks/payments",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Signature": "t=1700000000,v1=forged_signature_hex_value",
        },
    )
    assert response.status_code == 401


def test_webhook_idempotency_replay() -> None:
    """Sending the exact same signed event twice returns replayed status (idempotent)."""
    ts = int(time.time())
    payload_dict = {
        "event_id": f"evt_idemp_{ts}",
        "idempotency_key": f"idemp_key_unique_{ts}",
        "payment_reference": f"pay_idemp_{ts}",
        "amount": 99.00,
        "currency": "EUR",
    }
    raw_body = str(payload_dict).replace("'", '"').encode("utf-8")
    sig_header = build_signature_header(secret=settings.WEBHOOK_SECRET, payload=raw_body)
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": sig_header,
    }

    # First delivery -> processed
    first_res = client.post("/api/v1/webhooks/payments", content=raw_body, headers=headers)
    assert first_res.status_code == 200
    assert first_res.json()["status"] == "processed"

    # Second delivery (replay) -> returned as replayed
    second_res = client.post("/api/v1/webhooks/payments", content=raw_body, headers=headers)
    assert second_res.status_code == 200
    assert second_res.json()["status"] == "replayed"