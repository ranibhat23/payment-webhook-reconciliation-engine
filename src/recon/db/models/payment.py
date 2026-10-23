"""Our record of a payment and its lifecycle state."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from recon.core.money import Money
from recon.db.base import Base, TimestampMixin, UtcDateTime, enum_type
from recon.schemas.common import Currency, PaymentStatus

if TYPE_CHECKING:
    from recon.db.models.discrepancy import Discrepancy
    from recon.db.models.webhook_event import WebhookEvent

# Which states a payment may move to. Terminal states map to an empty set.
ALLOWED_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset(
        {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED, PaymentStatus.CANCELLED}
    ),
    PaymentStatus.SUCCEEDED: frozenset({PaymentStatus.REFUNDED}),
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.CANCELLED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        # One row per provider payment, however many webhooks mention it.
        UniqueConstraint("provider", "provider_payment_id"),
        # NULLs are distinct in unique constraints, so payments without a key never collide.
        UniqueConstraint("provider", "idempotency_key"),
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        Index("ix_payments_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50))
    provider_payment_id: Mapped[str] = mapped_column(String(255))
    idempotency_key: Mapped[str | None] = mapped_column(String(255))

    # Integer minor units (cents) + currency: exact, and portable across SQLite/Postgres.
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[Currency] = mapped_column(enum_type(Currency))

    status: Mapped[PaymentStatus] = mapped_column(
        enum_type(PaymentStatus), default=PaymentStatus.PENDING
    )
    # Provider timestamp of the newest event applied; lets the service ignore stale,
    # out-of-order webhooks.
    last_event_at: Mapped[datetime | None] = mapped_column(UtcDateTime())

    webhook_events: Mapped[list[WebhookEvent]] = relationship(
        back_populates="payment", order_by="WebhookEvent.occurred_at"
    )
    discrepancies: Mapped[list[Discrepancy]] = relationship(back_populates="payment")

    @property
    def amount(self) -> Money:
        return Money.from_minor_units(self.amount_minor, self.currency)

    def can_transition_to(self, new_status: PaymentStatus) -> bool:
        # Re-asserting the current status is allowed so duplicate webhooks are harmless.
        return new_status == self.status or new_status in ALLOWED_TRANSITIONS[self.status]

    def try_transition(self, new_status: PaymentStatus) -> bool:
        """Apply the transition if legal; return False (changing nothing) if not.

        Webhooks can arrive out of order, so an illegal transition is something the caller
        should record as a Discrepancy rather than an exception that fails the request.
        """
        if not self.can_transition_to(new_status):
            return False
        self.status = new_status
        return True