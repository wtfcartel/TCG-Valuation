"""Employer applicant-tracking-system boards. Each lists the employer's own open requisitions through
the public endpoint the vendor's career site itself uses, so a listing here is direct evidence of a
live requisition (it is still verified before documents are generated).

Endpoint shapes follow the vendors' public career-site APIs; freehire (MIT) documents the same
endpoints and was used as a reference for field names. No code was copied.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup

from logidx.pipeline.normalize import html_to_text, parse_datetime
from logidx.sources.base import BoardConfig, BoardSource, FetchResult, RawVacancy
from logidx.sources.http import HttpClient, SourceError

TitleFilter = Callable[[str], bool]

# Executive search terms used for large Workday tenants that cannot be listed in full.
WORKDAY_DEFAULT_TERMS = [
    "general manager",
    "head of",
    "director",
    "chief",
    "executive",
    "lead",
    "national",
    "strategy",
    "transformation",
    "commercial",
    "operations manager",
]


def _relative_posted(text: str | None, now: datetime) -> datetime | None:
    if not text:
        return None
    low = text.lower()
    if "today" in low:
        return now
    if "yesterday" in low:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*days?", low)
    return now - timedelta(days=int(m.group(1))) if m else None


class WorkdaySource(BoardSource):
    name = "workday"
    label = "Workday employer boards"
    PAGE = 20
    MAX_PAGES = 10

    def fetch(self, http: HttpClient, board: BoardConfig, title_filter: TitleFilter | None = None) -> FetchResult:
        host, tenant, site = board.board["host"], board.board["tenant"], board.board["site"]
        base = f"https://{host}/wday/cxs/{tenant}/{site}"
        full = bool(board.board.get("full_listing"))
        terms = [""] if full else board.board.get("search_terms") or WORKDAY_DEFAULT_TERMS
        now = datetime.now(UTC)
        postings: dict[str, dict] = {}  # type: ignore[type-arg]
        truncated = not full
        for term in terms:
            offset = 0
            for _ in range(self.MAX_PAGES):
                page = http.post_json(
                    f"{base}/jobs", {"appliedFacets": {}, "limit": self.PAGE, "offset": offset, "searchText": term}
                )
                items = page.get("jobPostings") or []
                for item in items:
                    if item.get("externalPath"):
                        postings.setdefault(item["externalPath"], item)
                offset += self.PAGE
                total = int(page.get("total") or 0)
                if not items or offset >= total:
                    break
            else:
                truncated = True
        out: list[RawVacancy] = []
        for path, item in postings.items():
            title = item.get("title") or ""
            vac = RawVacancy(
                source=self.name,
                board=board.key,
                source_job_id=f"{tenant}:{path}",
                title=title,
                url=f"https://{host}/{site}{path}",
                employer=board.name,
                location=item.get("locationsText"),
                posted_at=_relative_posted(item.get("postedOn"), now),
                is_employer_requisition=True,
                description_is_snippet=True,
                reference=(item.get("bulletFields") or [None])[0],
                raw={"postedOn": item.get("postedOn")},
            )
            if title_filter is None or title_filter(title):
                self._hydrate(http, base, path, vac)
            out.append(vac)
        limitation = None if full else f"searched by {len(terms)} executive keywords, not a full listing"
        return FetchResult(out, truncated=truncated, limitation=limitation)

    def _hydrate(self, http: HttpClient, base: str, path: str, vac: RawVacancy) -> None:
        try:
            detail = http.get_json(f"{base}{path}")
        except SourceError:
            return  # keep the listing row; description stays a snippet
        info = detail.get("jobPostingInfo") or {}
        vac.description = html_to_text(info.get("jobDescription"))
        vac.description_is_snippet = not vac.description
        vac.location = info.get("location") or vac.location
        vac.url = info.get("externalUrl") or vac.url
        vac.apply_url = vac.url
        vac.employment_type = info.get("timeType")
        vac.work_mode_hint = info.get("remoteType")
        vac.reference = info.get("jobReqId") or vac.reference
        if info.get("startDate"):
            vac.posted_at = parse_datetime(info["startDate"]) or vac.posted_at
        if "canApply" in info:
            vac.explicit_open = bool(info["canApply"])


class SmartRecruitersSource(BoardSource):
    name = "smartrecruiters"
    label = "SmartRecruiters employer boards"
    API = "https://api.smartrecruiters.com/v1/companies"

    def fetch(self, http: HttpClient, board: BoardConfig, title_filter: TitleFilter | None = None) -> FetchResult:
        company = board.board["company"]
        offset, items = 0, []
        while True:
            params = {"limit": 100, "offset": offset}
            if board.board.get("country"):
                params["country"] = board.board["country"]
            page = http.get_json(f"{self.API}/{company}/postings", params=params)
            content = page.get("content") or []
            items.extend(content)
            offset += 100
            if not content or offset >= int(page.get("totalFound") or 0) or offset >= 2000:
                break
        out = []
        for p in items:
            loc = p.get("location") or {}
            vac = RawVacancy(
                source=self.name,
                board=board.key,
                source_job_id=f"{company}:{p.get('id')}",
                title=p.get("name") or "",
                url=f"https://jobs.smartrecruiters.com/{company}/{p.get('id')}",
                employer=(p.get("company") or {}).get("name") or board.name,
                location=", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country", "").upper()])),
                posted_at=parse_datetime(p.get("releasedDate")),
                reference=p.get("refNumber"),
                work_mode_hint="remote" if loc.get("remote") else ("hybrid" if loc.get("hybrid") else None),
                employment_type=(p.get("typeOfEmployment") or {}).get("label"),
                is_employer_requisition=True,
                description_is_snippet=True,
            )
            if title_filter is None or title_filter(vac.title):
                try:
                    d = http.get_json(f"{self.API}/{company}/postings/{p.get('id')}")
                    sections = (d.get("jobAd") or {}).get("sections") or {}
                    parts = [
                        html_to_text((sections.get(k) or {}).get("text"))
                        for k in ("jobDescription", "qualifications", "additionalInformation")
                    ]
                    vac.description = "\n\n".join(x for x in parts if x)
                    vac.description_is_snippet = not vac.description
                    vac.url = d.get("postingUrl") or vac.url
                    vac.apply_url = d.get("applyUrl") or vac.url
                except SourceError:
                    pass
            out.append(vac)
        return FetchResult(out)


class GreenhouseSource(BoardSource):
    name = "greenhouse"
    label = "Greenhouse employer boards"

    def fetch(self, http: HttpClient, board: BoardConfig, title_filter: TitleFilter | None = None) -> FetchResult:
        token = board.board["token"]
        data = http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs", params={"content": "true"})
        out = []
        for j in data.get("jobs") or []:
            out.append(
                RawVacancy(
                    source=self.name,
                    board=board.key,
                    source_job_id=f"{token}:{j.get('id')}",
                    title=j.get("title") or "",
                    url=j.get("absolute_url"),
                    apply_url=j.get("absolute_url"),
                    employer=j.get("company_name") or board.name,
                    location=(j.get("location") or {}).get("name"),
                    description=html_to_text(j.get("content")),
                    reference=j.get("requisition_id"),
                    posted_at=parse_datetime(j.get("first_published") or j.get("updated_at")),
                    is_employer_requisition=True,
                )
            )
        return FetchResult(out)


class LeverSource(BoardSource):
    name = "lever"
    label = "Lever employer boards"

    def fetch(self, http: HttpClient, board: BoardConfig, title_filter: TitleFilter | None = None) -> FetchResult:
        site = board.board["site"]
        host = "api.eu.lever.co" if board.board.get("region") == "eu" else "api.lever.co"
        data = http.get_json(f"https://{host}/v0/postings/{site}", params={"mode": "json"})
        out = []
        for p in data or []:
            cats = p.get("categories") or {}
            lists = "\n\n".join(f"{x.get('text', '')}\n{html_to_text(x.get('content'))}" for x in p.get("lists") or [])
            desc = "\n\n".join(
                filter(
                    None,
                    [p.get("descriptionPlain") or html_to_text(p.get("description")), lists, p.get("additionalPlain")],
                )
            )
            salary = p.get("salaryRange") or {}
            out.append(
                RawVacancy(
                    source=self.name,
                    board=board.key,
                    source_job_id=f"{site}:{p.get('id')}",
                    title=p.get("text") or "",
                    url=p.get("hostedUrl"),
                    apply_url=p.get("applyUrl") or p.get("hostedUrl"),
                    employer=board.name,
                    location=cats.get("location"),
                    description=desc,
                    posted_at=parse_datetime(p.get("createdAt")),
                    employment_type=cats.get("commitment"),
                    work_mode_hint=p.get("workplaceType"),
                    salary_min=salary.get("min"),
                    salary_max=salary.get("max"),
                    is_employer_requisition=True,
                )
            )
        return FetchResult(out)


class PageUpSource(BoardSource):
    """PageUp People (common with Australian universities, councils, health and large employers).
    The listing endpoint returns JSON whose `results` is an HTML fragment of job rows."""

    name = "pageup"
    label = "PageUp employer boards"
    HOST = "https://careers.pageuppeople.com"
    XHR = {"X-Requested-With": "XMLHttpRequest"}
    JOB_RE = re.compile(r"/cw/en(?:-us)?/job/(\d+)/")

    def fetch(self, http: HttpClient, board: BoardConfig, title_filter: TitleFilter | None = None) -> FetchResult:
        inst = board.board["institution_id"]
        data = http.get_json(f"{self.HOST}/{inst}/cw/en/search/?page-items=1000", headers=self.XHR)
        soup = BeautifulSoup(data.get("results") or "", "html.parser")
        out: list[RawVacancy] = []
        seen: set[str] = set()
        for a in soup.select("a.job-link"):
            href = a.get("href") or ""
            m = self.JOB_RE.search(str(href))
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            row = a.find_parent(["tr", "li", "div"]) or a
            loc = row.select_one(".location")
            close = row.select_one(".close-date, time")
            summary = row.select_one(".job-summary, .summary, p")
            url = href if str(href).startswith("http") else f"{self.HOST}{href}"
            vac = RawVacancy(
                source=self.name,
                board=board.key,
                source_job_id=f"{inst}:{m.group(1)}",
                title=a.get_text(" ", strip=True),
                url=url,
                apply_url=url,
                employer=board.name,
                location=loc.get_text(" ", strip=True) if loc else None,
                description=summary.get_text(" ", strip=True) if summary else "",
                description_is_snippet=True,
                is_employer_requisition=True,
                raw={"close": close.get("datetime") or close.get_text(" ", strip=True)} if close else {},
            )
            if close is not None:
                parsed = parse_datetime(close.get("datetime")) if close.get("datetime") else None
                vac.closing_date = parsed.date() if parsed else None
            if title_filter is None or title_filter(vac.title):
                try:
                    resp = http.request("GET", url, headers=self.XHR)
                    if resp.status_code < 400:
                        detail = BeautifulSoup(resp.text, "html.parser")
                        body = detail.select_one("#job-details, .job-details, #job-content, main")
                        if body:
                            vac.description = html_to_text(str(body))
                            vac.description_is_snippet = False
                except SourceError:
                    pass
            out.append(vac)
        return FetchResult(out)
