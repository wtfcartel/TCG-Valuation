"""Daily coverage matrices: source-by-source and discipline-by-discipline, for one Melbourne calendar day."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from logidx.enums import SearchStatus
from logidx.models import CategoryAudit, Run, SourceSearch
from logidx.settings import get_settings
from logidx.sources.registry import TARGET_GROUPS, Watchlist, load_watchlist
from logidx.taxonomy import Taxonomy, default_taxonomy

_RANK = [
    SearchStatus.NATIVE_SEARCHED,
    SearchStatus.API_SEARCHED,
    SearchStatus.INDEXED_FALLBACK_ONLY,
    SearchStatus.FAILED,
    SearchStatus.ACCESS_BLOCKED,
    SearchStatus.NOT_SEARCHED,
]


def day_bounds(day: date) -> tuple[datetime, datetime]:
    tz = get_settings().tz
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def today_local() -> date:
    return datetime.now(get_settings().tz).date()


@dataclass
class SourceRow:
    group: str
    label: str
    status: str = SearchStatus.NOT_SEARCHED
    access_methods: set[str] = field(default_factory=set)
    searches: int = 0
    succeeded: int = 0
    failed: int = 0
    not_searched: int = 0
    results: int = 0
    unique: int = 0
    relevant: int = 0
    verified_open: int = 0
    errors: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    last_success: datetime | None = None
    members: dict[str, str] = field(default_factory=dict)  # board/source label -> best status today


def _group_for(search: SourceSearch, watch: Watchlist) -> str:
    if search.board:
        board = next((b for b in watch.boards if b.key == search.board), None)
        return board.target_group if board else "employer_careers"
    return search.source


def source_matrix(session: Session, day: date, watch: Watchlist | None = None) -> list[SourceRow]:
    watch = watch or load_watchlist()
    start, end = day_bounds(day)
    rows = {key: SourceRow(group=key, label=label) for key, label in TARGET_GROUPS}
    searches = session.scalars(
        select(SourceSearch).where(SourceSearch.started_at >= start, SourceSearch.started_at < end)
    ).all()
    best: dict[str, int] = {}
    for s in searches:
        group = _group_for(s, watch)
        row = rows.setdefault(group, SourceRow(group=group, label=group))
        row.searches += 1
        row.access_methods.add(s.access_method)
        status = SearchStatus(s.status)
        if status.succeeded:
            row.succeeded += 1
        elif status == SearchStatus.NOT_SEARCHED:
            row.not_searched += 1
        else:
            row.failed += 1
        row.results += s.results_retrieved
        row.unique += s.unique_vacancies
        row.relevant += s.relevant_vacancies
        row.verified_open += s.verified_open
        if s.error and s.error not in row.errors:
            row.errors.append(s.error)
        if s.limitation and s.limitation not in row.limitations:
            row.limitations.append(s.limitation)
        rank = _RANK.index(status)
        if rank < best.get(group, len(_RANK)):
            best[group] = rank
            row.status = status
        member = s.source_label
        if member not in row.members or _RANK.index(status) < _RANK.index(SearchStatus(row.members[member])):
            row.members[member] = status
    ok_statuses = [SearchStatus.NATIVE_SEARCHED, SearchStatus.API_SEARCHED, SearchStatus.INDEXED_FALLBACK_ONLY]
    history = session.execute(
        select(SourceSearch.source, SourceSearch.board, func.max(SourceSearch.started_at))
        .where(SourceSearch.status.in_(ok_statuses), SourceSearch.started_at < end)
        .group_by(SourceSearch.source, SourceSearch.board)
    ).all()
    for source, board_key, last in history:
        group = _group_for(SourceSearch(source=source, board=board_key), watch)
        row = rows.get(group)
        if row is not None and (row.last_success is None or last > row.last_success):
            row.last_success = last
    for row in rows.values():
        if row.searches and row.failed and row.succeeded:
            row.limitations.insert(0, f"partial: {row.failed} of {row.searches} searches failed")
    return list(rows.values())


@dataclass
class CategoryRow:
    key: str
    label: str
    status: str  # COMPLETE | INCOMPLETE | NOT SEARCHED
    runs: int
    planned_queries: list[str]
    executed_queries: list[str]
    missing_queries: list[str]
    sources_succeeded: list[str]
    sources_failed: list[str]
    sources_not_searched: list[str]
    results: int
    relevant: int
    note: str


def category_matrix(session: Session, day: date, taxonomy: Taxonomy | None = None) -> list[CategoryRow]:
    taxonomy = taxonomy or default_taxonomy()
    start, end = day_bounds(day)
    run_ids = [r for r in session.scalars(select(Run.id).where(Run.started_at >= start, Run.started_at < end))]
    audits = session.scalars(select(CategoryAudit).where(CategoryAudit.run_id.in_(run_ids))).all() if run_ids else []
    searches = (
        session.scalars(
            select(SourceSearch).where(SourceSearch.run_id.in_(run_ids), SourceSearch.category.is_not(None))
        ).all()
        if run_ids
        else []
    )
    query_sources_used = {s.source for s in searches if s.status != SearchStatus.NOT_SEARCHED}
    out = []
    planned_all = taxonomy.all_queries()
    for key in taxonomy.category_keys:
        cat_audits = [a for a in audits if a.category == key]
        ok = sorted({x for a in cat_audits for x in a.sources_succeeded})
        failed = sorted({x for a in cat_audits for x in a.sources_failed} - set(ok))
        not_searched = sorted({x for a in cat_audits for x in a.sources_not_searched})
        planned = planned_all[key]
        # A query counts as executed only if every query source that ran today ran it successfully.
        per_source = [
            {
                s.query
                for s in searches
                if s.category == key and s.source == src and SearchStatus(s.status).succeeded and s.query
            }
            for src in sorted(query_sources_used)
        ]
        executed: set[str] = set.intersection(*per_source) if per_source else set()
        missing = [q for q in planned if q not in executed] if query_sources_used else []
        if not ok:
            status, note = "NOT SEARCHED", "no source searched this discipline successfully today"
        elif missing or failed:
            status = "INCOMPLETE"
            note = "; ".join(
                filter(
                    None,
                    [
                        f"{len(missing)} planned queries not run successfully" if missing else "",
                        f"failed: {', '.join(failed)}" if failed else "",
                    ],
                )
            )
        else:
            status, note = "COMPLETE", "all planned searches succeeded"
        if not_searched:
            note += f" · not searched (access/config): {len(not_searched)} sources"
        out.append(
            CategoryRow(
                key=key,
                label=taxonomy.category_label(key),
                status=status,
                runs=len(cat_audits),
                planned_queries=planned,
                executed_queries=sorted(executed),
                missing_queries=missing,
                sources_succeeded=ok,
                sources_failed=failed,
                sources_not_searched=not_searched,
                results=max((a.results_retrieved for a in cat_audits), default=0),
                relevant=max((a.relevant_vacancies for a in cat_audits), default=0),
                note=note,
            )
        )
    return out
