"""Active-vacancy verification.

Status rules (deterministic, evidence recorded for every decision):

VERIFIED OPEN  – the vacancy is in the hiring employer's own live ATS listing (seen in the latest
                 successful fetch, with a requisition-specific URL), or the job-specific page states
                 that applications are open / close on a future date.
LIKELY OPEN    – recent sighting (agency ATS listing or aggregator ≤ 14 days old) and nothing
                 indicates closure, but the employer requisition is not confirmed.
RECRUITER CONFIRMATION REQUIRED – an agency listing that is older or no longer refreshed.
UNVERIFIED / STALE – insufficient or out-of-date evidence.
CLOSED         – closing date passed, the source says applications are closed, the job page is gone
                 (404/410) or states closure.

Never treated as proof of an open vacancy: a generic careers page, an "Apply" button alone, or a
redirect from a job URL to a search/landing page. The checker never logs in or submits a form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from logidx.enums import AccessMethod, Lifecycle, Verification
from logidx.models import Vacancy, VacancyEvent
from logidx.sources.http import HttpClient, SourceError

FRESH_SIGHTING = timedelta(hours=36)
AGGREGATOR_FRESH_DAYS = 14
AGENCY_FRESH_DAYS = 30

CLOSED_PHRASES = [
    "no longer accepting applications",
    "this job has expired",
    "job has expired",
    "this job is no longer available",
    "job is no longer available",
    "position has been filled",
    "this position is closed",
    "applications have closed",
    "applications are now closed",
    "this advert has expired",
    "advertisement has expired",
    "vacancy has closed",
    "this role has been filled",
    "job you are looking for is no longer",
    "posting is no longer available",
    "this job posting is closed",
    "no longer open",
]
OPEN_PHRASES = [
    "applications are open",
    "now accepting applications",
    "currently accepting applications",
    "applications are now open",
]
LOGIN_HINTS = [
    "sign in to view",
    "log in to view",
    "login to view",
    "please sign in",
    "authwall",
    "/login",
    "/signin",
    "checkpoint",
]
_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        start=1,
    )
}
_CLOSE_DATE = re.compile(
    r"(?:applications?\s+close|closing\s+date|close[sd]?\s+on|apply\s+by|applications?\s+due)[^0-9a-z]{0,20}"
    r"(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day,?\s+)?"
    r"(\d{1,2})(?:st|nd|rd|th)?[\s/.-]+([a-z]+|\d{1,2})[\s/.,-]+(\d{4}|\d{2})",
    re.IGNORECASE,
)


@dataclass
class UrlCheck:
    url: str
    checked_at: datetime
    status_code: int | None = None
    final_url: str | None = None
    closed_phrase: str | None = None
    open_phrase: str | None = None
    closing_date: date | None = None
    login_wall: bool = False
    job_specific: bool = True
    robots_blocked: bool = False
    error: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_evidence(self) -> dict[str, object]:
        return {
            "type": "url_check",
            "at": self.checked_at.isoformat(),
            "url": self.url,
            "status_code": self.status_code,
            "final_url": self.final_url,
            "closed_phrase": self.closed_phrase,
            "open_phrase": self.open_phrase,
            "closing_date": self.closing_date.isoformat() if self.closing_date else None,
            "login_wall": self.login_wall,
            "job_specific": self.job_specific,
            "robots_blocked": self.robots_blocked,
            "error": self.error,
            "notes": self.notes,
        }


def parse_closing_date(text: str) -> date | None:
    m = _CLOSE_DATE.search(text or "")
    if not m:
        return None
    day, month_raw, year_raw = m.groups()
    if month_raw.isdigit():
        month = int(month_raw)
    else:
        month = next((v for k, v in _MONTHS.items() if k.startswith(month_raw.lower()[:3])), 0)
    year = int(year_raw) + (2000 if len(year_raw) == 2 else 0)
    try:
        return date(year, month, int(day))  # Australian day-first order
    except ValueError:
        return None


def _job_specific(original: str, final: str) -> bool:
    """A job URL that redirects to a path without the original's last segment/id is a landing page."""
    o, f = urlsplit(original), urlsplit(final)
    if o.netloc != f.netloc and not f.path.strip("/"):
        return False
    o_tokens = [t for t in re.split(r"[/_\-?=&]", o.path + "?" + o.query) if re.search(r"\d{3,}", t)]
    if o_tokens:
        return any(t in final for t in o_tokens)
    return f.path.rstrip("/") == o.path.rstrip("/") or len(f.path.strip("/").split("/")) >= 2


def check_url(http: HttpClient, url: str, now: datetime | None = None) -> UrlCheck:
    now = now or datetime.now(UTC)
    result = UrlCheck(url=url, checked_at=now)
    if not http.robots_allows(url):
        result.robots_blocked = True
        result.notes.append("robots.txt disallows automated access; not fetched")
        return result
    try:
        resp = http.request("GET", url)
    except SourceError as exc:
        result.error = str(exc)
        result.status_code = exc.status_code
        if exc.blocked:
            result.login_wall = True
            result.notes.append("access refused (not bypassed)")
        return result
    result.status_code, result.final_url = resp.status_code, str(resp.url)
    if resp.status_code in (404, 410):
        result.closed_phrase = f"HTTP {resp.status_code}"
        return result
    text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True).lower() if resp.text else ""
    final_low = result.final_url.lower()
    if any(h in final_low for h in LOGIN_HINTS) or any(h in text[:3000] for h in LOGIN_HINTS[:4]):
        result.login_wall = True
        result.notes.append("login required to view; not bypassed")
    result.job_specific = _job_specific(url, result.final_url)
    if not result.job_specific:
        result.notes.append("redirected to a generic page — not evidence of an open vacancy")
    result.closed_phrase = next((p for p in CLOSED_PHRASES if p in text), None)
    result.open_phrase = next((p for p in OPEN_PHRASES if p in text), None)
    result.closing_date = parse_closing_date(text)
    return result


def assess_status(
    vacancy: Vacancy, now: datetime | None = None, url_check: UrlCheck | None = None
) -> tuple[Verification, list[dict[str, object]]]:
    """Derive the verification status from the vacancy's sightings (and an optional fresh URL check)."""
    now = now or datetime.now(UTC)
    today = now.astimezone(UTC).date()
    evidence: list[dict[str, object]] = []

    closing = vacancy.closing_date
    if url_check and url_check.closing_date:
        closing = url_check.closing_date
    if closing and closing < today:
        evidence.append({"type": "closing_date", "value": closing.isoformat(), "note": "closing date has passed"})
        return Verification.CLOSED, evidence
    if url_check and url_check.closed_phrase and url_check.job_specific:
        evidence.append(url_check.as_evidence())
        return Verification.CLOSED, evidence
    for link in vacancy.sources:
        if link.present and (link.raw or {}).get("explicit_open") is False:
            evidence.append(
                {"type": "source_flag", "source": link.source, "note": "source reports applications closed"}
            )
            return Verification.CLOSED, evidence

    fresh = [s for s in vacancy.sources if s.present and now - s.last_seen_at <= FRESH_SIGHTING]
    employer = [s for s in fresh if s.is_employer_requisition and s.url]
    agency = [s for s in fresh if s.is_agency_listing]
    api = [
        s
        for s in fresh
        if s.access_method in (AccessMethod.API, AccessMethod.NATIVE)
        and not s.is_employer_requisition
        and not s.is_agency_listing
    ]
    age_days = (now - vacancy.posted_at).days if vacancy.posted_at else None
    if closing:
        evidence.append({"type": "closing_date", "value": closing.isoformat(), "note": "closing date in future"})

    if employer:
        s = employer[0]
        evidence.append(
            {
                "type": "employer_requisition",
                "source": s.source,
                "board": s.board,
                "requisition": s.source_job_id,
                "url": s.url,
                "seen_at": s.last_seen_at.isoformat(),
                "explicit_open": (s.raw or {}).get("explicit_open"),
                "note": "listed in the employer's live ATS feed",
            }
        )
        return Verification.VERIFIED_OPEN, evidence
    if (
        url_check
        and url_check.job_specific
        and not url_check.login_wall
        and (url_check.open_phrase or (url_check.closing_date and url_check.closing_date >= today))
    ):
        evidence.append(url_check.as_evidence())
        return Verification.VERIFIED_OPEN, evidence
    if url_check:
        evidence.append(url_check.as_evidence())
    if agency:
        s = agency[0]
        evidence.append(
            {
                "type": "agency_listing",
                "source": s.source,
                "board": s.board,
                "url": s.url,
                "seen_at": s.last_seen_at.isoformat(),
                "posted_days_ago": age_days,
            }
        )
        if age_days is not None and age_days <= AGENCY_FRESH_DAYS:
            return Verification.LIKELY_OPEN, evidence
        return Verification.RECRUITER_CONFIRMATION, evidence
    if api:
        s = api[0]
        evidence.append(
            {
                "type": "aggregator_listing",
                "source": s.source,
                "url": s.url,
                "seen_at": s.last_seen_at.isoformat(),
                "posted_days_ago": age_days,
            }
        )
        if age_days is not None and age_days <= AGGREGATOR_FRESH_DAYS:
            return Verification.LIKELY_OPEN, evidence
        return Verification.UNVERIFIED_STALE, evidence
    if vacancy.is_confidential or vacancy.recruiting_agency:
        evidence.append({"type": "no_fresh_sighting", "note": "agency listing not refreshed recently"})
        return Verification.RECRUITER_CONFIRMATION, evidence
    evidence.append(
        {
            "type": "no_fresh_sighting",
            "note": f"last seen {vacancy.last_seen_at.date().isoformat()}; lifecycle {vacancy.lifecycle}",
        }
    )
    return Verification.UNVERIFIED_STALE, evidence


def update_verification(
    session: Session,
    vacancy: Vacancy,
    now: datetime | None = None,
    url_check: UrlCheck | None = None,
    actor: str = "system",
) -> Verification:
    now = now or datetime.now(UTC)
    status, evidence = assess_status(vacancy, now, url_check)
    previous = vacancy.verification_status
    vacancy.verification_status, vacancy.verification_evidence, vacancy.verified_at = status, evidence, now
    if status == Verification.CLOSED and vacancy.lifecycle == Lifecycle.ACTIVE:
        vacancy.lifecycle = Lifecycle.EXPIRED
    if previous != status:
        session.add(
            VacancyEvent(
                vacancy=vacancy, kind="verification_changed", actor=actor, detail={"from": previous, "to": str(status)}
            )
        )
    return status


def verify_now(session: Session, vacancy: Vacancy, http: HttpClient, actor: str = "system") -> Verification:
    """Full verification: re-check the advert/application URL live, then derive the status.
    Called for shortlisted vacancies and immediately before generating application documents."""
    url = vacancy.application_url or vacancy.advert_url
    check = check_url(http, url) if url else None
    return update_verification(session, vacancy, url_check=check, actor=actor)


def require_fresh_verification(vacancy: Vacancy, max_age: timedelta = timedelta(hours=24)) -> None:
    """Guard for document generation: raises unless verified open within `max_age`."""
    if vacancy.verification_status != Verification.VERIFIED_OPEN:
        raise PermissionError(f"vacancy is {vacancy.verification_status}, not VERIFIED OPEN")
    if not vacancy.verified_at or datetime.now(UTC) - vacancy.verified_at > max_age:
        raise PermissionError("verification is older than 24 hours; re-verify first")
