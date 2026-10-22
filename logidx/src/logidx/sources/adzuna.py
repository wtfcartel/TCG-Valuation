"""Adzuna Australia — official keyed API (https://developer.adzuna.com). Aggregates many AU boards.

Limitations recorded on every search: descriptions are snippets, and salaries flagged
`salary_is_predicted` are Adzuna estimates, which LogiDx discards.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from logidx.enums import AccessMethod
from logidx.pipeline.normalize import html_to_text, parse_datetime
from logidx.settings import get_settings
from logidx.sources.base import FetchResult, QuerySource, RawVacancy
from logidx.sources.http import HttpClient

API = "https://api.adzuna.com/v1/api/jobs/au/search/{page}"
PAGE_SIZE = 50
MAX_PAGES = 3


class AdzunaSource(QuerySource):
    name = "adzuna"
    label = "Adzuna Australia"
    access_method = AccessMethod.API

    def __init__(self, app_id: str | None = None, app_key: str | None = None) -> None:
        settings = get_settings()
        self.app_id = app_id if app_id is not None else settings.adzuna_app_id.get_secret_value()
        self.app_key = app_key if app_key is not None else settings.adzuna_app_key.get_secret_value()

    @property
    def available(self) -> tuple[bool, str | None]:
        if not (self.app_id and self.app_key):
            return False, "ADZUNA_APP_ID / ADZUNA_APP_KEY not configured (free key: developer.adzuna.com)"
        return True, None

    def search(self, http: HttpClient, query: str, *, max_age_days: int) -> FetchResult:
        vacancies: list[RawVacancy] = []
        total = 0
        for page in range(1, MAX_PAGES + 1):
            params = {
                "app_id": self.app_id,
                "app_key": self.app_key,
                "results_per_page": PAGE_SIZE,
                "what_phrase": query,
                "max_days_old": max_age_days,
                "sort_by": "date",
                "content-type": "application/json",
            }
            data = http.get_json(API.format(page=page), params=params)
            total = int(data.get("count") or 0)
            results = data.get("results") or []
            vacancies.extend(self._parse(r) for r in results)
            if len(results) < PAGE_SIZE or len(vacancies) >= total:
                break
        truncated = total > len(vacancies)
        limitation = "descriptions are snippets; predicted salaries discarded"
        if truncated:
            limitation += f"; {total} matches, first {len(vacancies)} retrieved"
        return FetchResult(vacancies, truncated=truncated, limitation=limitation)

    def _parse(self, r: dict) -> RawVacancy:  # type: ignore[type-arg]
        location = r.get("location") or {}
        area = location.get("area") or []
        loc_text = location.get("display_name") or ", ".join(reversed(area[1:]))
        return RawVacancy(
            source=self.name,
            source_job_id=str(r.get("id")),
            title=html_to_text(r.get("title") or ""),
            url=r.get("redirect_url"),
            employer=(r.get("company") or {}).get("display_name"),
            location=loc_text,
            description=html_to_text(r.get("description") or ""),
            description_is_snippet=True,
            posted_at=parse_datetime(r.get("created")),
            salary_min=r.get("salary_min"),
            salary_max=r.get("salary_max"),
            salary_predicted=str(r.get("salary_is_predicted", "0")) == "1",
            employment_type=" ".join(filter(None, [r.get("contract_time"), r.get("contract_type")])) or None,
            raw={k: r.get(k) for k in ("id", "created", "category", "location", "adref")},
        )


def max_age_for(last_success: datetime | None, default_days: int = 14) -> int:
    """Look back far enough to cover the gap since the last successful search (minimum 2 days)."""
    if last_success is None:
        return default_days
    gap = datetime.now(UTC) - last_success
    return max(2, min(default_days, int(gap / timedelta(days=1)) + 2))
