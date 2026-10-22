"""Known-vacancy recall regression.

Live cases are matched against discovered vacancies after each run. When a case is not found, the
cause is diagnosed (source access, query coverage, classification, location filtering, deduplication,
indexing/freshness) and stored with the result, so a correction can be re-tested on the next run.
Taxonomy fixtures run offline through the classifier and location rules.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from logidx.enums import MissCause, RecallOutcome, SearchStatus
from logidx.models import RecallCase, RecallResult, Run, SourceSearch, Vacancy, VacancyEvent, VacancySource
from logidx.pipeline.location import classify_location
from logidx.pipeline.normalize import norm_title
from logidx.settings import get_settings
from logidx.taxonomy import Taxonomy, default_taxonomy


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or get_settings().config_dir / "recall_cases.yaml"
    with path.open(encoding="utf-8") as fh:
        return list((yaml.safe_load(fh) or {}).get("cases", []))


def sync_cases(session: Session, cases: list[dict[str, Any]] | None = None) -> None:
    for spec in cases if cases is not None else load_cases():
        row = session.scalar(select(RecallCase).where(RecallCase.key == spec["key"]))
        if row is None:
            session.add(RecallCase(key=spec["key"], label=spec["label"], spec=spec))
        else:
            row.label, row.spec = spec["label"], spec
    session.flush()


@dataclass
class FixtureResult:
    key: str
    label: str
    passed: bool
    problems: list[str] = field(default_factory=list)
    observed: dict[str, Any] = field(default_factory=dict)


def check_probe(spec: dict[str, Any], taxonomy: Taxonomy) -> FixtureResult:
    """Run a case's probe through classification and location rules and compare with `expected`."""
    probe, expected = spec.get("probe") or {}, spec.get("expected") or {}
    c = taxonomy.classify(probe.get("title", ""), probe.get("description", ""))
    geo = classify_location(probe.get("location"), probe.get("description", ""))
    observed = {
        "relevant": c.is_relevant,
        "category": c.primary_category,
        "categories": list(c.categories),
        "geography": str(geo.geography),
        "seniority": c.seniority,
    }
    problems = []
    if "relevant" in expected and expected["relevant"] != c.is_relevant:
        problems.append(f"relevant expected {expected['relevant']}, got {c.is_relevant} (seniority {c.seniority})")
    if expected.get("category") and expected["category"] not in c.categories:
        problems.append(f"category {expected['category']} not assigned (got {list(c.categories) or 'none'})")
    if expected.get("geography") and probe.get("location") is not None and expected["geography"] != str(geo.geography):
        problems.append(f"geography expected {expected['geography']}, got {geo.geography}")
    return FixtureResult(spec["key"], spec["label"], not problems, problems, observed)


def taxonomy_fixtures(
    taxonomy: Taxonomy | None = None, cases: list[dict[str, Any]] | None = None
) -> list[FixtureResult]:
    taxonomy = taxonomy or default_taxonomy()
    return [
        check_probe(s, taxonomy) for s in (cases if cases is not None else load_cases()) if s.get("kind") == "taxonomy"
    ]


def _find(session: Session, spec: dict[str, Any]) -> tuple[Vacancy | None, str | None]:
    match = spec.get("match") or {}
    for pattern in match.get("source_ids", []):
        source, _, ident = pattern.partition(":")
        links = session.scalars(select(VacancySource).where(VacancySource.source == source)).all()
        for link in links:
            if fnmatch.fnmatch(link.source_job_id, ident):
                return link.vacancy, f"source id {link.source}:{link.source_job_id}"
    refs = [r.upper() for r in match.get("references", [])]
    if refs:
        v = session.scalar(select(Vacancy).where(Vacancy.reference.in_(refs)))
        if v:
            return v, f"reference {v.reference}"
    titles = [norm_title(t) for t in match.get("title_any", [])]
    parties = [p.lower() for p in match.get("party_any", [])]
    if titles:
        for v in session.scalars(select(Vacancy)).all():
            party = f"{v.employer or ''} {v.recruiting_agency or ''}".lower()
            if parties and not any(p in party for p in parties):
                continue
            if any(fuzz.token_sort_ratio(t, v.normalized_title) >= 90 for t in titles):
                return v, "title and advertiser match"
    return None, None


def _carrier_statuses(session: Session, carriers: list[str], since: datetime) -> dict[str, str]:
    out: dict[str, str] = {}
    for carrier in carriers:
        rows = session.scalars(
            select(SourceSearch).where(
                (SourceSearch.source == carrier) | (SourceSearch.board == carrier), SourceSearch.started_at >= since
            )
        ).all()
        statuses = {r.status for r in rows}
        succeeded = [s for s in statuses if SearchStatus(s).succeeded]
        if succeeded:
            out[carrier] = succeeded[0]
        elif statuses:
            out[carrier] = sorted(statuses)[0]
        else:
            out[carrier] = "NO RECORD"
    return out


def evaluate_case(
    session: Session, case: RecallCase, run: Run | None, taxonomy: Taxonomy, now: datetime | None = None
) -> RecallResult:
    now = now or datetime.now(UTC)
    spec = case.spec
    vacancy, how = _find(session, spec)
    detail: dict[str, Any] = {}
    if vacancy is not None:
        detail = {
            "matched_by": how,
            "vacancy_title": vacancy.title,
            "geography": vacancy.geography,
            "verification": vacancy.verification_status,
            "relevant": vacancy.is_relevant,
        }
        expected = spec.get("expected") or {}
        issues = []
        if expected.get("geography") and vacancy.geography != expected["geography"]:
            issues.append(f"geography {vacancy.geography} ≠ expected {expected['geography']}")
        if "relevant" in expected and vacancy.is_relevant != expected["relevant"]:
            issues.append("classified as not relevant")
        detail["issues"] = issues
        cause = MissCause.CLASSIFICATION if issues else None
        latency = None
        published = spec.get("first_published")
        if published:
            latency = (vacancy.first_discovered_at - datetime.fromisoformat(published).replace(tzinfo=UTC)) / timedelta(
                hours=1
            )
        result = RecallResult(
            case=case,
            run_id=run.id if run else None,
            outcome=RecallOutcome.FOUND,
            cause=cause,
            vacancy_id=vacancy.id,
            latency_hours=latency,
            detail=detail,
            at=now,
        )
    else:
        carriers = spec.get("carried_by", [])
        statuses = _carrier_statuses(session, carriers, now - timedelta(days=1))
        searched = [c for c, s in statuses.items() if s in {x.value for x in SearchStatus if x.succeeded}]
        probe = check_probe(spec, taxonomy)
        detail = {"carrier_statuses": statuses, "probe": probe.observed, "probe_problems": probe.problems}
        if not searched:
            outcome, cause = RecallOutcome.ACCESS_GAP, MissCause.SOURCE_ACCESS
            detail["explanation"] = "no source believed to carry this advert was searched successfully in the last day"
        else:
            outcome = RecallOutcome.MISSED
            if probe.problems and not probe.observed.get("relevant"):
                cause = MissCause.QUERY_COVERAGE
            elif _near_merge(session, spec):
                cause = MissCause.DEDUPLICATION
            else:
                cause = MissCause.INDEXING
            detail["explanation"] = f"searched {', '.join(searched)} but not found"
        result = RecallResult(
            case=case, run_id=run.id if run else None, outcome=outcome, cause=cause, detail=detail, at=now
        )
    session.add(result)
    return result


def _near_merge(session: Session, spec: dict[str, Any]) -> bool:
    titles = [norm_title(t) for t in (spec.get("match") or {}).get("title_any", [])]
    events = session.scalars(select(VacancyEvent).where(VacancyEvent.kind == "cross_post_merged")).all()
    for e in events:
        v = e.vacancy
        if any(fuzz.partial_ratio(t, v.normalized_title) >= 85 for t in titles):
            return True
    return False


def evaluate_all(session: Session, run: Run | None = None, taxonomy: Taxonomy | None = None) -> list[RecallResult]:
    taxonomy = taxonomy or default_taxonomy()
    sync_cases(session)
    results = []
    for case in session.scalars(select(RecallCase).where(RecallCase.active.is_(True))).all():
        if case.spec.get("kind") == "live":
            results.append(evaluate_case(session, case, run, taxonomy))
    session.flush()
    return results


def metrics(session: Session, since: datetime) -> dict[str, Any]:
    """Recall and quality metrics over results recorded since `since` (latest result per case)."""
    latest: dict[int, RecallResult] = {}
    for r in session.scalars(select(RecallResult).where(RecallResult.at >= since).order_by(RecallResult.at)).all():
        latest[r.case_id] = r
    found = sum(1 for r in latest.values() if r.outcome == RecallOutcome.FOUND)
    missed = sum(1 for r in latest.values() if r.outcome == RecallOutcome.MISSED)
    gaps = sum(1 for r in latest.values() if r.outcome == RecallOutcome.ACCESS_GAP)
    accessible = found + missed
    sightings = session.scalar(select(func.count(VacancySource.id))) or 0
    merges = session.scalar(select(func.count(VacancyEvent.id)).where(VacancyEvent.kind == "cross_post_merged")) or 0
    fixtures = taxonomy_fixtures()
    latencies = [r.latency_hours for r in latest.values() if r.latency_hours is not None]
    return {
        "live_cases": len(latest),
        "found": found,
        "missed": missed,
        "access_gaps": gaps,
        "recall_accessible": round(found / accessible, 3) if accessible else None,
        "duplicate_merge_rate": round(merges / sightings, 3) if sightings else None,
        "median_latency_hours": sorted(latencies)[len(latencies) // 2] if latencies else None,
        "fixtures_total": len(fixtures),
        "fixtures_passed": sum(1 for f in fixtures if f.passed),
        "fixture_failures": [{"key": f.key, "problems": f.problems} for f in fixtures if not f.passed],
    }
