"""Persistence for inbound webhook events (the idempotency ledger)."""

from __future__ import annotations

import uuid

from sqlalchemy import or_, select

from recon.db.models import WebhookEvent
from recon.repositories.base import BaseRepository
from recon.schemas.common import WebhookEventStatus


class WebhookEventRepository(BaseRepository):
    def get(self, event_pk: uuid.UUID) -> WebhookEvent | None:
        return self._session.get(WebhookEvent, event_pk)

    def find_by_provider_event_id(self, provider: str, event_id: str) -> WebhookEvent | None:
        stmt = select(WebhookEvent).where(
            WebhookEvent.provider == provider, WebhookEvent.event_id == event_id
        )
        return self._session.scalar(stmt)

    def find_by_idempotency_key(self, provider: str, idempotency_key: str) -> WebhookEvent | None:
        stmt = select(WebhookEvent).where(
            WebhookEvent.provider == provider, WebhookEvent.idempotency_key == idempotency_key
        )
        return self._session.scalar(stmt)

    def find_existing(
        self, provider: str, event_id: str, idempotency_key: str
    ) -> list[WebhookEvent]:
        """Every stored event that collides on event_id OR idempotency_key (0, 1 or 2 rows)."""
        stmt = (
            select(WebhookEvent)
            .where(
                WebhookEvent.provider == provider,
                or_(
                    WebhookEvent.event_id == event_id,
                    WebhookEvent.idempotency_key == idempotency_key,
                ),
            )
            .order_by(WebhookEvent.received_at)
        )
        return list(self._session.scalars(stmt))

    def add_if_absent(self, event: WebhookEvent) -> tuple[WebhookEvent, bool]:
        """Insert unless an event with the same event_id or idempotency_key exists.

        Returns (stored_event, created). When `created` is False, `stored_event` is the
        pre-existing row and the caller decides whether the new delivery is a harmless
        replay or a conflicting reuse of the key.
        """
        return self._insert_unless_exists(
            event,
            lambda: next(
                iter(self.find_existing(event.provider, event.event_id, event.idempotency_key)),
                None,
            ),
        )

    def list_by_status(self, status: WebhookEventStatus, *, limit: int = 100) -> list[WebhookEvent]:
        stmt = (
            select(WebhookEvent)
            .where(WebhookEvent.status == status)
            .order_by(WebhookEvent.received_at)
            .limit(limit)
        )
        return list(self._session.scalars(stmt))