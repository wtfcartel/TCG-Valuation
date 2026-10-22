"""Source-adapter interface.

Three kinds of source:
- QuerySource: searched per query (job boards / aggregators with a search API, e.g. Adzuna).
- BoardSource: lists every open requisition on one board (an employer ATS or an agency ATS); the
  taxonomy is then applied locally, so one successful fetch covers all nine disciplines.
- RestrictedSource: a target source with no authorised automated route. It is never contacted; the
  runner records NOT SEARCHED with the documented limitation so the gap is always visible.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from logidx.enums import AccessMethod
from logidx.sources.http import HttpClient


@dataclass
class RawVacancy:
    source: str
    source_job_id: str
    title: str
    url: str | None
    employer: str | None = None
    agency: str | None = None
    location: str | None = None
    description: str = ""
    description_is_snippet: bool = False
    apply_url: str | None = None
    posted_at: datetime | None = None
    closing_date: date | None = None
    salary_text: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_predicted: bool = False
    employment_type: str | None = None
    work_mode_hint: str | None = None
    reference: str | None = None
    board: str | None = None
    is_employer_requisition: bool = False  # listed on the hiring employer's own ATS
    is_agency_listing: bool = False  # listed by a recruitment agency
    explicit_open: bool | None = None  # source states applications are open (e.g. Workday canApply)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    vacancies: list[RawVacancy]
    truncated: bool = False  # page cap hit: absence from this result is not evidence of closure
    limitation: str | None = None


class BoardConfig(BaseModel):
    """One employer/agency board from config/watchlist.yaml."""

    key: str
    name: str
    ats: str
    enabled: bool = True
    board: dict[str, Any] = {}
    agency: bool = False
    target_group: str = "employer_careers"  # coverage-matrix row this board reports under
    industry: str | None = None
    notes: str | None = None

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.board) and all(v not in (None, "") for v in self.board.values())


class Source(ABC):
    name: str
    label: str
    access_method: AccessMethod

    @property
    def available(self) -> tuple[bool, str | None]:
        """(usable now, reason if not) — e.g. missing API key."""
        return True, None


class QuerySource(Source):
    @abstractmethod
    def search(self, http: HttpClient, query: str, *, max_age_days: int) -> FetchResult: ...


class BoardSource(Source):
    access_method = AccessMethod.NATIVE

    @abstractmethod
    def fetch(
        self, http: HttpClient, board: BoardConfig, title_filter: Callable[[str], bool] | None = None
    ) -> FetchResult:
        """List the board. `title_filter` selects which rows are worth a detail request."""


class RestrictedSource(Source):
    access_method = AccessMethod.NONE

    def __init__(self, name: str, label: str, limitation: str, compliant_routes: list[str]) -> None:
        self.name, self.label = name, label
        self.limitation = limitation
        self.compliant_routes = compliant_routes

    @property
    def available(self) -> tuple[bool, str | None]:
        return False, self.limitation
