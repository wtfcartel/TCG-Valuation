"""Demo 2 — Plant and operator allocation decision.

For next week's machine requests, find the lowest-cost feasible plan across owned plant + eligible operators and
external wet hire.

Eligibility (adapted from ShiftReady lib/nurse-status.ts + lib/actions/shifts.ts, where a worker may only claim a
shift once credentials are verified and induction is complete, enforced server-side):
  an operator is eligible for a request only if they hold the competency, the ticket is valid on every day of the job,
  they hold the client-site induction, and they are not unavailable or already allocated on those days.
An owned machine is eligible only if it is not broken down, not already allocated, and either has enough hours before
its next service, or there are enough free working days before the job starts to complete the service.

Cost basis (assumptions, stated in the report):
  owned   = (fuel + maintenance per hour) x planned hours + operator day cost x days     [marginal cost]
  hire    = wet-hire day rate x days + float in and out + fuel x planned hours          [wet hire incl. operator]
  The owned plant's fixed ownership cost is shown separately: it is incurred whether or not the machine works.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from common.report import DATA, REPORT_DATE, d, read_csv

SRC = DATA / "plant"
WEEK_START = date(2026, 11, 9)
LOW_UTILISATION = 0.40
WORKING_DAYS_8W = 40
# Tickets certify a competency; several machine sizes share one competency.
COMPETENCY = {"excavator_20t": "excavator", "excavator_8t": "excavator", "roller_12t": "roller"}


def competency(machine_type: str) -> str:
    return COMPETENCY.get(machine_type, machine_type)


@dataclass(frozen=True)
class Option:
    request_id: str
    kind: str  # OWNED | HIRE
    cost: float
    asset_id: str | None = None
    operator_id: str | None = None
    service_on: date | None = None
    days: tuple[date, ...] = ()


def workdays(start: date, n: int) -> tuple[date, ...]:
    out, day = [], start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return tuple(out)


def load() -> dict:
    return {n: read_csv(SRC / f"{n}.csv") for n in
            ("plant", "hire_rates", "usage_8_weeks", "operators", "tickets", "site_inductions", "requests_next_week")}


def operator_eligibility(op: dict, req: dict, days: tuple[date, ...], tickets: list[dict], inductions: list[dict]):
    """Return (eligible, reason). Mirrors ShiftReady's 'verified AND inducted' gate, plus expiry and availability."""
    held = [t for t in tickets if t["operator_id"] == op["operator_id"] and t["competency"] == competency(req["machine_type"])]
    if not held:
        return False, "no ticket for this machine"
    if any(d(t["expires"]) < days[-1] for t in held):
        return False, f"ticket expired {held[0]['expires']}" if d(held[0]["expires"]) < REPORT_DATE \
            else f"ticket expires {held[0]['expires']}, before job ends"
    if not any(i["operator_id"] == op["operator_id"] and i["site"] == req["site"] for i in inductions):
        return False, f"not inducted for {req['site']}"
    off = {d(x) for x in op["unavailable_dates"].split("|") if x}
    if off & set(days):
        return False, "unavailable on job dates"
    return True, "eligible"


def asset_eligibility(a: dict, req: dict, days: tuple[date, ...]):
    """Return (eligible, reason, service_date_or_None)."""
    if a["type"] != req["machine_type"]:
        return False, "wrong type", None
    if a["status"] == "breakdown" and a["unavailable_until"] and d(a["unavailable_until"]) >= days[0]:
        return False, f"breakdown until {a['unavailable_until']}", None
    hours_needed = float(req["hours_per_day"]) * len(days)
    if float(a["hours_meter"]) + hours_needed <= float(a["next_service_hours"]):
        return True, "available", None
    lead = [x for x in workdays(WEEK_START, 10) if x < days[0]]
    if len(lead) >= int(a["service_days"]):
        return True, f"service due — book service {lead[0]:%a %d %b}", lead[0]
    return False, "service due before job can finish", None


def candidate_options(data: dict) -> dict[str, list[Option]]:
    rates = {r["type"]: r for r in data["hire_rates"]}
    plant = {a["asset_id"]: a for a in data["plant"]}
    opts: dict[str, list[Option]] = {}
    for req in data["requests_next_week"]:
        days = workdays(d(req["start"]), int(req["days"]))
        hours = float(req["hours_per_day"]) * len(days)
        o: list[Option] = []
        for a in plant.values():
            ok_a, _, service_on = asset_eligibility(a, req, days)
            if not ok_a:
                continue
            for op in data["operators"]:
                ok_o, _ = operator_eligibility(op, req, days, data["tickets"], data["site_inductions"])
                if ok_o:
                    cost = (float(a["fuel_per_hour"]) + float(a["maint_per_hour"])) * hours + float(op["day_cost"]) * len(days)
                    o.append(Option(req["request_id"], "OWNED", cost, a["asset_id"], op["operator_id"], service_on, days))
        r = rates[req["machine_type"]]
        fuel = next(float(a["fuel_per_hour"]) for a in plant.values() if a["type"] == req["machine_type"])
        hire = float(r["wet_hire_per_day"]) * len(days) + 2 * float(r["float_each_way"]) + fuel * hours
        o.append(Option(req["request_id"], "HIRE", hire, days=days))
        opts[req["request_id"]] = o
    return opts


def optimise(opts: dict[str, list[Option]]) -> tuple[float, list[Option]]:
    """Exhaustive search with pruning — small enough for a weekly plan of tens of requests."""
    ids = sorted(opts, key=lambda k: len(opts[k]))  # most constrained first
    best: list = [float("inf"), []]

    def busy(chosen: list[Option], key: str, val: str, days: tuple[date, ...], service: date | None) -> bool:
        need = set(days) | ({service} if service and key == "asset_id" else set())
        for c in chosen:
            if getattr(c, key) == val:
                used = set(c.days) | ({c.service_on} if c.service_on and key == "asset_id" else set())
                if used & need:
                    return True
        return False

    def walk(i: int, chosen: list[Option], total: float) -> None:
        if total >= best[0]:
            return
        if i == len(ids):
            best[0], best[1] = total, list(chosen)
            return
        for o in sorted(opts[ids[i]], key=lambda x: x.cost):
            if o.kind == "OWNED" and (busy(chosen, "asset_id", o.asset_id, o.days, o.service_on)
                                      or busy(chosen, "operator_id", o.operator_id, o.days, None)):
                continue
            chosen.append(o)
            walk(i + 1, chosen, total + o.cost)
            chosen.pop()

    walk(0, [], 0.0)
    return best[0], sorted(best[1], key=lambda o: o.request_id)


def explain_hire(req: dict, data: dict) -> list[str]:
    """Why no owned machine/operator was used for this request (shown to the manager)."""
    days = workdays(d(req["start"]), int(req["days"]))
    notes = []
    for a in data["plant"]:
        if a["type"] == req["machine_type"]:
            ok, why, _ = asset_eligibility(a, req, days)
            notes.append(f"{a['asset_id']}: {why if not ok else 'available'}")
    for op in data["operators"]:
        if any(t["operator_id"] == op["operator_id"] and t["competency"] == competency(req["machine_type"]) for t in data["tickets"]):
            ok, why = operator_eligibility(op, req, days, data["tickets"], data["site_inductions"])
            notes.append(f"{op['name']}: {why}")
    return notes


def fleet_performance(data: dict) -> list[dict]:
    plant = {a["asset_id"]: a for a in data["plant"]}
    out = []
    for u in data["usage_8_weeks"]:
        a = plant[u["asset_id"]]
        worked, br, hrs = int(u["worked_days"]), int(u["breakdown_days"]), float(u["engine_hours"])
        revenue = float(a["internal_charge_per_day"]) * worked
        fixed = float(a["fixed_cost_per_day"]) * WORKING_DAYS_8W
        running = (float(a["fuel_per_hour"]) + float(a["maint_per_hour"])) * hrs
        out.append({"asset_id": a["asset_id"], "description": a["description"], "utilisation": worked / WORKING_DAYS_8W,
                    "breakdown_days": br, "internal_charge": revenue, "fixed_cost": fixed, "running_cost": running,
                    "contribution": revenue - fixed - running,
                    "hours_to_service": float(a["next_service_hours"]) - float(a["hours_meter"])})
    return out


def actions(data: dict, plan: list[Option], fleet: list[dict]) -> list[dict]:
    ops = {o["operator_id"]: o["name"] for o in data["operators"]}
    out = []
    for t in data["tickets"]:
        exp = d(t["expires"])
        holders = [x for x in data["tickets"] if x["competency"] == t["competency"] and d(x["expires"]) >= REPORT_DATE]
        if exp < REPORT_DATE:
            out.append({"severity": "RED", "item": f"{ops[t['operator_id']]} — {t['competency']} ticket expired {exp:%d %b}",
                        "owner": "Plant & Compliance Coordinator", "due": "this week"})
        elif exp <= REPORT_DATE + timedelta(days=30):
            sole = " — only current holder of this ticket" if len(holders) == 1 else ""
            out.append({"severity": "AMBER", "item": f"{ops[t['operator_id']]} — {t['competency']} ticket expires {exp:%d %b}{sole}",
                        "owner": "Plant & Compliance Coordinator", "due": f"before {exp:%d %b}"})
    for o in plan:
        if o.service_on:
            out.append({"severity": "AMBER", "item": f"{o.asset_id} — book service {o.service_on:%a %d %b} before {o.request_id}",
                        "owner": "Workshop Supervisor", "due": f"{o.service_on:%d %b}"})
    for f in fleet:
        if f["breakdown_days"] >= 4:
            out.append({"severity": "AMBER", "item": f"{f['asset_id']} — {f['breakdown_days']} breakdown days in 8 weeks; review reliability",
                        "owner": "Workshop Supervisor", "due": "2 weeks"})
        if f["utilisation"] < LOW_UTILISATION:
            out.append({"severity": "REVIEW", "item": f"{f['asset_id']} — {f['utilisation']:.0%} utilised over 8 weeks; "
                        "assess with 12 months of seasonal data before any hire-vs-own decision",
                        "owner": "Business Operations Director", "due": "90-day review"})
    return out


def run(data: dict | None = None) -> dict:
    data = data or load()
    opts = candidate_options(data)
    total, plan = optimise(opts)
    hire_all = sum(next(o.cost for o in v if o.kind == "HIRE") for v in opts.values())
    reqs = {r["request_id"]: r for r in data["requests_next_week"]}
    fleet = fleet_performance(data)
    return {"plan": plan, "total": total, "hire_all": hire_all, "options": opts, "requests": reqs,
            "hire_reasons": {o.request_id: explain_hire(reqs[o.request_id], data) for o in plan if o.kind == "HIRE"},
            "fleet": fleet, "actions": actions(data, plan, fleet), "data": data}


def what_if_ticket_renewed(operator_id: str, competency: str, new_expiry: str = "2027-12-31") -> float:
    """Cost of next week's plan if one lapsed ticket were current — the price of the compliance gap."""
    data = load()
    for t in data["tickets"]:
        if t["operator_id"] == operator_id and t["competency"] == competency:
            t["expires"] = new_expiry
    return run(data)["total"]
