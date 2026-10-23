"""Every inbound webhook, stored once, for idempotency and audit."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from recon.core.money import Money
from recon.db.base import Base, JSONType, TimestampMixin, UtcDateTime, enum_type, utcnow
from recon.schemas.common import Currency, PaymentStatus, WebhookEventStatus

if TYPE_CHECKING:
    from recon.db.models.discrepancy import Discrepancy
    from recon.db.models.payment import Payment


class WebhookEvent(TimestampMixin, Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        # The idempotency guarantee: a provider retry hits one of these and is rejected by
        # the database itself, which is race-free where "check then insert" is not.
        UniqueConstraint("provider", "event_id"),
        UniqueConstraint("provider", "idempotency_key"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        # Supports "give me unprocessed events, oldest first" for workers.
        Index("ix_webhook_events_status_received_at", "status", "received_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # --- identity / idempotency ---
    provider: Mapped[str] = mapped_column(String(50))
    event_id: Mapped[str] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(100))

    # --- what the webhook claims ---
    provider_payment_id: Mapped[str] = mapped_column(String(255), index=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[Currency] = mapped_column(enum_type(Currency))
    payment_status: Mapped[PaymentStatus] = mapped_column(enum_type(PaymentStatus))
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime())  # provider's timestamp
    received_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType)  # original body, for audit/replay

    # --- processing state ---
    status: Mapped[WebhookEventStatus] = mapped_column(
        enum_type(WebhookEventStatus), default=WebhookEventStatus.RECEIVED
    )
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(UtcDateTime())

    # Filled in once the event is matched to a Payment. RESTRICT: never silently orphan or
    # cascade-delete audit data.
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT")
    )

    payment: Mapped[Payment | None] = relationship(back_populates="webhook_events")
    discrepancies: Mapped[list[Discrepancy]] = relationship(back_populates="webhook_event")

    @property
    def amount(self) -> Money:
        return Money.from_minor_units(self.amount_minor, self.currency)