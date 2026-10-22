"""Verification status rules and the live URL checker (mocked)."""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import respx

from logidx.enums import AccessMethod, Verification
from logidx.models import Vacancy, VacancySource
from logidx.verification import assess_status, check_url, parse_closing_date, require_fresh_verification

NOW = datetime(2026, 10, 21, 10, tzinfo=UTC)


def vac(*links, **kw):
    v = Vacancy(
        title="General Manager Operations",
        original_title="x",
        normalized_title="x",
        last_seen_at=kw.pop("last_seen", NOW),
        posted_at=kw.pop("posted", NOW - timedelta(days=3)),
        lifecycle="ACTIVE",
        **kw,
    )
    v.sources = list(links)
    return v


def link(**kw):
    defaults = dict(
        source="workday",
        source_job_id="1",
        access_method=AccessMethod.NATIVE,
        url="https://x/job/1",
        present=True,
        last_seen_at=NOW - timedelta(hours=2),
        raw={},
    )
    defaults.update(kw)
    return VacancySource(**defaults)


def test_employer_requisition_in_live_feed_is_verified():
    status, ev = assess_status(vac(link(is_employer_requisition=True)), NOW)
    assert status == Verification.VERIFIED_OPEN and ev[-1]["type"] == "employer_requisition"


def test_stale_requisition_sighting_is_not_verified():
    status, _ = assess_status(vac(link(is_employer_requisition=True, last_seen_at=NOW - timedelta(days=3))), NOW)
    assert status == Verification.UNVERIFIED_STALE


def test_agency_listing_recent_vs_old():
    recent = vac(link(source="bullhorn", is_agency_listing=True), recruiting_agency="Six Degrees")
    old = vac(
        link(source="bullhorn", is_agency_listing=True),
        recruiting_agency="Six Degrees",
        posted=NOW - timedelta(days=60),
    )
    assert assess_status(recent, NOW)[0] == Verification.LIKELY_OPEN
    assert assess_status(old, NOW)[0] == Verification.RECRUITER_CONFIRMATION


def test_aggregator_listing():
    fresh = vac(link(source="adzuna", access_method=AccessMethod.API))
    stale = vac(link(source="adzuna", access_method=AccessMethod.API), posted=NOW - timedelta(days=40))
    assert assess_status(fresh, NOW)[0] == Verification.LIKELY_OPEN
    assert assess_status(stale, NOW)[0] == Verification.UNVERIFIED_STALE


def test_closing_date_passed_is_closed():
    v = vac(link(is_employer_requisition=True), closing_date=date(2026, 10, 1))
    assert assess_status(v, NOW)[0] == Verification.CLOSED


def test_source_flag_closed():
    v = vac(link(is_employer_requisition=True, raw={"explicit_open": False}))
    assert assess_status(v, NOW)[0] == Verification.CLOSED


def test_indexed_fallback_alone_is_unverified():
    v = vac(link(source="google_indexed", access_method=AccessMethod.INDEXED_FALLBACK))
    assert assess_status(v, NOW)[0] == Verification.UNVERIFIED_STALE


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Applications close: 30 October 2026", date(2026, 10, 30)),
        ("Closing date 05/11/2026", date(2026, 11, 5)),
        ("Apply by Friday, 7th November 2026", date(2026, 11, 7)),
        ("No closing date", None),
    ],
)
def test_parse_closing_date(text, expected):
    assert parse_closing_date(text) == expected


@respx.mock
def test_url_check_closed_phrase(http):
    respx.get("https://careers.example/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://careers.example/job/123456").mock(
        return_value=httpx.Response(200, text="<p>Sorry, this job is no longer available.</p>")
    )
    check = check_url(http, "https://careers.example/job/123456", NOW)
    status, _ = assess_status(vac(), NOW, check)
    assert check.closed_phrase and status == Verification.CLOSED


@respx.mock
def test_url_check_explicit_future_close_date_verifies(http):
    respx.get("https://careers.example/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://careers.example/job/123456").mock(
        return_value=httpx.Response(200, text="<h1>GM</h1><p>Applications close 30 November 2026.</p><a>Apply</a>")
    )
    status, _ = assess_status(vac(), NOW, check_url(http, "https://careers.example/job/123456", NOW))
    assert status == Verification.VERIFIED_OPEN


@respx.mock
def test_generic_redirect_and_apply_button_are_not_evidence(http):
    respx.get("https://careers.example/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://careers.example/job/123456").mock(
        return_value=httpx.Response(302, headers={"Location": "https://careers.example/"})
    )
    respx.get("https://careers.example/").mock(
        return_value=httpx.Response(200, text="<a>Apply now</a> Applications close 30 November 2026")
    )
    check = check_url(http, "https://careers.example/job/123456", NOW)
    assert not check.job_specific
    assert assess_status(vac(), NOW, check)[0] == Verification.UNVERIFIED_STALE


@respx.mock
def test_404_is_closed_and_login_wall_not_bypassed(http):
    respx.get("https://careers.example/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://careers.example/job/1").mock(return_value=httpx.Response(410))
    assert check_url(http, "https://careers.example/job/1").closed_phrase == "HTTP 410"
    respx.get("https://careers.example/job/2").mock(return_value=httpx.Response(403))
    check = check_url(http, "https://careers.example/job/2")
    assert check.login_wall and "not bypassed" in check.notes[0]


@respx.mock
def test_robots_disallow_prevents_fetch(http):
    respx.get("https://careers.example/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /job")
    )
    page = respx.get("https://careers.example/job/9")
    check = check_url(http, "https://careers.example/job/9")
    assert check.robots_blocked and not page.called


def test_document_generation_guard():
    v = vac(verification_status=Verification.LIKELY_OPEN, verified_at=datetime.now(UTC))
    with pytest.raises(PermissionError):
        require_fresh_verification(v)
    v.verification_status, v.verified_at = Verification.VERIFIED_OPEN, datetime.now(UTC) - timedelta(days=2)
    with pytest.raises(PermissionError):
        require_fresh_verification(v)
    v.verified_at = datetime.now(UTC)
    require_fresh_verification(v)
