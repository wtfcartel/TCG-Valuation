"""Engine and session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from logidx.settings import PACKAGE_ROOT, get_settings

MIGRATION_LOCK_KEY = 4_211_903  # arbitrary, constant advisory-lock id for schema migrations


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///") and ":memory:" not in url:
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def advisory_lock(url: str, key: int = MIGRATION_LOCK_KEY) -> Iterator[Connection | None]:
    """Hold a PostgreSQL session advisory lock for the duration (no-op on SQLite).

    Serverless instances that cold-start together serialise schema migration and seeding through it.
    """
    if not url.startswith("postgresql"):
        yield None
        return
    engine = make_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})
            conn.commit()
            try:
                yield conn
            finally:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                conn.commit()
    finally:
        engine.dispose()


def run_migrations(url: str | None = None, connection: Connection | None = None) -> None:
    """Bring the schema to the latest Alembic revision (pass `connection` to run on a locked connection)."""
    from alembic import command
    from alembic.config import Config

    url = url or get_settings().database_url
    cfg = Config()
    cfg.set_main_option("script_location", str(PACKAGE_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    if connection is not None:
        cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")
    if connection is not None:
        connection.commit()
