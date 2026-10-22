"""Test configuration. Every test runs against a migrated SQLite database with no network access:
external services are mocked with respx. Live integration tests are marked `live` and skipped by default."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="logidx-tests-"))
os.environ.update(
    {
        "LOGIDX_DATABASE_URL": f"sqlite:///{_TMP / 'test.db'}",
        "LOGIDX_DATA_DIR": str(_TMP / "data"),
        "LOGIDX_ENABLE_SCHEDULER": "false",
        "LOGIDX_COOKIE_SECURE": "false",
        "LOGIDX_SECRET_KEY": "test-secret-key-not-for-production",
        "LOGIDX_HTTP_MIN_INTERVAL": "0",
        "LOGIDX_CONFIG_DIR": str(Path(__file__).resolve().parent.parent / "config"),
    }
)
for _key in (
    "XAI_API_KEY",
    "ADZUNA_APP_ID",
    "ADZUNA_APP_KEY",
    "GOOGLE_CSE_KEY",
    "GOOGLE_CSE_CX",
    "SMTP_HOST",
    "SMTP_FROM",
    "LOGIDX_REPORT_RECIPIENT",
):
    os.environ.pop(_key, None)

import pytest  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from logidx.db import get_engine, get_sessionmaker, run_migrations  # noqa: E402
from logidx.models import Base  # noqa: E402
from logidx.sources.http import HttpClient  # noqa: E402


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if "live" in (config.getoption("-m") or ""):
        return
    skip = pytest.mark.skip(reason="live test: run with -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def _migrated() -> None:
    run_migrations()


@pytest.fixture(autouse=True)
def _clean_db() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def session() -> Session:
    s = get_sessionmaker()()
    yield s
    s.close()


@pytest.fixture
def http() -> HttpClient:
    client = HttpClient(sleep=lambda _s: None, min_interval=0, backoff_base=0)
    yield client
    client.close()
