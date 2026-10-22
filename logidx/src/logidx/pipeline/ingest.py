"""Turn a RawVacancy into a persistent, de-duplicated, classified Vacancy record."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from logidx.enums import AccessMethod, ApplicationStatus, Lifecycle, WorkMode
from logidx.models import Agency, Run, Vacancy, VacancyEvent, VacancySource
from logidx.pipeline import dedup
from logidx.pipeline.location import classify_location
from logidx.pipeline.normalize import (
    canonical_url,
    clean_title,
    description_hash,
    extract_reference,
    norm_company,
    norm_title,
)
from logidx.pipeline.salary import parse_salary
from logidx.profile import CandidateProfile
from logidx.sources.base import RawVacancy
from logidx.taxonomy import Taxonomy

DEDUP_WINDOW = timedelta(days=120)


@dataclass
class IngestOutcome:
    vacancy: Vacancy
    is_new: bool
    merged_reason: str | None = None


def _event(session: Session, vacancy: Vacancy, kind: str, actor: str = "system", **detail: object) -> None:
    session.add(VacancyEvent(vacancy=vacancy, kind=kind, actor=actor, detail=detail))


def apply_derived(vacancy: Vacancy, taxonomy: Taxonomy, profile: CandidateProfile) -> None:
    """(Re)compute every deterministic field from the vacancy's current text."""
    threshold = profile.remuneration.discovery_threshold_base_aud
    salary = parse_salary(vacancy.salary_text)
    if not salary.disclosed:
        snippet = _salary_snippet(vacancy.description)
        salary = parse_salary(snippet)
        if salary.disclosed:
            vacancy.salary_text = snippet
    if salary.disclosed:
        vacancy.salary_min, vacancy.salary_max = salary.min_annual, salary.max_annual
        vacancy.salary_period, vacancy.salary_currency = salary.period, salary.currency
        vacancy.salary_includes_super = salary.includes_super
        vacancy.salary_base_estimate_max = salary.base_estimate_max
        vacancy.benefits = salary.benefits
    vacancy.salary_below_threshold = bool(
        vacancy.salary_base_estimate_max is not None and vacancy.salary_base_estimate_max < threshold
    )

    geo = classify_location(vacancy.location_text, vacancy.description, vacancy.title)
    vacancy.geography, vacancy.geography_reason = geo.geography, geo.reason
    if geo.work_mode != WorkMode.UNKNOWN or not vacancy.work_mode:
        vacancy.work_mode = geo.work_mode  # keep an adapter-supplied mode when the text says nothing
    vacancy.work_base, vacancy.travel_requirements = geo.work_base, geo.travel

    c = taxonomy.classify(vacancy.title, vacancy.description, vacancy.salary_base_estimate_max, threshold)
    vacancy.categories = sorted(c.categories, key=lambda k: -c.categories[k])
    vacancy.primary_category = c.primary_category
    vacancy.families = list(c.families)
    vacancy.seniority_signal = c.seniority
    vacancy.relevance_flags = c.flags
    vacancy.prescore = c.prescore
    vacancy.is_relevant = c.is_relevant
    vacancy.description_hash = description_hash(vacancy.description)
    vacancy.reference = vacancy.reference or extract_reference(vacancy.title, vacancy.description)


def _salary_snippet(description: str) -> str | None:
    """Find a salary statement in the description (first sentence containing a $ figure and a pay word)."""
    for sentence in re.split(r"(?<=[.\n])\s+", description or ""):
        if "$" in sentence and re.search(
            r"salary|package|remuneration|base|per annum|p\.a|super|rate|\bk\b", sentence, re.I
        ):
            return sentence[:300]
    return None


def _agency(session: Session, name: str | None) -> Agency | None:
    if not name:
        return None
    agency = session.scalar(select(Agency).where(Agency.name == name))
    if agency is None:
        agency = Agency(name=name)
        session.add(agency)
    return agency


def ingest(
    session: Session,
    raw: RawVacancy,
    *,
    run: Run | None,
    access_method: AccessMethod,
    taxonomy: Taxonomy,
    profile: CandidateProfile,
    now: datetime | None = None,
) -> IngestOutcome:
    now = now or datetime.now(UTC)
    title = clean_title(raw.title)
    link = session.scalar(
        select(VacancySource).where(
            VacancySource.source == raw.source, VacancySource.source_job_id == raw.source_job_id
        )
    )
    if link is not None:
        vacancy = link.vacancy
        _refresh_link(link, raw, run, now)
        changed = _merge_fields(vacancy, raw, title)
        vacancy.last_seen_at = now
        if vacancy.lifecycle != Lifecycle.ACTIVE and not _closed_by_date(vacancy, now):
            _event(session, vacancy, "reappeared", source=raw.source)
            vacancy.lifecycle = Lifecycle.ACTIVE
        if changed:
            apply_derived(vacancy, taxonomy, profile)
        return IngestOutcome(vacancy, is_new=False)

    incoming = dedup.Incoming(
        norm_employer=norm_company(raw.employer),
        agency=raw.agency,
        normalized_title=norm_title(title),
        location=raw.location,
        description=raw.description,
        description_is_snippet=raw.description_is_snippet,
        description_hash=description_hash(raw.description),
        reference=raw.reference or extract_reference(raw.title, raw.description),
    )
    match = None
    if incoming.norm_employer or incoming.agency:
        conditions = []
        if incoming.norm_employer:
            conditions.append(Vacancy.norm_employer == incoming.norm_employer)
        if incoming.agency:
            conditions.append(Vacancy.recruiting_agency == incoming.agency)
        rows = session.scalars(
            select(Vacancy).where(or_(*conditions), Vacancy.first_discovered_at >= now - DEDUP_WINDOW)
        ).all()
        candidates = [
            dedup.DedupCandidate(
                v.id,
                v.norm_employer,
                v.recruiting_agency,
                v.normalized_title,
                v.location_text,
                v.description,
                v.description_is_snippet,
                v.description_hash,
                v.reference,
            )
            for v in rows
        ]
        match = dedup.find_duplicate(incoming, candidates)

    if match is not None:
        vacancy = session.get(Vacancy, match[0])
        assert vacancy is not None
        _merge_fields(vacancy, raw, title)
        vacancy.last_seen_at = now
        if vacancy.lifecycle != Lifecycle.ACTIVE and not _closed_by_date(vacancy, now):
            vacancy.lifecycle = Lifecycle.ACTIVE
        session.add(_new_link(vacancy, raw, run, access_method, now))
        _event(
            session, vacancy, "cross_post_merged", source=raw.source, source_job_id=raw.source_job_id, reason=match[1]
        )
        apply_derived(vacancy, taxonomy, profile)
        return IngestOutcome(vacancy, is_new=False, merged_reason=match[1])

    vacancy = Vacancy(
        employer=raw.employer,
        is_confidential=not raw.employer and bool(raw.agency),
        recruiting_agency=raw.agency,
        agency=_agency(session, raw.agency) if raw.agency else None,
        title=title,
        original_title=raw.title,
        normalized_title=incoming.normalized_title,
        norm_employer=incoming.norm_employer,
        description=raw.description,
        description_is_snippet=raw.description_is_snippet,
        reference=incoming.reference,
        employment_type=raw.employment_type,
        location_text=raw.location,
        salary_text=raw.salary_text,
        posted_at=raw.posted_at,
        closing_date=raw.closing_date,
        first_discovered_at=now,
        last_seen_at=now,
        advert_url=canonical_url(raw.url),
        application_url=raw.apply_url,
        application_status=ApplicationStatus.DISCOVERED,
        lifecycle=Lifecycle.ACTIVE,
    )
    if not raw.salary_text and (raw.salary_min or raw.salary_max) and not raw.salary_predicted:
        vacancy.salary_min, vacancy.salary_max = raw.salary_min, raw.salary_max
        hi = raw.salary_max or raw.salary_min
        lo = raw.salary_min or raw.salary_max
        vacancy.salary_text = f"${lo:,.0f} – ${hi:,.0f} (structured field from {raw.source})"
    vacancy.work_mode = _mode_from_hint(raw.work_mode_hint)
    session.add(vacancy)
    session.add(_new_link(vacancy, raw, run, access_method, now))
    apply_derived(vacancy, taxonomy, profile)
    if _closed_by_date(vacancy, now):
        vacancy.lifecycle = Lifecycle.EXPIRED
    _event(
        session,
        vacancy,
        "discovered",
        source=raw.source,
        source_job_id=raw.source_job_id,
        access_method=str(access_method),
        run_id=run.id if run else None,
    )
    return IngestOutcome(vacancy, is_new=True)


def _mode_from_hint(hint: str | None) -> str:
    low = (hint or "").lower()
    for word, mode in (("hybrid", WorkMode.HYBRID), ("remote", WorkMode.REMOTE), ("on", WorkMode.ONSITE)):
        if word in low:
            return mode
    return WorkMode.UNKNOWN


def _closed_by_date(vacancy: Vacancy, now: datetime) -> bool:
    return vacancy.closing_date is not None and vacancy.closing_date < now.date()


def _new_link(vacancy: Vacancy, raw: RawVacancy, run: Run | None, access: AccessMethod, now: datetime) -> VacancySource:
    return VacancySource(
        vacancy=vacancy,
        source=raw.source,
        board=raw.board,
        source_job_id=raw.source_job_id,
        access_method=str(access),
        is_employer_requisition=raw.is_employer_requisition,
        is_agency_listing=raw.is_agency_listing,
        url=raw.url,
        apply_url=raw.apply_url,
        first_seen_at=now,
        last_seen_at=now,
        last_seen_run_id=run.id if run else None,
        present=True,
        raw={
            **raw.raw,
            "explicit_open": raw.explicit_open,
            "posted_at": raw.posted_at.isoformat() if raw.posted_at else None,
        },
    )


def _refresh_link(link: VacancySource, raw: RawVacancy, run: Run | None, now: datetime) -> None:
    link.last_seen_at = now
    link.last_seen_run_id = run.id if run else link.last_seen_run_id
    link.present = True
    link.url = raw.url or link.url
    link.apply_url = raw.apply_url or link.apply_url
    link.raw = {**(link.raw or {}), **raw.raw, "explicit_open": raw.explicit_open}


def _merge_fields(vacancy: Vacancy, raw: RawVacancy, title: str) -> bool:
    """Enrich an existing vacancy from a new sighting. Employer requisitions and full text win.
    Returns True if text that drives classification changed."""
    changed = False
    if (
        raw.description
        and (vacancy.description_is_snippet or not vacancy.description)
        and (not raw.description_is_snippet or len(raw.description) > len(vacancy.description))
    ):
        vacancy.description = raw.description
        vacancy.description_is_snippet = raw.description_is_snippet
        changed = True
    if raw.is_employer_requisition:
        vacancy.advert_url = canonical_url(raw.url) or vacancy.advert_url
        vacancy.application_url = raw.apply_url or vacancy.application_url
        if raw.employer and not vacancy.employer:
            vacancy.employer, vacancy.norm_employer = raw.employer, norm_company(raw.employer)
            vacancy.is_confidential = False
    else:
        vacancy.advert_url = vacancy.advert_url or canonical_url(raw.url)
        vacancy.application_url = vacancy.application_url or raw.apply_url
    if raw.agency and not vacancy.recruiting_agency:
        vacancy.recruiting_agency = raw.agency
    if (
        raw.location
        and raw.location != vacancy.location_text
        and (raw.is_employer_requisition or not vacancy.location_text)
    ):
        vacancy.location_text = raw.location
        changed = True
    if raw.closing_date and raw.closing_date != vacancy.closing_date:
        vacancy.closing_date = raw.closing_date
    if raw.posted_at and (vacancy.posted_at is None or raw.posted_at > vacancy.posted_at):
        vacancy.posted_at = raw.posted_at
    if raw.salary_text and not vacancy.salary_text:
        vacancy.salary_text = raw.salary_text
        changed = True
    if title != vacancy.title and raw.is_employer_requisition:
        vacancy.title, vacancy.normalized_title = title, norm_title(title)
        changed = True
    return changed
