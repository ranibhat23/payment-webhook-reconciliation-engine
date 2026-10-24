"""Service health inspection endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from recon.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health", status_code=status.HTTP_200_OK)
def health_check(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Inspect application and database connectivity."""
    db.execute(text("SELECT 1"))
    return {"status": "healthy", "database": "connected"}