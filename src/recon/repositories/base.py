"""Base repository providing database session access and idempotent insert helpers."""

from __future__ import annotations

from typing import Callable, TypeVar
from sqlalchemy.orm import Session

T = TypeVar("T")


class BaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _insert_unless_exists(
        self,
        entity: T,
        finder: Callable[[], T | None],
    ) -> tuple[T, bool]:
        """
        Attempts to find an existing record using the `finder` function.
        - If found, returns (existing_entity, False)
        - If not found, persists and returns (entity, True)
        """
        existing = finder()
        if existing is not None:
            return existing, False

        self._session.add(entity)
        self._session.commit()
        self._session.refresh(entity)
        return entity, True