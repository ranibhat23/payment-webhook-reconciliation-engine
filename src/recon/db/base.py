"""Declarative base, naming conventions, shared column types and mixins."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, DateTime, MetaData
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

# Deterministic constraint names make Alembic migrations and error messages predictable.
# `column_0_N_name` joins ALL columns of a multi-column constraint, so
# UniqueConstraint("provider", "event_id") becomes uq_<table>_provider_event_id.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UtcDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on every backend.

    SQLite discards tzinfo; this type rejects naive datetimes on the way in and re-attaches
    UTC on the way out, so application code only ever sees aware datetimes.
    """

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime is not allowed; use timezone-aware UTC")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


# Plain JSON on SQLite, JSONB (indexable, faster) on PostgreSQL.
JSONType = JSON().with_variant(JSONB(), "postgresql")


def enum_type(enum_cls: type[Enum]) -> SAEnum:
    """Store enums as VARCHAR holding the enum *value* (not the member name).

    `native_enum=False` avoids Postgres ENUM types, which are painful to migrate, and
    `validate_strings=True` rejects values that aren't valid members.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=32,
        validate_strings=True,
        values_callable=lambda enum: [member.value for member in enum],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)