"""One discovery run: search every source independently, ingest, expire, verify, audit coverage.

Failure isolation: each (source, query) and each board is its own try/except, its own SourceSearch
row and its own status. One source failing never stops another, and a failed search is recorded as
FAILED / ACCESS BLOCKED — never as zero results.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from logidx import locks
from logidx.enums import AccessMethod, Lifecycle, RunStatus, SearchStatus, Verification
from logidx.models import CategoryAudit, Run, SourceSearch, Vacancy, VacancyEvent, VacancySource
from logidx.pipeline.ingest import ingest
from logidx.profile import CandidateProfile, get_profile
from logidx.schedule_config import get_schedule
from logidx.sources.adzuna import max_age_for
from logidx.sources.base import BoardConfig, BoardSource, FetchResult, QuerySource, RestrictedSource
from logidx.sources.http import HttpClient, SourceError
from logidx.sources.registry import RESTRICTED, Watchlist, board_sources, load_watchlist, query_sources
from logidx.taxonomy import GENERIC_FAMILIES, Taxonomy, default_taxonomy
from logidx.verification import update_verification

log = logging.getLogger(__name__)
LOCK_NAME = "discovery"
NOT_SEEN_GRACE = timedelta(days=3)
WINDOWED_RETIRE = timedelta(days=21)
MAX_CONSECUTIVE_BLOCKS = 3
TIME_BUDGET_NOTE = "skipped: this run's time budget was used up (serverless request limit)"


@dataclass
class RunPlan:
    query_sources: list[QuerySource]
    board_sources: dict[str, BoardSource]
    watchlist: Watchlist
    restricted: list[RestrictedSource]


@dataclass
class _Tally:
    vacancy_ids: set[int] = field(default_factory=set)
    new_ids: set[int] = field(default_factory=set)
    failed: int = 0


def default_plan() -> RunPlan:
    return RunPlan(query_sources(), board_sources(), load_watchlist(), RESTRICTED)


def start_run(
    session: Session,
    *,
    trigger: str,
    idempotency_key: str | None = None,
    slot: str | None = None,
    scheduled_for: datetime | None = None,
) -> Run | None:
    """Create the run row. Returns None if this idempotency key already ran (duplicate trigger)."""
    run = Run(
        idempotency_key=idempotency_key or f"{trigger}:{uuid.uuid4()}",
        trigger=trigger,
        slot=slot,
        scheduled_for=scheduled_for,
        status=RunStatus.RUNNING,
    )
    session.add(run)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    return run


def run_discovery(
    session: Session,
    run: Run,
    *,
    http: HttpClient | None = None,
    plan: RunPlan | None = None,
    taxonomy: Taxonomy | None = None,
    now: Callable[[], datetime] | None = None,
    post_run: Callable[[Session, Run], None] | None = None,
    time_budget: float | None = None,
) -> Run:
    """`time_budget` (seconds) stops new searches once spent — used on serverless hosts with a request limit."""
    clock = now or (lambda: datetime.now(UTC))
    deadline = time.monotonic() + time_budget if time_budget else None
    holder = f"run:{run.id}"
    if not locks.acquire(session, LOCK_NAME, holder):
        run.status, run.finished_at = RunStatus.SKIPPED, clock()
        run.error = "another discovery run is in progress"
        session.commit()
        return run
    own_http = http is None
    http = http or HttpClient()
    try:
        _execute(session, run, http, plan or default_plan(), taxonomy or default_taxonomy(), clock, deadline)
        if post_run is not None:
            try:
                post_run(session, run)
            except Exception as exc:  # post-run steps (AI, recall, report) must not fail discovery
                log.exception("post-run step failed")
                run.counts = {**run.counts, "post_run_error": str(exc)[:500]}
                session.commit()
    except Exception as exc:
        log.exception("discovery run failed")
        session.rollback()
        run.status, run.error = RunStatus.FAILED, f"{type(exc).__name__}: {exc}"[:2000]
        run.finished_at = clock()
        session.commit()
    finally:
        locks.release(session, LOCK_NAME, holder)
        if own_http:
            http.close()
    return run


def _execute(
    session: Session,
    run: Run,
    http: HttpClient,
    plan: RunPlan,
    taxonomy: Taxonomy,
    clock: Callable[[], datetime],
    deadline: float | None = None,
) -> None:
    def out_of_time() -> bool:
        return deadline is not None and time.monotonic() >= deadline

    profile = get_profile(session)
    schedule = get_schedule(session)
    slot_index = schedule.slot_index(run.slot) if run.slot else _manual_slot_index(session, len(schedule.slots))
    queries = taxonomy.queries_for_run(slot_index, len(schedule.slots))
    touched: set[int] = set()
    succeeded_full_boards: set[tuple[str, str]] = set()
    windowed: set[str] = set()
    cat_queries: dict[str, list[str]] = defaultdict(list)
    cat_ok: dict[str, set[str]] = defaultdict(set)
    cat_failed: dict[str, set[str]] = defaultdict(set)
    not_searched: list[str] = []
    ids_by_search: dict[int, set[int]] = {}

    # 1. Restricted sources: never contacted; recorded so the gap is always visible.
    for rs in plan.restricted:
        session.add(
            SourceSearch(
                run=run,
                source=rs.name,
                source_label=rs.label,
                access_method=AccessMethod.NONE,
                status=SearchStatus.NOT_SEARCHED,
                limitation=rs.limitation,
                started_at=clock(),
            )
        )
        not_searched.append(rs.label)

    # 2. Query sources, every category independently.
    for qs in plan.query_sources:
        ok, reason = qs.available
        if not ok:
            session.add(
                SourceSearch(
                    run=run,
                    source=qs.name,
                    source_label=qs.label,
                    access_method=qs.access_method,
                    status=SearchStatus.NOT_SEARCHED,
                    limitation=reason,
                    started_at=clock(),
                )
            )
            not_searched.append(f"{qs.label} ({reason})")
            continue
        last_ok = session.scalar(
            select(func.max(SourceSearch.started_at)).where(
                SourceSearch.source == qs.name,
                SourceSearch.status.in_(
                    [SearchStatus.API_SEARCHED, SearchStatus.NATIVE_SEARCHED, SearchStatus.INDEXED_FALLBACK_ONLY]
                ),
            )
        )
        max_age = max_age_for(last_ok)
        blocks = 0
        windowed.add(qs.name)
        for category, qlist in queries.items():
            for q in qlist:
                cat_queries[category].append(q)
                if blocks >= MAX_CONSECUTIVE_BLOCKS or out_of_time():
                    session.add(
                        SourceSearch(
                            run=run,
                            source=qs.name,
                            source_label=qs.label,
                            query=q,
                            category=category,
                            access_method=qs.access_method,
                            status=SearchStatus.NOT_SEARCHED,
                            started_at=clock(),
                            limitation=TIME_BUDGET_NOTE
                            if blocks < MAX_CONSECUTIVE_BLOCKS
                            else "skipped after repeated access refusals this run",
                        )
                    )
                    cat_failed[category].add(qs.label)
                    continue
                search = _search_row(run, qs.name, qs.label, qs.access_method, clock, query=q, category=category)
                session.add(search)
                t0 = time.monotonic()
                try:
                    result = qs.search(http, q, max_age_days=max_age)
                except SourceError as exc:
                    _fail(search, exc, t0)
                    cat_failed[category].add(qs.label)
                    blocks = blocks + 1 if exc.blocked else 0
                    continue
                except Exception as exc:  # adapter bug: isolate and record
                    log.exception("query source crashed", extra={"source": qs.name})
                    _fail(search, SourceError(f"{type(exc).__name__}: {exc}"), t0)
                    cat_failed[category].add(qs.label)
                    continue
                blocks = 0
                search.status = (
                    SearchStatus.INDEXED_FALLBACK_ONLY
                    if qs.access_method == AccessMethod.INDEXED_FALLBACK
                    else SearchStatus.API_SEARCHED
                )
                tally = _ingest_all(session, run, result, qs.access_method, taxonomy, profile, clock)
                _fill(search, result, tally, session, t0, ids_by_search)
                touched |= tally.vacancy_ids
                cat_ok[category].add(qs.label)

    # 3. Boards (employer ATS, agency ATS, feeds): one fetch each, taxonomy applied locally.
    def title_filter(title: str) -> bool:
        # Fetch full descriptions for anything that could be relevant once responsibilities are read.
        c = taxonomy.classify(title)
        if c.seniority == "excluded":
            return False
        return (
            c.is_relevant or c.seniority in ("executive", "senior", "lead") or bool(set(c.families) - GENERIC_FAMILIES)
        )

    for board in plan.watchlist.boards:
        source = plan.board_sources.get(board.ats)
        label = f"{board.name} ({board.ats})"
        if source is None or not board.configured:
            reason = (
                "ATS not yet identified"
                if source is None
                else "disabled"
                if not board.enabled
                else "board identifier not configured"
            )
            session.add(
                SourceSearch(
                    run=run,
                    source=board.ats if source else "unconfigured",
                    source_label=label,
                    board=board.key,
                    access_method=AccessMethod.NONE,
                    status=SearchStatus.NOT_SEARCHED,
                    limitation=reason,
                    started_at=clock(),
                )
            )
            continue
        if out_of_time():
            session.add(
                SourceSearch(
                    run=run,
                    source=source.name,
                    source_label=label,
                    board=board.key,
                    access_method=source.access_method,
                    status=SearchStatus.NOT_SEARCHED,
                    limitation=TIME_BUDGET_NOTE,
                    started_at=clock(),
                )
            )
            for cat in taxonomy.category_keys:
                cat_failed[cat].add(label)
            continue
        search = _search_row(run, source.name, label, source.access_method, clock, board=board.key)
        session.add(search)
        t0 = time.monotonic()
        try:
            result = source.fetch(http, board, title_filter)
        except SourceError as exc:
            _fail(search, exc, t0)
            for cat in taxonomy.category_keys:
                cat_failed[cat].add(label)
            continue
        except Exception as exc:
            log.exception("board source crashed", extra={"board": board.key})
            _fail(search, SourceError(f"{type(exc).__name__}: {exc}"), t0)
            for cat in taxonomy.category_keys:
                cat_failed[cat].add(label)
            continue
        search.status = SearchStatus.NATIVE_SEARCHED
        _tag_board(result, board)
        tally = _ingest_all(session, run, result, source.access_method, taxonomy, profile, clock)
        _fill(search, result, tally, session, t0, ids_by_search)
        touched |= tally.vacancy_ids
        if not result.truncated:
            succeeded_full_boards.add((source.name, board.key))
        for cat in taxonomy.category_keys:
            cat_ok[cat].add(label)
    session.flush()

    # 4. Lifecycle: absence only counts against sources that succeeded with a complete listing.
    touched |= _expire(session, run, succeeded_full_boards, windowed, clock())

    # 5. Verification for everything seen or expired this run.
    now = clock()
    for vid in touched:
        vacancy = session.get(Vacancy, vid)
        if vacancy is not None:
            update_verification(session, vacancy, now)
    session.flush()
    for search in run.searches:
        if search.status in (
            SearchStatus.API_SEARCHED,
            SearchStatus.NATIVE_SEARCHED,
            SearchStatus.INDEXED_FALLBACK_ONLY,
        ):
            ids = ids_by_search.get(search.id, set())
            search.verified_open = sum(
                1
                for i in ids
                if (v := session.get(Vacancy, i)) is not None and v.verification_status == Verification.VERIFIED_OPEN
            )

    # 6. Category audit.
    run_vacancies = [session.get(Vacancy, i) for i in touched]
    for cat in taxonomy.category_keys:
        in_cat = [v for v in run_vacancies if v is not None and cat in (v.categories or [])]
        complete = bool(cat_ok[cat]) and not cat_failed[cat]
        note = None
        if not cat_ok[cat]:
            note = "NOT SEARCHED SUCCESSFULLY — no source returned results for this category in this run"
        elif cat_failed[cat]:
            note = f"INCOMPLETE — failed: {', '.join(sorted(cat_failed[cat]))}"
        session.add(
            CategoryAudit(
                run=run,
                category=cat,
                complete=complete,
                queries=sorted(set(cat_queries[cat])),
                sources_succeeded=sorted(cat_ok[cat]),
                sources_failed=sorted(cat_failed[cat]),
                sources_not_searched=not_searched,
                results_retrieved=len(in_cat),
                relevant_vacancies=sum(1 for v in in_cat if v.is_relevant),
                note=note,
            )
        )

    attempted = [s for s in run.searches if s.status not in (SearchStatus.NOT_SEARCHED,)]
    failed = [s for s in attempted if s.status in (SearchStatus.FAILED, SearchStatus.ACCESS_BLOCKED)]
    all_complete = all(a.complete for a in run.category_audits)
    run.status = RunStatus.SUCCEEDED if attempted and not failed and all_complete else RunStatus.PARTIAL
    if not attempted:
        run.status = RunStatus.FAILED
        run.error = "no source could be searched (see Search Coverage for reasons)"
    run.counts = {
        "searches_attempted": len(attempted),
        "searches_failed": len(failed),
        "sources_not_searched": sum(1 for s in run.searches if s.status == SearchStatus.NOT_SEARCHED),
        "vacancies_seen": len(touched),
        "new_vacancies": sum(s.new_vacancies for s in run.searches),
        "relevant_seen": sum(1 for v in run_vacancies if v is not None and v.is_relevant),
        "categories_complete": sum(1 for a in run.category_audits if a.complete),
    }
    run.finished_at = clock()
    session.commit()


def _manual_slot_index(session: Session, slots: int) -> int:
    count = session.scalar(select(func.count(Run.id)).where(Run.trigger != "scheduled")) or 0
    return int(count) % max(1, slots)


def _search_row(
    run: Run, source: str, label: str, access: AccessMethod, clock: Callable[[], datetime], **kw: str | None
) -> SourceSearch:
    return SourceSearch(
        run=run,
        source=source,
        source_label=label,
        access_method=access,
        status=SearchStatus.FAILED,
        started_at=clock(),
        **kw,
    )


def _fail(search: SourceSearch, exc: SourceError, t0: float) -> None:
    search.status = SearchStatus.ACCESS_BLOCKED if exc.blocked else SearchStatus.FAILED
    search.error = str(exc)[:2000]
    search.duration_ms = int((time.monotonic() - t0) * 1000)


def _tag_board(result: FetchResult, board: BoardConfig) -> None:
    for raw in result.vacancies:
        raw.board = board.key
        if board.agency:
            raw.is_agency_listing, raw.is_employer_requisition = True, False
            raw.agency = raw.agency or board.name


def _ingest_all(
    session: Session,
    run: Run,
    result: FetchResult,
    access: AccessMethod,
    taxonomy: Taxonomy,
    profile: CandidateProfile,
    clock: Callable[[], datetime],
) -> _Tally:
    tally = _Tally()
    for raw in result.vacancies:
        if not raw.title or not raw.source_job_id:
            continue
        try:
            with session.begin_nested():  # one malformed record must not abort the source or the run
                outcome = ingest(
                    session, raw, run=run, access_method=access, taxonomy=taxonomy, profile=profile, now=clock()
                )
                session.flush()
        except Exception:
            log.exception("ingest failed", extra={"source": raw.source, "source_job_id": raw.source_job_id})
            tally.failed += 1
            continue
        tally.vacancy_ids.add(outcome.vacancy.id)
        if outcome.is_new:
            tally.new_ids.add(outcome.vacancy.id)
    return tally


def _fill(
    search: SourceSearch,
    result: FetchResult,
    tally: _Tally,
    session: Session,
    t0: float,
    ids_by_search: dict[int, set[int]],
) -> None:
    session.flush()
    search.results_retrieved = len(result.vacancies)
    search.unique_vacancies = len(tally.vacancy_ids)
    search.new_vacancies = len(tally.new_ids)
    search.relevant_vacancies = sum(
        1 for i in tally.vacancy_ids if (v := session.get(Vacancy, i)) is not None and v.is_relevant
    )
    search.truncated = result.truncated
    search.limitation = result.limitation
    if tally.failed:
        search.error = f"{tally.failed} record(s) could not be ingested (see logs)"
    search.duration_ms = int((time.monotonic() - t0) * 1000)
    ids_by_search[search.id] = set(tally.vacancy_ids)


def _expire(
    session: Session, run: Run, full_boards: set[tuple[str, str]], windowed: set[str], now: datetime
) -> set[int]:
    """Mark sightings absent and vacancies NOT SEEN / EXPIRED. Never deletes anything."""
    affected: set[int] = set()
    for source, board in full_boards:
        gone = session.scalars(
            select(VacancySource).where(
                VacancySource.source == source,
                VacancySource.board == board,
                VacancySource.present.is_(True),
                VacancySource.last_seen_run_id != run.id,
            )
        ).all()
        for link in gone:
            link.present = False
            affected.add(link.vacancy_id)
            session.add(
                VacancyEvent(
                    vacancy_id=link.vacancy_id,
                    kind="absent_from_source",
                    detail={"source": source, "board": board, "run_id": run.id},
                )
            )
    for source in windowed:
        old = session.scalars(
            select(VacancySource).where(
                VacancySource.source == source,
                VacancySource.present.is_(True),
                VacancySource.last_seen_at < now - WINDOWED_RETIRE,
            )
        ).all()
        for link in old:
            link.present = False
            affected.add(link.vacancy_id)
            session.add(
                VacancyEvent(
                    vacancy_id=link.vacancy_id,
                    kind="retired_from_windowed_source",
                    detail={"source": source, "last_seen": link.last_seen_at.isoformat()},
                )
            )
    session.flush()
    candidates = session.scalars(select(Vacancy).where(Vacancy.lifecycle != Lifecycle.EXPIRED)).all()
    for v in candidates:
        if any(s.present for s in v.sources):
            continue
        new_state = Lifecycle.EXPIRED if now - v.last_seen_at > NOT_SEEN_GRACE else Lifecycle.NOT_SEEN
        if v.lifecycle != new_state:
            session.add(
                VacancyEvent(vacancy=v, kind="lifecycle_changed", detail={"from": v.lifecycle, "to": str(new_state)})
            )
            v.lifecycle = new_state
            affected.add(v.id)
    return affected
