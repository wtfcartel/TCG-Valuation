"""Dashboard security (auth, CSRF, rate limiting, headers, secret handling) and page smoke tests."""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from logidx.enums import AccessMethod
from logidx.models import AuditLog, User, Vacancy, VacancyEvent
from logidx.pipeline.ingest import ingest
from logidx.profile import seed_profile
from logidx.security import LoginRateLimiter, hash_password, redact, verify_password
from logidx.sources.base import RawVacancy
from logidx.taxonomy import default_taxonomy
from logidx.web import app as webapp

PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(session):
    session.add(User(email="exec@example.com", password_hash=hash_password(PASSWORD)))
    session.commit()
    webapp.limiter = LoginRateLimiter()
    with TestClient(webapp.create_app(start_scheduler=False)) as c:
        yield c


def csrf(client, path="/login"):
    return re.search(r'name="csrf" value="([^"]+)"', client.get(path).text).group(1)


def login(client):
    r = client.post(
        "/login", data={"email": "exec@example.com", "password": PASSWORD, "csrf": csrf(client)}, follow_redirects=False
    )
    assert r.status_code == 303
    return client


def test_password_hashing():
    h = hash_password(PASSWORD)
    assert verify_password(PASSWORD, h) and not verify_password("wrong password!!", h)
    assert PASSWORD not in h
    with pytest.raises(ValueError):
        hash_password("short")


def test_redaction():
    text = "GET https://api.adzuna.com/x?app_id=abc123&app_key=SECRETKEY99 Authorization: Bearer xai-abcdefghijklmnop"
    out = redact(text, extra_secrets=["SECRETKEY99"])
    assert "SECRETKEY99" not in out and "abc123" not in out and "xai-abcdefghijklmnop" not in out


def test_pages_require_login(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/api/vacancies").status_code == 401


def test_post_requires_csrf(client):
    login(client)
    assert client.post("/runs", data={}).status_code == 403
    assert (
        client.post("/settings/schedule", data={"slots": "06:00", "report_slot": "06:00", "csrf": "forged"}).status_code
        == 403
    )


def test_login_rate_limited(client):
    token = csrf(client)
    for _ in range(5):
        r = client.post("/login", data={"email": "exec@example.com", "password": "wrong-password!", "csrf": token})
        assert "incorrect" in r.text
    r = client.post("/login", data={"email": "exec@example.com", "password": PASSWORD, "csrf": token})
    assert "Too many attempts" in r.text


def test_security_headers_and_cookie(client):
    r = client.get("/login")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    r = client.post(
        "/login", data={"email": "exec@example.com", "password": PASSWORD, "csrf": csrf(client)}, follow_redirects=False
    )
    cookie = r.headers["set-cookie"].lower()
    assert "logidx_session=" in cookie and "httponly" in cookie and "samesite=strict" in cookie


def test_settings_page_never_shows_secrets(client, monkeypatch):
    from pydantic import SecretStr

    from logidx.settings import get_settings

    monkeypatch.setattr(get_settings(), "xai_api_key", SecretStr("xai-supersecret-value-123"))
    login(client)
    html = client.get("/settings").text
    assert "xAI Grok</strong> — configured" in html
    assert "xai-supersecret-value-123" not in html and "test-secret-key-not-for-production" not in html


def seed_vacancy(session):
    raw = RawVacancy(
        source="t",
        source_job_id="1",
        title="General Manager Supply Chain",
        url="https://x/job/1",
        employer="Southern Freight (Fixture)",
        location="Melbourne VIC",
        description="Lead national logistics with full P&L, reporting to the CEO.",
        is_employer_requisition=True,
    )
    v = ingest(
        session, raw, run=None, access_method=AccessMethod.NATIVE, taxonomy=default_taxonomy(), profile=seed_profile()
    ).vacancy
    session.commit()
    return v


def test_all_pages_render(client, session):
    v = seed_vacancy(session)
    login(client)
    for path in [
        "/",
        "/jobs",
        "/jobs?category=supply_chain_logistics&workable=1",
        f"/jobs/{v.id}",
        "/priority",
        "/disciplines",
        "/applications",
        "/recruiters",
        "/coverage",
        "/runs",
        "/recall",
        "/report",
        "/import",
        "/documents",
        "/settings",
        "/api/vacancies",
        f"/api/vacancies/{v.id}",
        "/api/coverage",
        "/api/runs",
        "/healthz",
    ]:
        r = client.get(path)
        assert r.status_code == 200, path
    assert "General Manager Supply Chain" in client.get("/jobs?category=supply_chain_logistics").text


def test_status_change_is_audited(client, session):
    v = seed_vacancy(session)
    login(client)
    token = csrf(client, f"/jobs/{v.id}")
    r = client.post(
        f"/jobs/{v.id}/status",
        data={"status": "APPLIED", "note": "via employer site", "csrf": token},
        follow_redirects=False,
    )
    assert r.status_code == 303
    session.expire_all()
    v = session.get(Vacancy, v.id)
    assert v.application_status == "APPLIED" and v.applied_at is not None
    assert session.scalar(select(VacancyEvent).where(VacancyEvent.kind == "status_changed")).actor == "exec@example.com"
    assert session.scalar(select(AuditLog).where(AuditLog.action == "status_changed")) is not None


def test_manual_import_and_dedupe(client, session):
    login(client)
    token = csrf(client, "/import")
    data = {
        "url": "https://www.seek.com.au/job/12345678",
        "title": "Head of Logistics",
        "employer": "",
        "agency": "Sigma Search Supply Chain",
        "location": "Ingleburn, NSW",
        "origin": "seek",
        "description": "Lead logistics across NSW distribution centres.",
        "csrf": token,
    }
    r = client.post("/import", data=data, follow_redirects=False)
    assert r.status_code == 303
    v = session.scalar(select(Vacancy).where(Vacancy.title == "Head of Logistics"))
    assert v.geography.startswith("INTERSTATE") and v.sources[0].access_method == "MANUAL"
    client.post("/import", data=data)
    assert len(session.scalars(select(Vacancy)).all()) == 1


def test_schedule_saved(client):
    login(client)
    token = csrf(client, "/settings")
    r = client.post(
        "/settings/schedule",
        data={"slots": "06:30, 14:00", "report_slot": "14:00", "enabled": "on", "csrf": token},
        follow_redirects=True,
    )
    assert "Schedule saved" in r.text and "06:30, 14:00" in r.text


def test_profile_validation(client):
    login(client)
    token = csrf(client, "/settings")
    r = client.post(
        "/settings/profile", data={"profile_yaml": "evidence: [{claim: no id}]", "csrf": token}, follow_redirects=True
    )
    assert "Profile not saved" in r.text


def test_logout(client):
    login(client)
    client.post("/logout", data={"csrf": csrf(client, "/")})
    assert client.get("/", follow_redirects=False).status_code == 303
