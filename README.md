# Enterprise Payment Webhook & Reconciliation Engine

[![CI Pipeline](https://github.com/ranibhat23/payment-webhook-reconciliation-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/ranibhat23/payment-webhook-reconciliation-engine/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.14-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green)
![Coverage](https://img.shields.io/badge/Coverage-80%25+-brightgreen)
![License](https://img.shields.io/badge/License-MIT-purple)

An enterprise-grade financial transaction ingestion and reconciliation service. Built to simulate high-reliability payment infrastructure used by core banking systems, external payment service providers (PSPs), and payment schemes (e.g., Stripe, SEPA, and Australian NPP rail integrations).

---

## Key Capabilities

- **HMAC-SHA256 Cryptographic Authentication**: Validates external webhook signatures using constant-time string comparison (`hmac.compare_digest`) and a strict 300-second timestamp tolerance window to defeat replay attacks.
- **Strict Idempotency Ledger**: Employs double-layer idempotency (at both the application service layer and database schema level) to guarantee that retransmitted webhooks and network retries never produce duplicate payment settlements.
- **Minor-Unit Financial Precision**: Eliminates floating-point rounding hazards by handling monetary values via an immutable `Money` value object backed by ISO 4217 minor-unit integer storage.
- **Automated Audit & Discrepancy Tracking**: Persists non-blocking discrepancy records and forensic audit trails whenever mismatched currencies, duplicate references, or altered payloads are detected.

---

## System Architecture

```text
 [ External Payment Gateway / Core Banking Rail ]
                        │
                        │ POST /api/v1/webhooks/payments
                        │ (Header: X-Webhook-Signature)
                        ▼
            ┌───────────────────────┐
            │   FastAPI Router      │
            └───────────┬───────────┘
                        │
            ┌───────────▼───────────┐
            │  SignatureVerifier    │ ───► Fails? ──► HTTP 401 Unauthorized
            └───────────┬───────────┘
                        │ (Valid HMAC & Timestamp)
            ┌───────────▼───────────┐
            │ WebhookIngestionSvc   │
            └───────────┬───────────┘
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
┌──────────────────┐          ┌──────────────────┐
│ WebhookEventRepo │          │   PaymentRepo    │
│ (Idempotency)    │          │  (State Engine)  │
└────────┬─────────┘          └────────┬─────────┘
         │                             │
         └──────────────┬──────────────┘
                        │
                        ▼
              [ SQLite / PostgreSQL ]
```

---

## Tech Stack & Design Decisions

| Component             | Technology              | Rationale                                                                                                                                   |
| :-------------------- | :---------------------- | :------------------------------------------------------------------------------------------------------------------------------------------ |
| **API Framework**     | FastAPI                 | High-performance asynchronous execution with native OpenAPI/Swagger documentation.                                                          |
| **Data Validation**   | Pydantic v2             | Strict payload enforcement and ISO 4217 currency validation prior to business logic execution.                                              |
| **Data Access & ORM** | SQLAlchemy 2.0          | Explicit session management with atomic transaction boundaries and migration-ready entity mapping.                                          |
| **Persistence**       | SQLite / PostgreSQL     | Zero-config local development and testing (SQLite), fully compatible with PostgreSQL row-locking (`FOR UPDATE`) for production concurrency. |
| **Testing**           | Pytest, HTTPX, Coverage | Automated integration testing simulating network retries, signature tampering, and idempotency collisions.                                  |
| **CI/CD**             | GitHub Actions          | Automated build validation and test pipeline executed on every branch push and pull request.                                                |

---

## Project Structure

```text
payment-webhook-reconciliation-engine/
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI test workflow
├── src/
│   └── recon/
│       ├── api/
│       │   ├── routes/          # Health and webhook endpoints
│       │   └── deps.py          # FastAPI dependency injection
│       ├── core/
│       │   ├── errors.py        # Domain exceptions & error codes
│       │   ├── logging.py       # Structured console logging
│       │   └── money.py         # Currency & minor-unit precision utilities
│       ├── db/
│       │   ├── models/          # SQLAlchemy ORM database models
│       │   ├── base.py          # Declarative Base metadata
│       │   └── session.py       # Engine & sessionmaker configuration
│       ├── repositories/        # Database query & idempotent persistence layer
│       ├── schemas/             # Pydantic data schemas & enums
│       ├── services/            # HMAC verification & ingestion business logic
│       ├── config.py            # Environment settings (pydantic-settings)
│       └── main.py              # Application entrypoint
├── tests/
│   └── integration/             # Automated test suite
├── pyproject.toml               # Package build configuration & dependencies
└── README.md
```

---

## Local Setup & Quickstart

### Prerequisites

- Python 3.10+
- Git

### 1. Clone the Repository

```powershell
git clone [https://github.com/ranibhat23/payment-webhook-reconciliation-engine.git](https://github.com/ranibhat23/payment-webhook-reconciliation-engine.git)
cd payment-webhook-reconciliation-engine
```

### 2. Create and Activate Virtual Environment

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

Install the package in editable mode with development and test tooling:

```powershell
pip install -e ".[dev]"
```

_(If your shell doesn't parse extras quotes, use `pip install -e .`)_

---

## Running the Application

Start the local development server with live reload:

```powershell
uvicorn recon.main:app --reload
```

- **Interactive API Docs (Swagger)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Alternative API Docs (ReDoc)**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## Testing & Verification

### Run Automated Tests

Execute the integration test suite and generate coverage reports:

```powershell
pytest -v
```

### Manual Endpoint Verification

#### 1. Service Health Check

Verify that the FastAPI service and database connection are live:

```powershell
curl.exe [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
```

**Expected Response:**

```json
{ "status": "healthy", "database": "connected" }
```

#### 2. Sending an Inbound Payment Webhook

External gateways sign requests with a timestamp and HMAC SHA-256 signature (`X-Webhook-Signature: t=<timestamp>,v1=<signature>`).

**Test unauthorized rejection (timestamp out of tolerance):**

```powershell
curl.exe -X POST "http://127.0.0.1:8000/api/v1/webhooks/payments" `
  -H "Content-Type: application/json" `
  -H "X-Webhook-Signature: t=1700000000,v1=invalid_signature" `
  -d '{\"event_id\":\"evt_101\",\"idempotency_key\":\"idemp_101\",\"payment_reference\":\"pay_101\",\"amount\":120.00,\"currency\":\"AUD\"}'
```

**Expected Response:** `HTTP 401 Unauthorized` with:

```json
{
  "error_code": "TIMESTAMP_OUT_OF_TOLERANCE",
  "detail": "Signature timestamp is outside the allowed tolerance"
}
```

**Test valid end-to-end payment ingestion (with dynamic HMAC generation):**

```powershell
python -c "import time, json, httpx; from recon.config import get_settings; from recon.services.signature import build_signature_header; s=get_settings(); data={'event_id': f'evt_{int(time.time())}', 'idempotency_key': f'key_{int(time.time())}', 'payment_reference': f'pay_{int(time.time())}', 'amount': 150.00, 'currency': 'AUD'}; body=json.dumps(data).encode(); sig=build_signature_header(s.WEBHOOK_SECRET, body); res=httpx.post('[http://127.0.0.1:8000/api/v1/webhooks/payments](http://127.0.0.1:8000/api/v1/webhooks/payments)', content=body, headers={'Content-Type': 'application/json', 'X-Webhook-Signature': sig}); print(res.status_code, res.json())"
```

**Expected Response:** `HTTP 200 OK` with:

```json
{ "status": "processed", "event_id": "evt_...", "payment_id": "..." }
```
