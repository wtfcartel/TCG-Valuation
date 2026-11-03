"""Tests for the calculations and controls in all three demos. Run: python -m pytest -q"""

from __future__ import annotations

import copy

import pytest

from common.report import chain_events, verify_chain

# ------------------------------------------------------------------ Demo 3: invoice reader
from demo3_invoice_reader import reader as R


@pytest.fixture(scope="module")
def batch():
    return {r.cap.source: r for r in R.run_batch()}


def test_abn_checksum():
    assert R.abn_valid("49 624 595 711")
    assert not R.abn_valid("20 052 172 128")  # one OCR-misread digit must fail
    assert not R.abn_valid("12 345")


def test_routing_outcomes(batch):
    expected = {
        "pitchline_PSS-20915.eml": "READY", "kerrigan_KQ-5520.eml": "READY", "southway_SF-77812.jpg": "READY",
        "torque_TH-1187.jpg": "READY", "eastvale_remittance.jpg": "READY",
        "meridian_MSC-0042.jpg": "NEEDS APPROVAL", "bayside_BPH-4436.jpg": "NEEDS APPROVAL",
        "council_remittance.eml": "NEEDS APPROVAL",
        "bayside_BPH-4410.eml": "EXCEPTION", "greenline_GIS-3307.eml": "EXCEPTION",
    }
    assert {k: v.status for k, v in batch.items()} == expected


def test_scanned_fields_read_correctly(batch):
    m = batch["meridian_MSC-0042.jpg"].ext
    assert (m.abn, m.invoice_number, m.subtotal, m.gst, m.total) == ("20 052 172 123", "MSC-0042", 8250.0, 825.0, 9075.0)
    t = batch["torque_TH-1187.jpg"].ext
    assert t.total == 4802.6 and sum(x["amount"] for x in t.lines) == pytest.approx(t.subtotal)


def test_gl_unavailable_routes_to_pm_with_variation_link(batch):
    r = batch["meridian_MSC-0042.jpg"]
    assert r.suggested_gl is None and r.gl_confidence < 0.75
    assert [c["code"] for c in r.gl_candidates[:2]] == ["5600", "6200"]
    assert r.approver["name"] == "Sam Ortiz"
    assert any("V-101-2" in x for x in r.related)


def test_po_cumulative_overrun(batch):
    r = batch["bayside_BPH-4436.jpg"]
    assert any("over by $10,250" in i for i in r.issues)


def test_duplicate_and_gst_errors_are_held(batch):
    assert any("Duplicate" in i for i in batch["bayside_BPH-4410.eml"].issues)
    assert any("GST" in i for i in batch["greenline_GIS-3307.eml"].issues)


def test_remittance_short_payment(batch):
    r = batch["council_remittance.eml"]
    assert r.remittance_matches[0]["difference"] == -60000.0


def test_asset_reference_matched_despite_ocr_error():
    plant = [{"asset_id": "EX20-01"}, {"asset_id": "GR-01"}]
    assert R.match_assets(["BX20-01"], plant) == ["EX20-01"]
    assert R.match_assets(["QQ20-01"], plant) == []


# ------------------------------------------------------------------ Demo 1: project control
from demo1_project_control import engine as P


@pytest.fixture(scope="module")
def projects():
    return P.run()


def test_p101_forecast_margin(projects):
    r = next(x for x in projects["results"] if x.p["project_id"] == "P-101")
    # BAC 1,516,000; EV 833,800; AC 905,000 → CPI 0.9213; EAC = BAC x AC / EV = 1,645,454.5; revenue 1,895,000
    assert r.cpi == pytest.approx(0.92133, abs=1e-4)
    assert r.eac == pytest.approx(1_516_000 * 905_000 / 833_800, abs=0.01)
    assert r.forecast_margin == pytest.approx(0.1317, abs=1e-3)


def test_stale_cost_data_is_not_reported(projects):
    r = next(x for x in projects["results"] if x.p["project_id"] == "P-103")
    assert r.rag == "NOT REPORTED"
    assert "P-103" in projects["portfolio"]["excluded_stale"]


def test_early_warning_trips_in_september(projects):
    flags = {h["month_end"]: h["flag"] for h in projects["history"]}
    assert flags == {"2026-07-31": "GREEN", "2026-08-31": "GREEN", "2026-09-30": "AMBER", "2026-10-31": "RED"}


def test_every_exception_has_owner_and_due_date(projects):
    assert all(e.owner and e.due for e in projects["exceptions"])


def test_action_log_detects_tampering():
    log = chain_events([{"event": "RAISED", "n": 1}, {"event": "CLOSED", "n": 2}, {"event": "RAISED", "n": 3}])
    assert verify_chain(log) == (True, None)
    bad = copy.deepcopy(log)
    bad[1]["event"] = "RAISED"
    assert verify_chain(bad) == (False, 1)


# ------------------------------------------------------------------ Demo 2: plant allocation
from demo2_plant_allocation import engine as A


def test_expired_ticket_blocks_operator():
    data = A.load()
    op = next(o for o in data["operators"] if o["operator_id"] == "OP-01")
    req = next(r for r in data["requests_next_week"] if r["request_id"] == "R1")
    ok, why = A.operator_eligibility(op, req, A.workdays(A.d(req["start"]), 5), data["tickets"], data["site_inductions"])
    assert not ok and "expired" in why


def test_plan_is_cheapest_and_feasible():
    res = A.run()
    assert res["total"] == pytest.approx(29480, abs=1)
    used = {}
    for o in res["plan"]:
        if o.kind == "OWNED":
            for key in (o.asset_id, o.operator_id):
                assert not (set(used.get(key, ())) & set(o.days)), f"{key} double-booked"
                used[key] = tuple(used.get(key, ())) + o.days


def test_cost_of_lapsed_ticket():
    assert A.run()["total"] - A.what_if_ticket_renewed("OP-01", "excavator") == pytest.approx(5350, abs=1)


def test_abn_reconciled_only_when_close_to_supplier_master():
    ref = R.load_reference()
    base = ("Pitchline Synthetic Surfaces TAX INVOICE\nABN {abn}\nInvoice No: PSS-30001\nInvoice Date: 27/10/2026\n"
            "Due Date: 26/11/2026\nPO Number: PO-3021\nSynthetic turf supply 1 ea $1,000.00 $1,000.00\n"
            "Subtotal $1,000.00\nGST $100.00\nTotal AUD $1,100.00\n")
    near = R.process_text(base.format(abn="49 624 505 711"), ref=ref)   # one digit misread
    far = R.process_text(base.format(abn="11 111 595 711"), ref=ref)    # too different to trust
    assert near.ext.abn == "49 624 595 711" and near.status == "READY"
    assert far.status == "EXCEPTION"


def test_abn_read_through_ocr_punctuation():
    assert R.extract("Acme\nABN 49 624:595.711 Invoice Date: 27/10/2026").abn == "49 624 595 711"
    assert R.extract("Acme\nABN14.281 152/836 Invoice Date").abn == "14 281 152 836"
    assert R.extract("Acme\nABN 14.281 152 89 Invoice").abn is None  # only 10 digits: not guessed
