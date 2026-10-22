"""Known-vacancy recall regression: access gaps, found cases, miss diagnosis and taxonomy fixtures."""

import httpx
import respx
from sqlalchemy import select

from logidx import recall
from logidx.enums import MissCause, RecallOutcome
from logidx.models import RecallCase
from logidx.pipeline.runner import RunPlan, run_discovery, start_run
from logidx.sources.agencies import BullhornSource
from logidx.sources.base import BoardConfig
from logidx.sources.registry import RESTRICTED, Watchlist
from tests import payloads


def six_degrees(configured=True):
    b = {"cluster": "33", "corp_token": "tok"} if configured else {"cluster": "", "corp_token": ""}
    return BoardConfig(
        key="six_degrees",
        name="Six Degrees Executive",
        ats="bullhorn",
        agency=True,
        target_group="executive_search",
        board=b,
    )


def run_with(session, boards):
    run = start_run(session, trigger="test")
    return run_discovery(session, run, plan=RunPlan([], {"bullhorn": BullhornSource()}, Watchlist(boards), RESTRICTED))


def outcomes(session, run):
    return {r.case.key: r for r in recall.evaluate_all(session, run)}


def test_access_gaps_when_carriers_not_searched(session):
    run = run_with(session, [six_degrees(configured=False)])
    res = outcomes(session, run)
    a, b = res["case_a_sigma_head_of_logistics"], res["case_b_six_degrees_gm_supply_chain"]
    assert a.outcome == RecallOutcome.ACCESS_GAP and a.cause == MissCause.SOURCE_ACCESS
    assert a.detail["carrier_statuses"]["linkedin"] == "NOT SEARCHED"
    assert b.outcome == RecallOutcome.ACCESS_GAP
    # Case A's geography is still classified from the known location, independent of discovery.
    assert a.detail["probe"]["geography"] == "INTERSTATE — RELOCATION OR SUBSTANTIAL ATTENDANCE"
    assert a.detail["probe"]["relevant"] is True


@respx.mock
def test_case_b_found_via_bullhorn_reference(session):
    respx.get("https://public-rest33.bullhornstaffing.com/rest-services/tok/search/JobOrder").mock(
        return_value=httpx.Response(200, json=payloads.bullhorn_page(31092))
    )
    run = run_with(session, [six_degrees()])
    b = outcomes(session, run)["case_b_six_degrees_gm_supply_chain"]
    assert b.outcome == RecallOutcome.FOUND and b.vacancy_id is not None
    assert "source id" in b.detail["matched_by"]


@respx.mock
def test_case_b_missed_when_carrier_searched_but_absent(session):
    respx.get("https://public-rest33.bullhornstaffing.com/rest-services/tok/search/JobOrder").mock(
        return_value=httpx.Response(200, json={"total": 0, "start": 0, "count": 0, "data": []})
    )
    run = run_with(session, [six_degrees()])
    b = outcomes(session, run)["case_b_six_degrees_gm_supply_chain"]
    assert b.outcome == RecallOutcome.MISSED and b.cause == MissCause.INDEXING
    assert "six_degrees" in b.detail["explanation"]


def test_results_accumulate_and_metrics(session):
    run = run_with(session, [six_degrees(configured=False)])
    recall.evaluate_all(session, run)
    recall.evaluate_all(session, run)
    case = session.scalar(select(RecallCase).where(RecallCase.key == "case_a_sigma_head_of_logistics"))
    assert len(case.results) == 2
    from datetime import UTC, datetime, timedelta

    m = recall.metrics(session, datetime.now(UTC) - timedelta(days=1))
    assert m["access_gaps"] == 2 and m["recall_accessible"] is None  # no accessible cases → no recall claim
    assert m["fixtures_passed"] == m["fixtures_total"] > 0


def test_taxonomy_fixtures_all_pass():
    failures = [(f.key, f.problems) for f in recall.taxonomy_fixtures() if not f.passed]
    assert failures == []
