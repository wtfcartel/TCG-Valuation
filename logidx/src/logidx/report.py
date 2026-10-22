"""Daily executive recruitment intelligence report."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from logidx import coverage, recall
from logidx.enums import ApplicationStatus, FitClass, Geography, Lifecycle, SearchStatus, Verification
from logidx.models import Assessment, Document, Notification, Run, SourceSearch, Vacancy, VacancyEvent
from logidx.taxonomy import default_taxonomy

BLOCKED_GEO = [Geography.INTERSTATE, Geography.OVERSEAS, Geography.NATIONAL_UNCONFIRMED]
WORKABLE_GEO = [g for g in Geography if g.melbourne_workable] + [Geography.REGIONAL_VIC, Geography.UNKNOWN]

_env = Environment(loader=PackageLoader("logidx", "web/templates"), autoescape=select_autoescape(["html"]))


@dataclass
class DailyReport:
    day: date
    context: dict[str, Any]
    subject: str
    html: str
    text: str
    body_html: str


def _q(session: Session, *where: Any, order: Any = None, limit: int = 50) -> list[Vacancy]:
    stmt = select(Vacancy).where(*where)
    stmt = stmt.order_by(*(order if isinstance(order, tuple) else (order,))) if order is not None else stmt
    return list(session.scalars(stmt.limit(limit)).all())


def build(session: Session, day: date | None = None) -> DailyReport:
    day = day or coverage.today_local()
    start, end = coverage.day_bounds(day)
    week = start - timedelta(days=7)
    active = Vacancy.lifecycle != Lifecycle.EXPIRED
    rank = (Vacancy.overall_fit.desc().nullslast(), Vacancy.prescore.desc())

    new_priority = _q(
        session,
        Vacancy.first_discovered_at >= start,
        Vacancy.fit_class == FitClass.PRIORITY,
        Vacancy.verification_status == Verification.VERIFIED_OPEN,
        Vacancy.geography.in_([g.value for g in WORKABLE_GEO]),
        order=rank,
    )
    priority_other = _q(
        session,
        active,
        Vacancy.fit_class == FitClass.PRIORITY,
        Vacancy.id.not_in([v.id for v in new_priority]) if new_priority else True,
        Vacancy.geography.in_([g.value for g in WORKABLE_GEO]),
        Vacancy.verification_status != Verification.CLOSED,
        order=rank,
    )
    adjacent = _q(
        session,
        active,
        Vacancy.fit_class == FitClass.ADJACENT,
        Vacancy.first_discovered_at >= week,
        Vacancy.geography.in_([g.value for g in WORKABLE_GEO]),
        Vacancy.verification_status != Verification.CLOSED,
        order=rank,
    )
    exploratory = _q(
        session,
        active,
        Vacancy.fit_class == FitClass.EXPLORATORY,
        Vacancy.first_discovered_at >= week,
        Vacancy.verification_status != Verification.CLOSED,
        order=rank,
        limit=20,
    )
    unassessed = _q(
        session,
        active,
        Vacancy.is_relevant.is_(True),
        Vacancy.fit_class == FitClass.UNASSESSED,
        Vacancy.first_discovered_at >= week,
        Vacancy.verification_status != Verification.CLOSED,
        order=(Vacancy.prescore.desc(), Vacancy.first_discovered_at.desc()),
        limit=30,
    )
    geo_blocked = _q(
        session,
        active,
        Vacancy.geography.in_([g.value for g in BLOCKED_GEO]),
        or_(
            Vacancy.fit_class.in_([FitClass.PRIORITY, FitClass.ADJACENT]),
            (Vacancy.fit_class == FitClass.UNASSESSED) & (Vacancy.prescore >= 6),
        ),
        Vacancy.first_discovered_at >= week,
        order=rank,
        limit=20,
    )
    recruiter_confirm = _q(
        session,
        active,
        Vacancy.is_relevant.is_(True),
        Vacancy.verification_status == Verification.RECRUITER_CONFIRMATION,
        order=rank,
        limit=20,
    )
    changed_ids = {
        e.vacancy_id
        for e in session.scalars(
            select(VacancyEvent).where(
                VacancyEvent.at >= start,
                VacancyEvent.at < end,
                VacancyEvent.kind.in_(["verification_changed", "lifecycle_changed"]),
            )
        ).all()
    }
    closed_stale = [
        v
        for v in (session.get(Vacancy, i) for i in changed_ids)
        if v is not None
        and v.is_relevant
        and v.verification_status in (Verification.CLOSED, Verification.UNVERIFIED_STALE)
    ]
    seen_today = Vacancy.last_seen_at >= start
    prior = _q(
        session,
        seen_today,
        Vacancy.application_status.in_(
            [
                ApplicationStatus.APPLIED,
                ApplicationStatus.REJECTED,
                ApplicationStatus.WITHDRAWN,
                ApplicationStatus.INTERVIEWING,
                ApplicationStatus.OFFER,
            ]
        ),
        limit=30,
    )
    status_events = session.scalars(
        select(VacancyEvent).where(
            VacancyEvent.at >= start, VacancyEvent.at < end, VacancyEvent.kind == "status_changed"
        )
    ).all()

    runs = session.scalars(
        select(Run).where(Run.started_at >= start, Run.started_at < end).order_by(Run.started_at)
    ).all()
    failures = session.scalars(
        select(SourceSearch).where(
            SourceSearch.started_at >= start,
            SourceSearch.started_at < end,
            SourceSearch.status.in_([SearchStatus.FAILED, SearchStatus.ACCESS_BLOCKED]),
        )
    ).all()
    ai_errors = session.scalars(
        select(Assessment).where(
            Assessment.created_at >= start, Assessment.created_at < end, Assessment.valid.is_(False)
        )
    ).all()
    docs = session.scalars(select(Document).where(Document.created_at >= start, Document.created_at < end)).all()
    notifications = session.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(5)).all()

    sources = coverage.source_matrix(session, day)
    categories = coverage.category_matrix(session, day)
    remediation: list[str] = []
    for row in sources:
        if row.status == SearchStatus.NOT_SEARCHED and row.limitations:
            remediation.append(f"{row.label}: {row.limitations[0]}")
    for c in categories:
        if c.status != "COMPLETE":
            remediation.append(f"Discipline '{c.label}': {c.status} — {c.note}")
    if not runs:
        remediation.insert(0, "No discovery run recorded today. Check the scheduler.")

    ctx = {
        "day": day,
        "generated_at": datetime.now(UTC),
        "taxonomy": default_taxonomy(),
        "new_priority": new_priority,
        "priority_other": priority_other,
        "adjacent": adjacent,
        "exploratory": exploratory,
        "unassessed": unassessed,
        "geo_blocked": geo_blocked,
        "recruiter_confirm": recruiter_confirm,
        "closed_stale": closed_stale,
        "prior": prior,
        "status_events": status_events,
        "runs": runs,
        "failures": failures,
        "ai_errors": ai_errors,
        "docs": docs,
        "notifications": notifications,
        "sources": sources,
        "categories": categories,
        "recall": recall.metrics(session, start - timedelta(days=1)),
        "remediation": remediation,
        "gmail_note": "Gmail correspondence reconciliation is not implemented yet (Phase 4); "
        "application changes below are those recorded in LogiDx.",
    }
    n_open = len(new_priority)
    subject = (
        f"LogiDx {day:%a %d %b}: {n_open} new verified-open Priority · {len(adjacent)} Adjacent · "
        f"{sum(1 for c in categories if c.status == 'COMPLETE')}/9 disciplines complete"
    )
    html = _env.get_template("report_email.html").render(**ctx)
    body_html = _env.get_template("report_body.html").render(**ctx)
    text = _env.get_template("report_email.txt").render(**ctx)
    return DailyReport(day, ctx, subject, html, text, body_html)
