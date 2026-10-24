"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from recon.api.routes import health, webhooks
from recon.config import get_settings
from recon.core.errors import AppError, InvalidSignatureError
from recon.core.logging import setup_logging
from recon.db.base import Base
from recon.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize resources on startup."""
    setup_logging()
    Base.metadata.create_all(bind=engine)
    yield


settings = get_settings()

app = FastAPI(
    title="Payment Webhook & Reconciliation Engine",
    version="1.0.0",
    description="Enterprise event ingestion, HMAC verification, and idempotency ledger.",
    lifespan=lifespan,
)

# Exception handlers for domain errors
@app.exception_handler(InvalidSignatureError)
async def invalid_signature_handler(request: Request, exc: InvalidSignatureError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error_code": exc.code.value, "detail": str(exc)},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error_code": exc.code.value, "detail": str(exc)},
    )


# Mount routers
app.include_router(health.router)
app.include_router(webhooks.router)