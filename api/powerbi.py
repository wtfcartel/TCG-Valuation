"""GET /api/powerbi?table=<name>&format=csv|json — live data feeds for Power BI (Get Data → Web) or Excel.

Every table is recalculated from the synthetic CSVs on each request, except ap_queue, which is the last batch the
OCR reader processed (OCR of the full inbox needs the Tesseract engine, which runs locally, not on Vercel).
Standard library only.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from demo1_project_control.engine import RULE_LABEL, run as run_projects  # noqa: E402
from demo2_plant_allocation.engine import run as run_plant  # noqa: E402


def t_projects() -> list[dict]:
    return [{"project_id": r.p["project_id"], "project": r.p["name"], "client_type": r.p["client_type"],
             "project_manager": r.p["project_manager"], "status": r.rag, "contract_value": r.revised_revenue,
             "pct_complete": float(r.p["pct_complete"]), "budget_at_completion": r.bac, "actual_cost": r.actual,
             "committed_cost": r.committed, "earned_value": round(r.ev, 2),
             "cpi": None if r.stale else round(r.cpi, 4), "forecast_cost": None if r.stale else round(r.eac, 2),
             "quoted_margin_pct": round(r.quoted_margin, 4),
             "forecast_margin_pct": None if r.stale else round(r.forecast_margin, 4),
             "margin_fade_pts": None if r.stale else round(r.fade * 100, 2), "invoiced": r.invoiced,
             "not_invoiced": round(max(r.under_billed, 0), 2), "schedule_slip_days": r.slip_days,
             "cost_data_age_days": r.days_since_update} for r in run_projects()["results"]]


def t_exceptions() -> list[dict]:
    res = run_projects()
    return [{"key": e.key, "project_id": e.project_id, "issue": RULE_LABEL[e.rule], "severity": e.severity,
             "finding": e.finding, "owner": e.owner, "escalate_to": e.escalate_to or "", "due": e.due.isoformat(),
             "status": res["status"].get(e.key, "RAISED"), "value": round(e.value, 4)} for e in res["exceptions"]]


def t_margin_history() -> list[dict]:
    return [{"project_id": "P-101", **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in h.items()}}
            for h in run_projects()["history"]]


def t_debtor_ageing() -> list[dict]:
    return [{"bucket": k, "outstanding": v} for k, v in run_projects()["portfolio"]["ageing"].items()]


def t_plant_plan() -> list[dict]:
    res = run_plant()
    return [{"request_id": o.request_id, "project_id": res["requests"][o.request_id]["project_id"],
             "machine_type": res["requests"][o.request_id]["machine_type"], "start": o.days[0].isoformat(),
             "days": len(o.days), "allocation": o.kind, "asset_id": o.asset_id or "", "operator_id": o.operator_id or "",
             "service_first": o.service_on.isoformat() if o.service_on else "", "cost": round(o.cost, 2),
             "hire_alternative": round(next(x.cost for x in res["options"][o.request_id] if x.kind == "HIRE"), 2)}
            for o in res["plan"]]


def t_plant_fleet() -> list[dict]:
    return [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()} for f in run_plant()["fleet"]]


def t_plant_actions() -> list[dict]:
    return run_plant()["actions"]


def t_ap_queue() -> list[dict]:
    path = os.path.join(ROOT, "output", "invoice_reader", "extraction_audit.json")
    with open(path, encoding="utf-8") as f:
        audit = json.load(f)
    rows = []
    for a in audit:
        fl = a["fields"]
        num = lambda k: float(fl[k]) if fl.get(k) not in (None, "None", "") else None  # noqa: E731
        rows.append({"document": a["document"], "method": a["method"], "status": a["status"], "kind": fl["kind"],
                     "supplier": fl.get("supplier_text"), "invoice_number": fl.get("invoice_number"),
                     "invoice_date": fl.get("invoice_date"), "po_number": None if fl.get("po_number") == "None" else fl.get("po_number"),
                     "subtotal": num("subtotal"), "gst": num("gst"), "total": num("total"),
                     "suggested_gl": a["suggested_gl"] or "", "gl_confidence": a["gl_confidence"],
                     "issues": " | ".join(a["issues"]), "ocr_confidence": a["ocr_confidence"]})
    return rows


TABLES = {"projects": t_projects, "exceptions": t_exceptions, "margin_history": t_margin_history,
          "debtor_ageing": t_debtor_ageing, "ap_queue": t_ap_queue, "plant_plan": t_plant_plan,
          "plant_fleet": t_plant_fleet, "plant_actions": t_plant_actions}


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return buf.getvalue()


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        q = parse_qs(urlparse(self.path).query)
        table, fmt = (q.get("table") or [""])[0], (q.get("format") or ["csv"])[0]
        if table not in TABLES:
            body, ctype, code = json.dumps({"tables": sorted(TABLES), "usage": "/api/powerbi?table=projects&format=csv",
                                            "data": "synthetic demonstration data"}).encode(), "application/json", 200
        else:
            rows = TABLES[table]()
            if fmt == "json":
                body, ctype = json.dumps(rows, default=str).encode(), "application/json"
            else:
                body, ctype = to_csv(rows).encode(), "text/csv; charset=utf-8"
            code = 200
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
