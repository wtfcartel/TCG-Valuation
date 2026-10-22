"""Recruitment-agency and feed sources.

- Bullhorn: the public career-portal REST API (keyless; returns only jobs the agency has published).
  Many Australian executive-search firms run Bullhorn; "BH-" style references are Bullhorn job ids.
- RSS/Atom: job feeds published by boards and agencies (EthicalJobs, Pro Bono Australia, boutiques).
- Google Programmable Search: an *indexed fallback* only. Results never count as a native search of
  the site they point at.
"""

from __future__ import annotations

import hashlib
from datetime import UTC
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree as SafeET

from logidx.enums import AccessMethod
from logidx.pipeline.normalize import canonical_url, html_to_text, parse_datetime
from logidx.settings import get_settings
from logidx.sources.base import BoardConfig, BoardSource, FetchResult, QuerySource, RawVacancy
from logidx.sources.http import HttpClient, SourceError


class BullhornSource(BoardSource):
    name = "bullhorn"
    label = "Bullhorn agency boards"
    PAGE = 500
    MAX_PAGES = 10
    FIELDS = (
        "id,title,publicDescription,address(city,state,countryName),dateAdded,dateLastPublished,"
        "employmentType,salary,salaryUnit"
    )

    def fetch(self, http: HttpClient, board: BoardConfig, title_filter=None) -> FetchResult:  # type: ignore[no-untyped-def]
        cls, token = board.board["cluster"], board.board["corp_token"]
        base = f"https://public-rest{cls}.bullhornstaffing.com/rest-services/{token}"
        url_template = board.board.get("job_url_template")
        orders: list[dict] = []  # type: ignore[type-arg]
        start = 0
        truncated = False
        for page_no in range(self.MAX_PAGES):
            data = http.get_json(
                f"{base}/search/JobOrder",
                params={
                    "query": "(isOpen:1)",
                    "fields": self.FIELDS,
                    "count": self.PAGE,
                    "start": start,
                    "sort": "-dateAdded",
                },
            )
            batch = data.get("data") or []
            orders.extend(batch)
            start += len(batch)
            if not batch or start >= int(data.get("total") or 0):
                break
            if page_no == self.MAX_PAGES - 1:
                truncated = True
        out = []
        for o in orders:
            addr = o.get("address") or {}
            job_id = str(o.get("id"))
            url = url_template.format(id=job_id) if url_template else f"{base}/entity/JobOrder/{job_id}"
            salary = o.get("salary")
            unit = (o.get("salaryUnit") or "").lower()
            out.append(
                RawVacancy(
                    source=self.name,
                    board=board.key,
                    source_job_id=f"{token}:{job_id}",
                    title=o.get("title") or "",
                    url=url,
                    apply_url=url if url_template else None,
                    agency=board.name,
                    employer=None,
                    location=", ".join(filter(None, [addr.get("city"), addr.get("state"), addr.get("countryName")])),
                    description=html_to_text(o.get("publicDescription")),
                    posted_at=parse_datetime(o.get("dateLastPublished") or o.get("dateAdded")),
                    employment_type=o.get("employmentType"),
                    reference=f"BH-{job_id}",
                    is_agency_listing=True,
                    salary_text=f"${salary:,.0f} {unit}".strip()
                    if isinstance(salary, int | float) and salary
                    else None,
                )
            )
        return FetchResult(out, truncated=truncated)


class RssSource(BoardSource):
    name = "rss"
    label = "RSS / Atom job feeds"

    def fetch(self, http: HttpClient, board: BoardConfig, title_filter=None) -> FetchResult:  # type: ignore[no-untyped-def]
        url = board.board["url"]
        if not http.robots_allows(url):
            raise SourceError(f"robots.txt disallows {url}", blocked=True)
        resp = http.request("GET", url)
        if resp.status_code >= 400:
            raise SourceError(f"HTTP {resp.status_code} from feed", status_code=resp.status_code)
        try:
            root = SafeET.fromstring(resp.content)
        except Exception as exc:  # defusedxml raises several types for hostile/malformed XML
            raise SourceError(f"feed is not valid XML: {exc}") from exc
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        out = []
        for it in items:

            def text(tag: str, it=it) -> str:  # type: ignore[no-untyped-def]
                el = it.find(tag)
                if el is None:
                    el = it.find(f"{{http://www.w3.org/2005/Atom}}{tag}")
                return (el.text or "").strip() if el is not None and el.text else ""

            link = text("link")
            if not link:
                atom_link = it.find("{http://www.w3.org/2005/Atom}link")
                link = atom_link.get("href", "") if atom_link is not None else ""
            guid = text("guid") or text("id") or link
            posted = None
            raw_date = text("pubDate") or text("updated") or text("published")
            if raw_date:
                try:
                    posted = parsedate_to_datetime(raw_date).astimezone(UTC)
                except (TypeError, ValueError):
                    posted = parse_datetime(raw_date)
            out.append(
                RawVacancy(
                    source=self.name,
                    board=board.key,
                    source_job_id=f"{board.key}:{hashlib.sha1(guid.encode()).hexdigest()[:16]}",
                    title=html_to_text(text("title")),
                    url=canonical_url(link),
                    employer=None if board.agency else None,
                    agency=board.name if board.agency else None,
                    description=html_to_text(text("description") or text("summary") or text("content")),
                    description_is_snippet=True,
                    posted_at=posted,
                    is_agency_listing=board.agency,
                )
            )
        return FetchResult(out, limitation="feed items carry summaries only")


class GoogleIndexedSource(QuerySource):
    """Google Programmable Search JSON API restricted to job-site URLs. Indexed fallback only."""

    name = "google_indexed"
    label = "Google-indexed fallback (Programmable Search)"
    access_method = AccessMethod.INDEXED_FALLBACK
    SITES = ["linkedin.com/jobs/view", "seek.com.au/job", "au.indeed.com/viewjob"]

    def __init__(self) -> None:
        s = get_settings()
        self.key, self.cx = s.google_cse_key.get_secret_value(), s.google_cse_cx

    @property
    def available(self) -> tuple[bool, str | None]:
        if not (self.key and self.cx):
            return False, "GOOGLE_CSE_KEY / GOOGLE_CSE_CX not configured"
        return True, None

    def search(self, http: HttpClient, query: str, *, max_age_days: int) -> FetchResult:
        sites = " OR ".join(f"site:{s}" for s in self.SITES)
        data = http.get_json(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": self.key,
                "cx": self.cx,
                "q": f'"{query}" Australia ({sites})',
                "num": 10,
                "dateRestrict": f"d{max_age_days}",
                "gl": "au",
            },
        )
        out = []
        for item in data.get("items") or []:
            link = item.get("link") or ""
            out.append(
                RawVacancy(
                    source=self.name,
                    source_job_id=hashlib.sha1(link.encode()).hexdigest()[:20],
                    title=item.get("title") or "",
                    url=link,
                    description=item.get("snippet") or "",
                    description_is_snippet=True,
                    raw={"displayLink": item.get("displayLink")},
                )
            )
        return FetchResult(
            out, truncated=True, limitation="indexed results only; not a native search of LinkedIn/SEEK/Indeed"
        )
