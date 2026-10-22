"""Source adapters against synthetic vendor-shaped payloads (see tests/payloads.py), plus HTTP behaviour."""

import httpx
import pytest
import respx

from logidx.sources.adzuna import AdzunaSource, max_age_for
from logidx.sources.agencies import BullhornSource, RssSource
from logidx.sources.ats import GreenhouseSource, LeverSource, PageUpSource, SmartRecruitersSource, WorkdaySource
from logidx.sources.base import BoardConfig
from logidx.sources.http import SourceError
from tests import payloads


def board(ats, **b):
    return BoardConfig(key=f"{ats}_fixture", name=f"{ats.title()} (Fixture)", ats=ats, board=b)


@respx.mock
def test_adzuna_parses_and_discards_predicted_salary(http):
    route = respx.get("https://api.adzuna.com/v1/api/jobs/au/search/1").mock(
        return_value=httpx.Response(200, json=payloads.ADZUNA_PAGE)
    )
    res = AdzunaSource("id", "key").search(http, "general manager", max_age_days=3)
    assert route.called
    params = dict(route.calls[0].request.url.params)
    assert params["what_phrase"] == "general manager" and params["max_days_old"] == "3"
    first, second = res.vacancies
    assert first.title == "General Manager Supply Chain"  # highlight tags stripped
    assert first.employer == "Southern Freight (Fixture)" and first.description_is_snippet
    assert first.salary_max == 260000 and not first.salary_predicted
    assert second.salary_predicted  # ingest discards it
    assert "snippets" in res.limitation


def test_adzuna_unavailable_without_keys():
    ok, reason = AdzunaSource("", "").available
    assert not ok and "ADZUNA_APP_ID" in reason


def test_max_age_covers_gap():
    from datetime import UTC, datetime, timedelta

    assert max_age_for(None) == 14
    assert max_age_for(datetime.now(UTC) - timedelta(hours=8)) == 2
    assert max_age_for(datetime.now(UTC) - timedelta(days=5)) == 7


@respx.mock
def test_workday_lists_and_hydrates_relevant_only(http):
    base = "https://example.wd3.myworkdayjobs.com/wday/cxs/example/External"
    respx.post(f"{base}/jobs").mock(return_value=httpx.Response(200, json=payloads.WORKDAY_LIST))
    detail = respx.get(f"{base}/job/Melbourne/EGM-Operations_R10001").mock(
        return_value=httpx.Response(200, json=payloads.WORKDAY_DETAIL)
    )
    other = respx.get(f"{base}/job/Laverton/Warehouse-Team-Leader_R10002")
    res = WorkdaySource().fetch(
        http,
        board("workday", host="example.wd3.myworkdayjobs.com", tenant="example", site="External", full_listing=True),
        title_filter=lambda t: "Executive" in t,
    )
    assert detail.called and not other.called
    egm = next(v for v in res.vacancies if v.reference == "R10001")
    assert egm.is_employer_requisition and egm.explicit_open is True
    assert "national operations" in egm.description and not egm.description_is_snippet
    assert not res.truncated  # full listing


@respx.mock
def test_workday_keyword_mode_is_truncated(http):
    base = "https://example.wd3.myworkdayjobs.com/wday/cxs/example/External"
    respx.post(f"{base}/jobs").mock(return_value=httpx.Response(200, json={"total": 0, "jobPostings": []}))
    res = WorkdaySource().fetch(
        http, board("workday", host="example.wd3.myworkdayjobs.com", tenant="example", site="External")
    )
    assert res.truncated and "keywords" in res.limitation


@respx.mock
def test_smartrecruiters(http):
    api = "https://api.smartrecruiters.com/v1/companies/CoastalFixture/postings"
    respx.get(api).mock(return_value=httpx.Response(200, json=payloads.SMARTRECRUITERS_LIST))
    respx.get(f"{api}/744000012345678").mock(return_value=httpx.Response(200, json=payloads.SMARTRECRUITERS_DETAIL))
    [v] = SmartRecruitersSource().fetch(http, board("smartrecruiters", company="CoastalFixture")).vacancies
    assert v.title == "Head of Commercial" and v.location == "Melbourne, VIC, AU"
    assert v.apply_url.endswith("/apply") and "Senior commercial leadership" in v.description


@respx.mock
def test_greenhouse_unescapes_content(http):
    respx.get("https://boards-api.greenhouse.io/v1/boards/fixture/jobs").mock(
        return_value=httpx.Response(200, json=payloads.GREENHOUSE_JOBS)
    )
    [v] = GreenhouseSource().fetch(http, board("greenhouse", token="fixture")).vacancies
    assert v.description == "Lead acquisitions, due diligence and post-merger integration."
    assert v.source_job_id == "fixture:5550001"


@respx.mock
def test_lever(http):
    respx.get("https://api.lever.co/v0/postings/fixture").mock(
        return_value=httpx.Response(200, json=payloads.LEVER_POSTINGS)
    )
    [v] = LeverSource().fetch(http, board("lever", site="fixture")).vacancies
    assert v.title == "Head of Transformation" and "Turnaround" in v.description and v.posted_at is not None


@respx.mock
def test_pageup(http):
    respx.get("https://careers.pageuppeople.com/999/cw/en/search/").mock(
        return_value=httpx.Response(200, json=payloads.PAGEUP_LIST)
    )
    respx.get("https://careers.pageuppeople.com/999/cw/en/job/600123/general-manager-fleet-services").mock(
        return_value=httpx.Response(200, text=payloads.PAGEUP_DETAIL_HTML)
    )
    [v] = PageUpSource().fetch(http, board("pageup", institution_id="999"), title_filter=lambda t: True).vacancies
    assert v.source_job_id == "999:600123" and v.location == "Dandenong, VIC"
    assert str(v.closing_date) == "2030-11-15" and "national fleet" in v.description


@respx.mock
def test_bullhorn_agency_listing(http):
    route = respx.get("https://public-rest33.bullhornstaffing.com/rest-services/tok/search/JobOrder").mock(
        return_value=httpx.Response(200, json=payloads.bullhorn_page())
    )
    res = BullhornSource().fetch(
        http,
        BoardConfig(
            key="six_degrees",
            name="Six Degrees Executive",
            ats="bullhorn",
            agency=True,
            board={"cluster": "33", "corp_token": "tok"},
        ),
    )
    assert route.calls[0].request.url.params["query"] == "(isOpen:1)"
    [v] = res.vacancies
    assert v.reference == "BH-31092" and v.agency == "Six Degrees Executive" and v.is_agency_listing


@respx.mock
def test_rss_feed_and_robots(http):
    respx.get("https://jobs.example.org/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://jobs.example.org/feed.xml").mock(return_value=httpx.Response(200, content=payloads.RSS_FEED))
    [v] = RssSource().fetch(http, board("rss", url="https://jobs.example.org/feed.xml")).vacancies
    assert v.url == "https://jobs.example.org/ceo-123"  # tracking parameter removed
    assert v.posted_at.isoformat() == "2026-10-18T22:00:00+00:00"


@respx.mock
def test_rss_respects_robots_disallow(http):
    respx.get("https://jobs.example.org/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /")
    )
    with pytest.raises(SourceError) as exc:
        RssSource().fetch(http, board("rss", url="https://jobs.example.org/feed.xml"))
    assert exc.value.blocked


def test_rss_rejects_hostile_xml(http):
    bomb = (b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]>'
            b"<rss><channel>&b;</channel></rss>")
    with respx.mock:
        respx.get("https://x.example/robots.txt").mock(return_value=httpx.Response(404))
        respx.get("https://x.example/f.xml").mock(return_value=httpx.Response(200, content=bomb))
        with pytest.raises(SourceError):
            RssSource().fetch(http, board("rss", url="https://x.example/f.xml"))


# ------------------------------------------------------------------ HTTP behaviour
@respx.mock
def test_403_is_access_blocked_and_not_retried(http):
    route = respx.get("https://boards-api.greenhouse.io/v1/boards/x/jobs").mock(return_value=httpx.Response(403))
    with pytest.raises(SourceError) as exc:
        GreenhouseSource().fetch(http, board("greenhouse", token="x"))
    assert exc.value.blocked and route.call_count == 1


@respx.mock
def test_5xx_retried_with_backoff_then_succeeds(http):
    route = respx.get("https://boards-api.greenhouse.io/v1/boards/x/jobs").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json={"jobs": []}),
        ]
    )
    assert GreenhouseSource().fetch(http, board("greenhouse", token="x")).vacancies == []
    assert route.call_count == 3


@respx.mock
def test_transport_errors_become_failures(http):
    respx.get("https://boards-api.greenhouse.io/v1/boards/x/jobs").mock(side_effect=httpx.ConnectTimeout("t"))
    with pytest.raises(SourceError) as exc:
        GreenhouseSource().fetch(http, board("greenhouse", token="x"))
    assert not exc.value.blocked


def test_board_config_requires_identifiers():
    assert not BoardConfig(key="a", name="A", ats="bullhorn", board={"cluster": "", "corp_token": ""}).configured
    assert not BoardConfig(key="a", name="A", ats="workday", board={}).configured
    assert BoardConfig(key="a", name="A", ats="lever", board={"site": "a"}).configured
