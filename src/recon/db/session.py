"""Engine, session factory and the FastAPI `get_db` dependency (synchronous SQLAlchemy)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from recon.config import get_settings
from recon.db.base import Base


def build_engine(database_url: str, *, echo: bool = False) -> Engine:
    url = make_url(database_url)
    kwargs: dict[str, Any] = {"echo": echo, "pool_pre_ping": True}
    is_sqlite = url.get_backend_name() == "sqlite"

    if is_sqlite:
        # FastAPI runs sync endpoints in a threadpool, so SQLite connections cross threads.
        kwargs["connect_args"] = {"check_same_thread": False}
        if url.database in (None, "", ":memory:"):
            # An in-memory DB vanishes per connection; StaticPool shares one for tests.
            kwargs["poolclass"] = StaticPool

    engine = create_engine(url, **kwargs)

    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
            # SQLite ignores FOREIGN KEY constraints unless this is switched on per connection.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


settings = get_settings()
engine = build_engine(settings.database_url, echo=settings.sql_echo)

# expire_on_commit=False keeps ORM objects readable after commit (handy when returning them
# from a route); autoflush=False makes writes explicit and easier to reason about.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards.

    Services/repositories own commit/rollback; closing the session discards anything
    uncommitted.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables directly from the models. Convenient for local SQLite/tests;
    use Alembic migrations for anything shared or long-lived."""
    import recon.db.models  # noqa: F401  (importing registers every table on Base.metadata)

    Base.metadata.create_all(bind=engine)