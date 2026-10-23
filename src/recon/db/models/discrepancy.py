"""A mismatch found during reconciliation, with a lightweight audit trail."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from recon.db.base import Base, JSONType, TimestampMixin, UtcDateTime, enum_type, utcnow
from recon.schemas.common import DiscrepancyStatus, DiscrepancyType

if TYPE_CHECKING:
    from recon.db.models.payment import Payment
    from recon.db.models.webhook_event import WebhookEvent


class Discrepancy(TimestampMixin, Base):
    __tablename__ = "discrepancies"
    __table_args__ = (
        # Re-running reconciliation over the same data must not create duplicate findings;
        # the fingerprint is the dedupe key (see make_fingerprint).
        UniqueConstraint("fingerprint"),
        # Audit integrity: a closed discrepancy must say when it was closed.
        CheckConstraint(
            "status NOT IN ('resolved', 'ignored') OR resolved_at IS NOT NULL",
            name="closed_requires_resolved_at",
        ),
        Index("ix_discrepancies_status_detected_at", "status", "detected_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    fingerprint: Mapped[str] = mapped_column(String(64))
    type: Mapped[DiscrepancyType] = mapped_column(enum_type(DiscrepancyType))
    status: Mapped[DiscrepancyStatus] = mapped_column(
        enum_type(DiscrepancyStatus), default=DiscrepancyStatus.OPEN
    )

    # Either side may be absent (missing payment -> no payment_id; missing webhook -> no event).
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT")
    )
    webhook_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("webhook_events.id", ondelete="RESTRICT")
    )

    expected_value: Mapped[str | None] = mapped_column(String(255))
    actual_value: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONType)

    # --- audit trail ---
    detected_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime())
    resolved_by: Mapped[str | None] = mapped_column(String(255))
    resolution_note: Mapped[str | None] = mapped_column(Text)

    payment: Mapped[Payment | None] = relationship(back_populates="discrepancies")
    webhook_event: Mapped[WebhookEvent | None] = relationship(back_populates="discrepancies")

    @staticmethod
    def make_fingerprint(discrepancy_type: DiscrepancyType, *parts: object) -> str:
        """Stable SHA-256 over the type plus identifying parts, e.g. the payment id and
        webhook event id, so the same finding always hashes to the same value."""
        raw = "|".join([discrepancy_type.value, *(str(part) for part in parts)])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def close(
        self,
        *,
        resolved_by: str,
        note: str | None = None,
        ignore: bool = False,
        at: datetime | None = None,
    ) -> None:
        """Mark resolved (or ignored) and record who/when/why in one step."""
        self.status = DiscrepancyStatus.IGNORED if ignore else DiscrepancyStatus.RESOLVED
        self.resolved_at = at or utcnow()
        self.resolved_by = resolved_by
        self.resolution_note = note