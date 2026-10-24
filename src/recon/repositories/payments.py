"""Persistence for payments and discrepancies.

Discrepancies live here for now because every finding is about a payment or the event that
touched it; they can move to repositories/reconciliation.py once reconciliation runs exist.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from recon.db.models import Discrepancy, Payment
from recon.repositories.base import BaseRepository
from recon.schemas.common import DiscrepancyStatus, PaymentStatus


class PaymentRepository(BaseRepository):
    def get(self, payment_id: uuid.UUID) -> Payment | None:
        return self._session.get(Payment, payment_id)

    def get_by_provider_id(
        self, provider: str, provider_payment_id: str, *, for_update: bool = False
    ) -> Payment | None:
        """Look a payment up by the provider's reference.

        `for_update=True` takes a row lock (SELECT ... FOR UPDATE on PostgreSQL) so two
        concurrent webhooks for the same payment are applied one after the other. SQLite has
        no row locks and SQLAlchemy simply omits the clause there.
        """
        stmt = select(Payment).where(
            Payment.provider == provider, Payment.provider_payment_id == provider_payment_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self._session.scalar(stmt)

    def add_if_absent(self, payment: Payment) -> tuple[Payment, bool]:
        """Insert the payment unless this provider reference already exists (row-locked)."""
        return self._insert_unless_exists(
            payment,
            lambda: self.get_by_provider_id(
                payment.provider, payment.provider_payment_id, for_update=True
            ),
        )

    def list_by_status(self, status: PaymentStatus, *, limit: int = 100) -> list[Payment]:
        stmt = (
            select(Payment)
            .where(Payment.status == status)
            .order_by(Payment.created_at)
            .limit(limit)
        )
        return list(self._session.scalars(stmt))


class DiscrepancyRepository(BaseRepository):
    def get_by_fingerprint(self, fingerprint: str) -> Discrepancy | None:
        return self._session.scalar(
            select(Discrepancy).where(Discrepancy.fingerprint == fingerprint)
        )

    def add_if_absent(self, discrepancy: Discrepancy) -> tuple[Discrepancy, bool]:
        """Insert unless the same finding (by fingerprint) was already recorded, so retries
        and re-runs never duplicate audit rows."""
        return self._insert_unless_exists(
            discrepancy, lambda: self.get_by_fingerprint(discrepancy.fingerprint)
        )

    def list_open(self, *, limit: int = 100) -> list[Discrepancy]:
        stmt = (
            select(Discrepancy)
            .where(Discrepancy.status == DiscrepancyStatus.OPEN)
            .order_by(Discrepancy.detected_at)
            .limit(limit)
        )
        return list(self._session.scalars(stmt))

    def list_for_payment(self, payment_id: uuid.UUID) -> list[Discrepancy]:
        stmt = (
            select(Discrepancy)
            .where(Discrepancy.payment_id == payment_id)
            .order_by(Discrepancy.detected_at)
        )
        return list(self._session.scalars(stmt))