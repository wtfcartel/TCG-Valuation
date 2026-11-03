"""Demo 1 — Project margin early-warning and exceptions register.

Calculations (all traceable to /data/projects/*.csv):
  revised contract   = quoted revenue + approved variation revenue
  revised budget BAC = quoted cost + approved variation cost
  earned value EV    = BAC x physical % complete (reported by the PM)
  cost performance   = EV / actual cost to date (CPI; below 1.0 means each $1 of planned work is costing more than $1)
  forecast cost EAC  = max(BAC / CPI, actual + committed)
  forecast margin    = (revised contract - EAC) / revised contract
  margin fade        = quoted margin - forecast margin (percentage points)
  under-billing      = revised contract x % complete - invoiced to date

A project whose cost data is older than STALE_DAYS is reported as NOT REPORTED and excluded from forecast totals,
rather than shown as healthy. (Pattern from LogiDx coverage.py: missing data is never presented as "no problem".)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from common.report import DATA, REPORT_DATE, chain_events, d, read_csv

SRC = DATA / "projects"

# Thresholds are deliberately simple and would be agreed with management in Days 1-30.
RULES = {
    "STALE_DAYS": 14,
    "FADE_AMBER": 0.03, "FADE_RED": 0.06,              # margin fade, percentage points
    "OVERCOMMIT_AMBER": 0.05,                          # actual+committed above category budget, share of budget
    "VAR_AGE_AMBER": 14, "VAR_AGE_RED": 28,            # days unapproved with work already performed
    "UNDERBILL_AMBER": 0.10, "UNDERBILL_RED": 0.20,    # share of earned revenue not yet invoiced
    "DEBTOR_AMBER": 60, "DEBTOR_RED": 90,              # days since invoice issued, unpaid
    "SLIP_AMBER": 14, "SLIP_RED": 30,                  # calendar days forecast finish beyond plan
}

RULE_LABEL = {
    "COST_DATA_STALE": "Cost data not updated",
    "MARGIN_FADE": "Forecast margin below quote",
    "OVERCOMMITTED": "Commitments exceed category budget",
    "PENDING_VARIATION": "Variation work done, not approved",
    "UNDER_BILLED": "Work done, not invoiced",
    "DEBTOR_OVERDUE": "Invoice unpaid",
    "SCHEDULE_SLIP": "Forecast finish beyond plan",
}

ACCOUNTS, COMMERCIAL, BOD = "Jo Park (Accounts Lead)", "Ravi Menon (Commercial Manager)", "Business Operations Director"


@dataclass
class Exception_:
    project_id: str
    rule: str
    severity: str  # RED | AMBER | NOT REPORTED
    finding: str
    owner: str
    escalate_to: str | None
    due: date
    value: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.project_id}|{self.rule}"


@dataclass
class ProjectResult:
    p: dict
    stale: bool
    days_since_update: int
    revised_revenue: float
    bac: float
    actual: float
    committed: float
    ev: float
    cpi: float | None
    eac: float | None
    quoted_margin: float
    forecast_margin: float | None
    fade: float | None
    earned_revenue: float
    invoiced: float
    under_billed: float
    slip_days: int
    pending_var_revenue: float
    forecast_margin_if_pending_approved: float | None
    categories: list[dict] = field(default_factory=list)
    rag: str = "GREEN"


def _business_days(n: int) -> date:
    day, added = REPORT_DATE, 0
    while added < n:
        day += timedelta(days=1)
        if day.weekday() < 5:
            added += 1
    return day


def load() -> dict:
    return {name: read_csv(SRC / f"{name}.csv") for name in
            ("projects", "cost_lines", "variations", "invoices", "p101_monthly_history", "management_responses")}


def project_metrics(p: dict, lines: list[dict], variations: list[dict], invoices: list[dict]) -> ProjectResult:
    qrev, qcost, pc = float(p["quoted_revenue"]), float(p["quoted_cost"]), float(p["pct_complete"])
    approved = [v for v in variations if v["status"] == "approved"]
    pending = [v for v in variations if v["status"] == "pending"]
    rev = qrev + sum(float(v["revenue"]) for v in approved)
    bac = qcost + sum(float(v["cost"]) for v in approved)
    actual = sum(float(c["actual_to_date"]) for c in lines)
    committed = sum(float(c["committed_not_yet_spent"]) for c in lines)
    ev = bac * pc
    cpi = ev / actual if actual else None
    eac = max(bac / cpi, actual + committed) if cpi else None
    qm = (qrev - qcost) / qrev
    fm = (rev - eac) / rev if eac is not None else None
    pend_rev = sum(float(v["revenue"]) for v in pending if v["work_performed"] == "yes")
    fm_if = (rev + pend_rev - eac) / (rev + pend_rev) if eac is not None and pend_rev else None
    earned_rev = rev * pc
    invoiced = sum(float(i["amount"]) for i in invoices)
    days_since = (REPORT_DATE - d(p["cost_updated"])).days
    cats = []
    for c in lines:
        b, a, cm = float(c["budget"]), float(c["actual_to_date"]), float(c["committed_not_yet_spent"])
        cats.append({"category": c["category"], "budget": b, "actual": a, "committed": cm,
                     "over": (a + cm) - b, "over_share": ((a + cm) - b) / b if b else 0.0})
    return ProjectResult(
        p=p, stale=days_since > RULES["STALE_DAYS"], days_since_update=days_since, revised_revenue=rev, bac=bac,
        actual=actual, committed=committed, ev=ev, cpi=cpi, eac=eac, quoted_margin=qm, forecast_margin=fm,
        fade=(qm - fm) if fm is not None else None, earned_revenue=earned_rev, invoiced=invoiced,
        under_billed=earned_rev - invoiced, slip_days=(d(p["forecast_finish"]) - d(p["planned_finish"])).days,
        pending_var_revenue=pend_rev, forecast_margin_if_pending_approved=fm_if, categories=cats)


def exceptions_for(r: ProjectResult, variations: list[dict], invoices: list[dict]) -> list[Exception_]:
    pid, pm = r.p["project_id"], f'{r.p["project_manager"]} (PM)'
    out: list[Exception_] = []
    R = RULES

    if r.stale:
        out.append(Exception_(pid, "COST_DATA_STALE", "NOT REPORTED",
                              f"Costs last updated {r.days_since_update} days ago; margin and cost forecasts suppressed "
                              "until updated", pm, BOD, _business_days(2)))
    else:
        if r.fade is not None and r.fade >= R["FADE_AMBER"]:
            sev = "RED" if r.fade >= R["FADE_RED"] else "AMBER"
            out.append(Exception_(pid, "MARGIN_FADE", sev,
                                  f"Forecast margin {r.forecast_margin:.1%} vs {r.quoted_margin:.1%} quoted "
                                  f"({r.fade * 100:.1f} pts fade; CPI {r.cpi:.2f})", pm,
                                  BOD if sev == "RED" else None, _business_days(2 if sev == "RED" else 5), r.fade))
        for c in r.categories:
            if c["budget"] and c["over_share"] > R["OVERCOMMIT_AMBER"]:
                out.append(Exception_(pid, "OVERCOMMITTED", "AMBER",
                                      f'{c["category"]}: spent + committed ${c["actual"] + c["committed"]:,.0f} vs '
                                      f'budget ${c["budget"]:,.0f} (+{c["over_share"]:.0%})', pm, COMMERCIAL,
                                      _business_days(5), c["over"]))

    for v in variations:
        if v["status"] == "pending" and v["work_performed"] == "yes":
            age = (REPORT_DATE - d(v["raised"])).days
            if age > R["VAR_AGE_AMBER"]:
                sev = "RED" if age > R["VAR_AGE_RED"] else "AMBER"
                out.append(Exception_(pid, "PENDING_VARIATION", sev,
                                      f'{v["variation_id"]} "{v["description"]}": ${float(v["cost"]):,.0f} cost incurred, '
                                      f'${float(v["revenue"]):,.0f} claim unapproved for {age} days', COMMERCIAL, pm,
                                      _business_days(3), float(v["revenue"])))

    if r.earned_revenue and r.under_billed / r.earned_revenue > R["UNDERBILL_AMBER"]:
        share = r.under_billed / r.earned_revenue
        sev = "RED" if share > R["UNDERBILL_RED"] else "AMBER"
        out.append(Exception_(pid, "UNDER_BILLED", sev,
                              f"${r.under_billed:,.0f} of work completed but not invoiced ({share:.0%} of earned revenue)",
                              pm, ACCOUNTS, _business_days(3), r.under_billed))

    for i in invoices:
        outstanding = float(i["amount"]) - float(i["paid"])
        age = (REPORT_DATE - d(i["issued"])).days
        if outstanding > 0 and age > R["DEBTOR_AMBER"]:
            sev = "RED" if age > R["DEBTOR_RED"] else "AMBER"
            out.append(Exception_(pid, "DEBTOR_OVERDUE", sev,
                                  f'{i["invoice_no"]} ${outstanding:,.0f} unpaid, {age} days since issue',
                                  ACCOUNTS, pm, _business_days(3), outstanding))

    if r.slip_days > R["SLIP_AMBER"]:
        sev = "RED" if r.slip_days > R["SLIP_RED"] else "AMBER"
        out.append(Exception_(pid, "SCHEDULE_SLIP", sev,
                              f'Forecast finish {r.p["forecast_finish"]} is {r.slip_days} days after plan',
                              pm, BOD if sev == "RED" else None, _business_days(5), r.slip_days))
    return out


def debtor_ageing(invoices: list[dict]) -> dict[str, float]:
    buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    for i in invoices:
        o = float(i["amount"]) - float(i["paid"])
        if o <= 0:
            continue
        age = (REPORT_DATE - d(i["issued"])).days
        key = "0-30" if age <= 30 else "31-60" if age <= 60 else "61-90" if age <= 90 else "90+"
        buckets[key] += o
    return buckets


def history(rows: list[dict], p: dict) -> list[dict]:
    """Month-by-month forecast margin for one project: when would the early warning have tripped?"""
    qrev, qcost = float(p["quoted_revenue"]), float(p["quoted_cost"])
    qm = (qrev - qcost) / qrev
    out = []
    for h in rows:
        rev = qrev + float(h["approved_variation_revenue"])
        bac = qcost + float(h["approved_variation_cost"])
        pc, ac = float(h["pct_complete"]), float(h["actual_cost"])
        cpi = bac * pc / ac
        eac = bac / cpi
        fm = (rev - eac) / rev
        out.append({"month_end": h["month_end"], "pct_complete": pc, "cpi": cpi, "forecast_margin": fm,
                    "fade": qm - fm, "budget_remaining_share": (bac - ac) / bac,
                    "flag": "RED" if qm - fm >= RULES["FADE_RED"] else "AMBER" if qm - fm >= RULES["FADE_AMBER"] else "GREEN"})
    return out


def action_log(excs: list[Exception_], responses: list[dict]) -> list[dict]:
    events = [{"date": REPORT_DATE.isoformat(), "exception_key": e.key, "event": "RAISED", "by": "system",
               "note": f"{e.severity}: {e.finding}; owner {e.owner}; due {e.due.isoformat()}"} for e in excs]
    keys = {e.key for e in excs}
    events += [{k: r[k] for k in ("date", "exception_key", "event", "by", "note")}
               for r in responses if r["exception_key"] in keys]
    return chain_events(events)


def run() -> dict:
    data = load()
    by = lambda rows, pid: [x for x in rows if x["project_id"] == pid]  # noqa: E731
    results, excs = [], []
    for p in data["projects"]:
        pid = p["project_id"]
        r = project_metrics(p, by(data["cost_lines"], pid), by(data["variations"], pid), by(data["invoices"], pid))
        e = exceptions_for(r, by(data["variations"], pid), by(data["invoices"], pid))
        sevs = {x.severity for x in e}
        r.rag = "NOT REPORTED" if r.stale else "RED" if "RED" in sevs else "AMBER" if "AMBER" in sevs else "GREEN"
        results.append(r)
        excs.extend(e)
    order = {"RED": 0, "NOT REPORTED": 1, "AMBER": 2}
    excs.sort(key=lambda x: (order[x.severity], x.due, x.project_id))
    log = action_log(excs, data["management_responses"])
    status = {}
    for ev in log:
        status[ev["exception_key"]] = ev["event"]

    live = [r for r in results if not r.stale]
    rev = sum(r.revised_revenue for r in live)
    portfolio = {
        "projects": len(results), "excluded_stale": [r.p["project_id"] for r in results if r.stale],
        "revised_revenue": rev, "forecast_gm": sum(r.revised_revenue - r.eac for r in live),
        "quoted_gm": sum(r.revised_revenue * r.quoted_margin for r in live),
        "under_billed": sum(max(r.under_billed, 0) for r in results),
        "ageing": debtor_ageing(data["invoices"]),
        "counts": {s: sum(1 for x in excs if x.severity == s) for s in ("RED", "AMBER", "NOT REPORTED")},
    }
    portfolio["forecast_gm_pct"] = portfolio["forecast_gm"] / rev
    portfolio["quoted_gm_pct"] = portfolio["quoted_gm"] / rev
    p101 = next(p for p in data["projects"] if p["project_id"] == "P-101")
    return {"results": results, "exceptions": excs, "status": status, "log": log, "portfolio": portfolio,
            "history": history(data["p101_monthly_history"], p101)}
