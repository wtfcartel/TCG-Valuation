"""Serverless deployment behaviour: settings, cron endpoint, time budget, bootstrap and packaging."""

import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from logidx.bootstrap import ensure_ready
from logidx.enums import SearchStatus
from logidx.models import Run, SourceSearch, User
from logidx.pipeline.runner import TIME_BUDGET_NOTE, RunPlan, run_discovery, start_run
from logidx.settings import Settings, get_settings
from logidx.sources.registry import Watchlist
from logidx.web import app as webapp
from tests.test_runner import FakeQuery

ROOT = Path(__file__).resolve().parent.parent


def test_neon_urls_get_psycopg_driver_and_serverless_defaults(monkeypatch):
    monkeypatch.delenv("LOGIDX_DATA_DIR")
    s = Settings(DATABASE_URL="postgres://u:p@ep-x.neon.tech/db?sslmode=require", VERCEL="1")
    assert s.database_url == "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"
    assert s.serverless and not s.enable_scheduler and s.auto_migrate
    assert str(s.data_dir) == "/tmp/logidx" and s.run_time_budget_seconds == 240
    assert Settings(POSTGRES_URL="postgresql://a@b/c").database_url.startswith("postgresql+psycopg://")


def test_serverless_requires_secret_key(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "serverless", True)
    monkeypatch.setattr(s, "secret_key", SecretStr(""))
    with pytest.raises(RuntimeError, match="LOGIDX_SECRET_KEY"):
        webapp.create_app(start_scheduler=False)


@pytest.fixture
def cron_client(monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", SecretStr("cron-secret-value-1234"))
    import logidx.service as service

    empty = RunPlan([], {}, Watchlist([]), [])
    original = service.execute
    monkeypatch.setattr(service, "execute", lambda **kw: original(plan=empty, send_daily_report=False, **kw))
    with TestClient(webapp.create_app(start_scheduler=False)) as c:
        yield c


def test_cron_requires_secret(cron_client):
    assert cron_client.get("/cron/run?slot=20:00").status_code == 401
    assert cron_client.get("/cron/run?slot=20:00", headers={"Authorization": "Bearer wrong"}).status_code == 401
    bad = cron_client.get("/cron/run?slot=25:00", headers={"Authorization": "Bearer cron-secret-value-1234"})
    assert bad.status_code == 400


def test_cron_runs_once_per_slot_per_day(cron_client, session):
    auth = {"Authorization": "Bearer cron-secret-value-1234"}
    first = cron_client.get("/cron/run?slot=20:00", headers=auth).json()
    second = cron_client.get("/cron/run?slot=20:00", headers=auth).json()
    assert first["run_id"] and second["status"] == "duplicate"
    assert session.scalar(select(func.count(Run.id)).where(Run.trigger == "scheduled")) == 1


def test_cron_disabled_without_secret(monkeypatch):
    monkeypatch.setattr(get_settings(), "cron_secret", SecretStr(""))
    with TestClient(webapp.create_app(start_scheduler=False)) as c:
        assert c.get("/cron/run?slot=20:00", headers={"Authorization": "Bearer "}).status_code == 503


def test_time_budget_skips_remaining_searches_visibly(session):
    run = start_run(session, trigger="test")
    run_discovery(session, run, plan=RunPlan([FakeQuery()], {}, Watchlist([]), []), time_budget=1e-9)
    skipped = session.scalars(select(SourceSearch).where(SourceSearch.limitation == TIME_BUDGET_NOTE)).all()
    assert skipped and all(s.status == SearchStatus.NOT_SEARCHED for s in skipped)
    assert all(not a.complete for a in run.category_audits)


def test_bootstrap_creates_first_user_only_once(session):
    s = Settings(
        LOGIDX_ADMIN_EMAIL="Owner@Example.com",
        LOGIDX_ADMIN_PASSWORD=SecretStr("bootstrap-pass-123"),
        LOGIDX_DATABASE_URL=get_settings().database_url,
    )
    ensure_ready(s)
    ensure_ready(
        Settings(
            LOGIDX_ADMIN_EMAIL="other@example.com",
            LOGIDX_ADMIN_PASSWORD=SecretStr("another-pass-123"),
            LOGIDX_DATABASE_URL=get_settings().database_url,
        )
    )
    assert [u.email for u in session.scalars(select(User)).all()] == ["owner@example.com"]


def test_requirements_txt_matches_pyproject():
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    lines = [ln for ln in (ROOT / "requirements.txt").read_text().splitlines() if ln and not ln.startswith("#")]
    assert lines == deps


def test_vercel_entrypoint_defines_top_level_app():
    # Vercel only detects a Python function whose module assigns `app` at top level.
    assert "\napp = " in (ROOT / "api" / "index.py").read_text()
