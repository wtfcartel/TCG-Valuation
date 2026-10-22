"""Database-backed run lock with expiry. Works across processes and on SQLite and PostgreSQL:
acquisition is an INSERT on a primary key, so two contenders cannot both succeed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from logidx.models import RunLock


def acquire(session: Session, name: str, holder: str, ttl: timedelta = timedelta(hours=2)) -> bool:
    now = datetime.now(UTC)
    session.execute(delete(RunLock).where(RunLock.name == name, RunLock.expires_at < now))
    session.commit()
    session.add(RunLock(name=name, holder=holder, acquired_at=now, expires_at=now + ttl))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return False
    return True


def release(session: Session, name: str, holder: str) -> None:
    session.execute(delete(RunLock).where(RunLock.name == name, RunLock.holder == holder))
    session.commit()


def holder_of(session: Session, name: str) -> RunLock | None:
    lock = session.get(RunLock, name)
    if lock and lock.expires_at < datetime.now(UTC):
        return None
    return lock
