"""Bring a deployment to a usable state: migrate, seed, and create the first user from the environment.

Used by `logidx initdb` and on serverless cold start (where there is no shell to run commands).
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from logidx import recall
from logidx.db import advisory_lock, run_migrations, session_scope
from logidx.models import AuditLog, User
from logidx.profile import get_profile, save_profile
from logidx.security import hash_password
from logidx.settings import Settings, get_settings

log = logging.getLogger(__name__)


def ensure_ready(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    with advisory_lock(settings.database_url) as conn:  # one instance at a time migrates and seeds
        run_migrations(settings.database_url, connection=conn)
        _seed(settings)


def _seed(settings: Settings) -> None:
    with session_scope() as s:
        save_profile(s, get_profile(s))  # seeds from config/profile.yaml on first run
        recall.sync_cases(s)
        email, password = settings.admin_email.strip().lower(), settings.admin_password.get_secret_value()
        if email and password and not s.scalar(select(func.count(User.id))):
            s.add(User(email=email, password_hash=hash_password(password)))
            s.add(AuditLog(actor="bootstrap", action="user_created", detail={"email": email}))
            log.warning("created first user from LOGIDX_ADMIN_EMAIL; remove LOGIDX_ADMIN_PASSWORD from the environment")
