"""Discovery runs: failure isolation, audit records, lifecycle without deletion, idempotency and locking."""

from datetime import UTC, datetime, timedelta

import httpx
import respx
from sqlalchemy import func, select

from logidx import locks
from logidx.enums import AccessMethod, Lifecycle, RunStatus, SearchStatus, Verification
from logidx.models import CategoryAudit, SourceSearch, Vacancy, VacancyEvent
from logidx.pipeline.runner import LOCK_NAME, RunPlan, run_discovery, start_run
from logidx.sources.agencies import BullhornSource
from logidx.sources.ats import GreenhouseSource
from logidx.sources.base import BoardConfig, BoardSource, FetchResult, QuerySource, RawVacancy
from logidx.sources.http import SourceError
from logidx.sources.registry import RESTRICTED, Watchlist
from tests import payloads


class FakeQuery(QuerySource):
    name, label, access_method = "fakeapi", "Fake API", AccessMethod.API

    def __init__(self, results=None, fail_on=(), blocked=False):
        self.results, self.fail_on, self.blocked, self.queries = results or {}, set(fail_on), blocked, []

    def search(self, http, query, *, max_age_days):
        self.queries.append(query)
        if query in self.fail_on or "*" in self.fail_on:
            raise SourceError("HTTP 500 from fake", blocked=self.blocked)
        return FetchResult(list(self.results.get(query, [])), truncated=False)


class FakeBoard(BoardSource):
    name, label = "fakeats", "Fake ATS"

    def __init__(self, listings):
        self.listings = listings  # board key -> list[RawVacancy] | Exception

    def fetch(self, http, board, title_filter=None):
        value = self.listings[board.key]
        if isinstance(value, Exception):
            raise value
        return FetchResult(list(value))


def raw(job_id, title, **kw):
    kw.setdefault("employer", "Southern Freight (Fixture)")
    kw.setdefault("location", "Melbourne VIC")
    kw.setdefault("description", "Reporting to the CEO with full P&L accountability for national operations.")
    return RawVacancy(
        source=kw.pop("source", "fakeats"),
        source_job_id=job_id,
        title=title,
        url=f"https://jobs.example/{job_id}",
        is_employer_requisition=kw.pop("req", True),
        **kw,
    )


def plan(query=None, listings=None, boards=None, restricted=True):
    boards = boards or [BoardConfig(key=k, name=k, ats="fakeats", board={"id": k}) for k in (listings or {})]
    return RunPlan(
        query_sources=[query] if query else [],
        board_sources={"fakeats": FakeBoard(listings or {})},
        watchlist=Watchlist(boards),
        restricted=RESTRICTED if restricted else [],
    )


def go(session, p, key=None, now=None):
    run = start_run(session, trigger="test", idempotency_key=key)
    return run_discovery(session, run, plan=p, now=now)


def test_failure_isolation_and_audit(session):
    good = [raw("1", "General Manager Supply Chain")]
    p = plan(
        listings={"good": good, "bad": SourceError("HTTP 500 from bad")}, query=FakeQuery(fail_on={"head of strategy"})
    )
    run = go(session, p)
    statuses = {(s.board, s.status) for s in run.searches if s.board}
    assert ("good", SearchStatus.NATIVE_SEARCHED) in statuses and ("bad", SearchStatus.FAILED) in statuses
    assert run.status == RunStatus.PARTIAL
    assert session.scalar(select(func.count(Vacancy.id))) == 1  # the good board still ingested
    failed_q = session.scalar(select(SourceSearch).where(SourceSearch.query == "head of strategy"))
    assert failed_q.status == SearchStatus.FAILED and failed_q.results_retrieved == 0 and failed_q.error
    strategy = session.scalar(
        select(CategoryAudit).where(CategoryAudit.run_id == run.id, CategoryAudit.category == "strategy")
    )
    assert not strategy.complete and "INCOMPLETE" in strategy.note


def test_restricted_sources_always_recorded_not_searched(session):
    run = go(session, plan(listings={"b": []}))
    rows = {s.source: s for s in run.searches if s.source in {r.name for r in RESTRICTED}}
    assert set(rows) == {"seek", "linkedin", "indeed", "google_jobs", "jora", "careerone", "workforce_australia"}
    assert all(r.status == SearchStatus.NOT_SEARCHED and r.limitation for r in rows.values())


def test_unconfigured_board_is_not_searched_with_reason(session):
    boards = [
        BoardConfig(key="six", name="Six Degrees", ats="fakeats", board={"cluster": "", "corp_token": ""}),
        BoardConfig(key="toll", name="Toll", ats="unknown", board={}),
    ]
    run = go(session, plan(boards=boards, listings={}))
    reasons = {s.board: s.limitation for s in run.searches if s.board}
    assert reasons == {"six": "board identifier not configured", "toll": "ATS not yet identified"}
    assert run.status == RunStatus.FAILED and "no source could be searched" in run.error
    assert session.scalar(select(func.count(CategoryAudit.id)).where(CategoryAudit.complete.is_(True))) == 0


def test_zero_results_is_a_successful_search_not_a_failure(session):
    run = go(session, plan(query=FakeQuery(), restricted=False))
    api = [s for s in run.searches if s.source == "fakeapi"]
    assert api and all(s.status == SearchStatus.API_SEARCHED and s.results_retrieved == 0 for s in api)


def test_repeated_access_blocks_stop_the_source(session):
    q = FakeQuery(fail_on={"*"}, blocked=True)
    run = go(session, plan(query=q, restricted=False))
    assert len(q.queries) == 3  # stopped after three refusals
    skipped = [s for s in run.searches if s.status == SearchStatus.NOT_SEARCHED and s.source == "fakeapi"]
    assert skipped and "repeated access refusals" in skipped[0].limitation


def test_lifecycle_never_deletes_and_expires_after_grace(session):
    t0 = datetime(2026, 10, 20, 9, tzinfo=UTC)
    listings = {"b": [raw("1", "Head of Logistics"), raw("2", "Head of Operations")]}
    p = plan(listings=listings, restricted=False)
    go(session, p, now=lambda: t0)
    v2 = session.scalar(select(Vacancy).where(Vacancy.title == "Head of Operations"))
    assert v2.verification_status == Verification.VERIFIED_OPEN

    listings["b"] = [raw("1", "Head of Logistics")]  # job 2 disappears from a complete listing
    go(session, p, now=lambda: t0 + timedelta(days=1))
    session.refresh(v2)
    assert v2.lifecycle == Lifecycle.NOT_SEEN and not v2.sources[0].present
    assert v2.verification_status == Verification.UNVERIFIED_STALE

    go(session, p, now=lambda: t0 + timedelta(days=5))
    session.refresh(v2)
    assert v2.lifecycle == Lifecycle.EXPIRED
    assert session.get(Vacancy, v2.id) is not None  # record kept
    kinds = [e.kind for e in v2.events]
    assert "absent_from_source" in kinds and "lifecycle_changed" in kinds

    listings["b"].append(raw("2", "Head of Operations"))  # it comes back
    go(session, p, now=lambda: t0 + timedelta(days=6))
    session.refresh(v2)
    assert v2.lifecycle == Lifecycle.ACTIVE and "reappeared" in [e.kind for e in v2.events]


def test_failed_source_does_not_expire_its_jobs(session):
    t0 = datetime(2026, 10, 20, 9, tzinfo=UTC)
    listings = {"b": [raw("1", "Head of Logistics")]}
    p = plan(listings=listings, restricted=False)
    go(session, p, now=lambda: t0)
    listings["b"] = SourceError("HTTP 503")
    go(session, p, now=lambda: t0 + timedelta(days=1))
    v = session.scalar(select(Vacancy))
    assert v.lifecycle == Lifecycle.ACTIVE and v.sources[0].present


def test_windowed_query_source_absence_does_not_expire(session):
    t0 = datetime(2026, 10, 20, 9, tzinfo=UTC)
    item = raw("a1", "General Manager Supply Chain", source="fakeapi", req=False)
    q = FakeQuery(results={"general manager supply chain": [item]})
    p = plan(query=q, restricted=False)
    go(session, p, now=lambda: t0)
    q.results = {}
    go(session, p, now=lambda: t0 + timedelta(days=2))
    v = session.scalar(select(Vacancy))
    assert v.lifecycle == Lifecycle.ACTIVE
    go(session, p, now=lambda: t0 + timedelta(days=30))
    session.refresh(v)
    assert v.lifecycle == Lifecycle.EXPIRED  # retired only after the windowed retirement period


def test_cross_posting_merges(session):
    listings = {"emp": [raw("1", "General Manager Supply Chain", reference="R55")]}
    agency_copy = raw("9", "GM Supply Chain", source="fakeapi", req=False, reference="R55")
    q = FakeQuery(results={"general manager supply chain": [agency_copy]})
    go(session, plan(listings=listings, query=q, restricted=False))
    assert session.scalar(select(func.count(Vacancy.id))) == 1
    v = session.scalar(select(Vacancy))
    assert len(v.sources) == 2 and any(e.kind == "cross_post_merged" for e in v.events)


def test_duplicate_idempotency_key_runs_once(session):
    assert start_run(session, trigger="scheduled", idempotency_key="scheduled:2026-10-21:06:00") is not None
    assert start_run(session, trigger="scheduled", idempotency_key="scheduled:2026-10-21:06:00") is None


def test_lock_prevents_overlapping_runs(session):
    assert locks.acquire(session, LOCK_NAME, "someone-else")
    run = go(session, plan(listings={"b": []}))
    assert run.status == RunStatus.SKIPPED and "in progress" in run.error
    locks.release(session, LOCK_NAME, "someone-else")


def test_expired_lock_is_taken_over(session):
    assert locks.acquire(session, LOCK_NAME, "crashed", ttl=timedelta(seconds=-1))
    assert locks.acquire(session, LOCK_NAME, "new")


@respx.mock
def test_end_to_end_with_vendor_adapters(session):
    """Real adapters + ingestion + verification + audit on synthetic vendor payloads."""
    respx.get("https://boards-api.greenhouse.io/v1/boards/fixture/jobs").mock(
        return_value=httpx.Response(200, json=payloads.GREENHOUSE_JOBS)
    )
    respx.get("https://public-rest33.bullhornstaffing.com/rest-services/tok/search/JobOrder").mock(
        return_value=httpx.Response(200, json=payloads.bullhorn_page())
    )
    boards = [
        BoardConfig(key="gh", name="Network Holdings (Fixture)", ats="greenhouse", board={"token": "fixture"}),
        BoardConfig(
            key="six_degrees",
            name="Six Degrees Executive",
            ats="bullhorn",
            agency=True,
            target_group="executive_search",
            board={"cluster": "33", "corp_token": "tok"},
        ),
    ]
    p = RunPlan([], {"greenhouse": GreenhouseSource(), "bullhorn": BullhornSource()}, Watchlist(boards), RESTRICTED)
    run = go(session, p)
    vs = {v.title: v for v in session.scalars(select(Vacancy)).all()}
    corp = vs["Director, Corporate Development & M&A"]
    assert corp.verification_status == Verification.VERIFIED_OPEN and "mna" in corp.categories
    assert corp.geography == "NATIONAL — MELBOURNE OPTION STATED"
    gm = vs["General Manager Supply Chain"]
    assert gm.is_confidential and gm.recruiting_agency == "Six Degrees Executive"
    assert gm.verification_status == Verification.LIKELY_OPEN  # agency listing, not employer requisition
    assert gm.reference == "BH-31092"
    assert all(a.complete for a in run.category_audits)
    discovered = session.scalars(select(VacancyEvent).where(VacancyEvent.kind == "discovered")).all()
    assert len(discovered) == 2


def test_daily_category_coverage_requires_every_rotating_query(session):
    from logidx import coverage

    q = FakeQuery()
    p = plan(query=q, restricted=False)
    for slot in ("06:00", "14:00"):
        r = start_run(session, trigger="scheduled", idempotency_key=f"k{slot}", slot=slot)
        run_discovery(session, r, plan=p)
    day = coverage.today_local()
    rows = {c.key: c for c in coverage.category_matrix(session, day)}
    assert rows["supply_chain_logistics"].status == "INCOMPLETE" and rows["supply_chain_logistics"].missing_queries
    r = start_run(session, trigger="scheduled", idempotency_key="k20", slot="20:00")
    run_discovery(session, r, plan=p)
    rows = {c.key: c for c in coverage.category_matrix(session, day)}
    assert all(c.status == "COMPLETE" for c in rows.values()), {k: c.note for k, c in rows.items()}
    src = {s.group: s for s in coverage.source_matrix(session, day)}
    assert src["seek"].status == "NOT SEARCHED"  # target rows exist even with no searches


def test_last_success_and_work_mode_hint(session):
    from logidx import coverage

    item = raw("1", "Head of Logistics", work_mode_hint="Hybrid", description="Lead logistics.")
    go(session, plan(listings={"b": [item]}, restricted=False))
    v = session.scalar(select(Vacancy))
    assert v.work_mode == "HYBRID"
    rows = {r.group: r for r in coverage.source_matrix(session, coverage.today_local(), Watchlist([]))}
    assert rows["employer_careers"].last_success is not None
