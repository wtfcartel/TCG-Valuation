"""Cash flow and customer payments, from the committed jobs, invoices and the remittances the reader matched.

13-week forecast (weekly, from the Monday after the report date), two scenarios:
  prompt   work invoiced at each month end, as milestones are completed
  current  work invoiced about a month later (current_invoice_lag_weeks)
Receipts: unpaid invoices (less remittances already received), work done but not invoiced, and the rest of each
committed job billed monthly as it is delivered, each collected on the customer's terms.
Payments: remaining job cost spread to forecast finish (wages in the week, suppliers a month later), plus overheads.
No site work during the Christmas shutdown.

12-month view: the season model's revenue collected a month later; costs paid half in the month, half the month after.
Standard library only. All inputs are synthetic.
"""

from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path

from common.report import DATA, OUTPUT, REPORT_DATE
from demo1_project_control.engine import run as run_projects
from demo4_seasonality.engine import run as run_season

WEEKS = 13


def _assumptions() -> dict[str, str]:
    with (DATA / "cashflow" / "assumptions.csv").open(newline="", encoding="utf-8") as f:
        return {r["key"]: r["value"] for r in csv.DictReader(f)}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _remittances() -> list[dict]:
    path = OUTPUT / "invoice_reader" / "extraction_audit.json"
    if not path.exists():
        return []
    out = []
    for doc in json.loads(path.read_text(encoding="utf-8")):
        if doc["fields"].get("kind") != "remittance":
            continue
        for m in doc.get("remittance_matches") or []:
            out.append({"invoice": m["invoice"], "amount": float(m["paid"]), "received": doc["fields"].get("invoice_date"),
                        "document": doc["document"]})
    return out


def _month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def run() -> dict:
    a = _assumptions()
    start = REPORT_DATE + timedelta(days=(7 - REPORT_DATE.weekday()) % 7 or 7)   # next Monday
    weeks = [start + timedelta(weeks=i) for i in range(WEEKS)]
    end = weeks[-1] + timedelta(days=6)
    shut_a, shut_b = date.fromisoformat(a["shutdown_start"]), date.fromisoformat(a["shutdown_end"])
    working = lambda w: not (shut_a <= w <= shut_b)  # noqa: E731

    def week_of(d: date) -> int | None:
        if d < start:
            return 0
        i = (d - start).days // 7
        return i if i < WEEKS else None

    projects = {p["project_id"]: p for p in _read(DATA / "projects" / "projects.csv")}
    customers = {r["project_id"]: r["customer"] for r in _read(DATA / "projects" / "customers.csv")}
    terms = {pid: int(a[f"terms_{p['client_type']}"]) for pid, p in projects.items()}
    lag = int(a["current_invoice_lag_weeks"])

    rec = {"prompt": [0.0] * WEEKS, "current": [0.0] * WEEKS}
    pay = [0.0] * WEEKS

    # 1. Unpaid invoices, less remittances already received
    remits = _remittances()
    invoices = []
    for inv in _read(DATA / "projects" / "invoices.csv"):
        pid = inv["project_id"]
        issued = date.fromisoformat(inv["issued"])
        due = issued + timedelta(days=terms[pid])
        amount, paid = float(inv["amount"]), float(inv["paid"])
        r = [x for x in remits if x["invoice"] == inv["invoice_no"]]
        remitted = sum(x["amount"] for x in r)
        outstanding = max(amount - paid - remitted, 0.0)
        if paid >= amount:
            status = "Paid"
        elif r and outstanding > 0:
            status = "Short-paid"
        elif r:
            status = "Remittance received"
        elif due < REPORT_DATE:
            status = "Overdue"
        else:
            status = "Not yet due"
        invoices.append({"invoice": inv["invoice_no"], "project_id": pid, "customer": customers.get(pid, pid),
                         "issued": inv["issued"], "due": due.isoformat(), "amount": amount, "paid": paid,
                         "remitted": remitted, "outstanding": outstanding, "status": status,
                         "days_overdue": max((REPORT_DATE - due).days, 0) if status in ("Overdue", "Short-paid") else 0,
                         "remittance_doc": r[0]["document"] if r else ""})
        for when, amt in ([(start, remitted)] if remitted else []) + (
                [(start + timedelta(weeks=int(a["disputed_settle_weeks"])), outstanding)] if status == "Short-paid" else
                [(max(due, start + timedelta(weeks=1 if status == "Overdue" else 0)), outstanding)] if outstanding else []):
            i = week_of(when)
            if i is not None:
                for s in rec:
                    rec[s][i] += amt

    # 2. Work done, not invoiced, and 3. the rest of each job billed monthly as delivered
    proj = run_projects()
    not_invoiced_total = 0.0
    for r in proj["results"]:
        pid = r.p["project_id"]
        t = timedelta(days=terms[pid])
        ub = max(r.under_billed, 0.0)
        not_invoiced_total += ub
        for s, inv_date in (("prompt", start), ("current", start + timedelta(weeks=lag))):
            i = week_of(inv_date + t)
            if ub and i is not None:
                rec[s][i] += ub
        finish = date.fromisoformat(r.p["forecast_finish"])
        live = [w for w in weeks if w <= finish and working(w)]
        remaining_rev = max(r.revised_revenue - r.invoiced - ub, 0.0)
        remaining_cost = max((r.bac if r.stale else r.eac) - r.actual, 0.0)
        span = max(len([w for w in [start + timedelta(weeks=k) for k in range(104)] if w <= finish and working(w)]), 1)
        rev_w, cost_w = remaining_rev / span, remaining_cost / span
        billed: dict[date, float] = {}
        for w in live:
            billed[_month_end(w)] = billed.get(_month_end(w), 0.0) + rev_w
            i = week_of(w)
            pay[i] += cost_w * float(a["labour_share"])
            j = week_of(w + timedelta(weeks=int(a["supplier_terms_weeks"])))
            if j is not None:
                pay[j] += cost_w * (1 - float(a["labour_share"]))
        # suppliers for work done in the four weeks before the forecast starts
        for k in range(int(a["supplier_terms_weeks"])):
            if working(start - timedelta(weeks=k + 1)):
                pay[int(a["supplier_terms_weeks"]) - 1 - k] += cost_w * (1 - float(a["labour_share"]))
        for me, amt in billed.items():
            for s, inv_date in (("prompt", me), ("current", me + timedelta(weeks=lag))):
                i = week_of(inv_date + t)
                if i is not None:
                    rec[s][i] += amt
    for i in range(WEEKS):
        pay[i] += float(a["overhead_per_week"]) * (1 if working(weeks[i]) else 0.5)

    opening = float(a["opening_cash"])
    rows, bal = [], {"prompt": opening, "current": opening}
    for i, w in enumerate(weeks):
        for s in bal:
            bal[s] += rec[s][i] - pay[i]
        rows.append({"week": w.isoformat(), "label": w.strftime("%d %b"), "receipts_prompt": round(rec["prompt"][i], 2),
                     "receipts_current": round(rec["current"][i], 2), "payments": round(pay[i], 2),
                     "balance_prompt": round(bal["prompt"], 2), "balance_current": round(bal["current"], 2),
                     "shutdown": not working(w)})

    # 12-month season view
    season = run_season()
    ebit = {m: sum(x["ebit"] for x in season["monthly"] if x["month"] == m) for m in season["months"]}
    revenue = {b["month"]: b["revenue"] for b in season["business"]}
    months = season["months"]
    cost = {m: revenue[m] - ebit[m] for m in months}
    bal12, monthly = opening, []
    for k, m in enumerate(months):
        prev = months[k - 1]
        cash_in = revenue[prev]
        cash_out = 0.5 * cost[m] + 0.5 * cost[prev]
        bal12 += cash_in - cash_out
        monthly.append({"month": m, "season": season["business"][k]["season"], "cash_in": round(cash_in, 2),
                        "cash_out": round(cash_out, 2), "net": round(cash_in - cash_out, 2), "balance": round(bal12, 2)})

    by_customer: dict[str, dict] = {}
    for inv in invoices:
        c = by_customer.setdefault(inv["customer"], {"customer": inv["customer"], "paid": 0.0, "remitted": 0.0,
                                                      "not_due": 0.0, "overdue": 0.0, "invoiced": 0.0, "max_overdue": 0})
        c["invoiced"] += inv["amount"]
        c["paid"] += inv["paid"]
        c["remitted"] += inv["remitted"]
        if inv["status"] in ("Overdue", "Short-paid"):
            c["overdue"] += inv["outstanding"]
            c["max_overdue"] = max(c["max_overdue"], inv["days_overdue"])
        else:
            c["not_due"] += inv["outstanding"]

    low_p = min(rows, key=lambda r: r["balance_prompt"])
    low_c = min(rows, key=lambda r: r["balance_current"])
    return {"weeks": rows, "monthly": monthly, "invoices": invoices,
            "customers": sorted(by_customer.values(), key=lambda c: -c["invoiced"]), "remittances": remits,
            "opening": opening, "not_invoiced": round(not_invoiced_total, 2),
            "lowest_prompt": low_p, "lowest_current": low_c, "assumptions": a}


if __name__ == "__main__":
    out = run()
    for w in out["weeks"]:
        print(w)
    print("lowest prompt", out["lowest_prompt"]["label"], out["lowest_prompt"]["balance_prompt"],
          "| lowest current", out["lowest_current"]["label"], out["lowest_current"]["balance_current"])
    for m in out["monthly"]:
        print(m)
    for i in out["invoices"]:
        print(i["invoice"], i["customer"], i["status"], i["outstanding"], i["days_overdue"])
    for c in out["customers"]:
        print(c)
