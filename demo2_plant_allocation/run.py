"""Run Demo 2 and write output/plant_allocation.html and output/plant_allocation.json.

    python -m demo2_plant_allocation.run
"""

from __future__ import annotations

import json

from common.report import OUTPUT, esc, money, page
from demo2_plant_allocation.engine import WEEK_START, run, what_if_ticket_renewed


def render(res: dict) -> str:
    data, plan, reqs = res["data"], res["plan"], res["requests"]
    ops = {o["operator_id"]: o["name"] for o in data["operators"]}
    renewed = what_if_ticket_renewed("OP-01", "excavator")
    owned = [o for o in plan if o.kind == "OWNED"]
    kpis = f"""<div class="grid k4">
<div class="card kpi"><div class="l">Machine requests, week of {WEEK_START:%d %b}</div><div class="v">{len(plan)}</div>
<div class="s">{len(owned)} met from owned fleet · {len(plan) - len(owned)} external hire</div></div>
<div class="card kpi"><div class="l">Lowest-cost feasible plan</div><div class="v">{money(res['total'])}</div>
<div class="s">vs {money(res['hire_all'])} if every request were hired</div></div>
<div class="card kpi"><div class="l">Cost of one lapsed ticket</div><div class="v">{money(res['total'] - renewed)}</div>
<div class="s">this week, if Mark Delaney's excavator ticket were current</div></div>
<div class="card kpi"><div class="l">Compliance and fleet actions</div><div class="v">{len(res['actions'])}</div>
<div class="s">each with an owner and due date</div></div></div>"""
    rows = ""
    for o in plan:
        q = reqs[o.request_id]
        alt = next(x.cost for x in res["options"][o.request_id] if x.kind == "HIRE")
        if o.kind == "OWNED":
            how = f"<b>{esc(o.asset_id)}</b> + {esc(ops[o.operator_id])}" + (
                f"<br><span class='note'>service booked {o.service_on:%a %d %b} first</span>" if o.service_on else "")
            why = f"Owned plant {money(alt - o.cost)} cheaper than wet hire ({money(alt)})"
        else:
            how = "<b>External wet hire</b>"
            notes = []
            for x in res["hire_reasons"][o.request_id]:
                who, _, why = x.partition(": ")
                clash = why in ("available", "eligible") and next((p for p in owned if set(p.days) & set(o.days) and
                              (p.asset_id == who or ops.get(p.operator_id) == who)), None)
                if clash:
                    notes.append(f"{who}: allocated to {clash.request_id}" +
                                 (" (only current grader operator)" if clash.request_id == "R4" else ""))
                elif why != "available" or not any(p.asset_id == who for p in owned):
                    notes.append(x if why != "eligible" else f"{who}: eligible but unavailable")
            if any(n.endswith(": available") for n in notes):
                notes = [n.replace(": available", ": available, but no eligible operator") for n in notes]
            why = "<br>".join(esc(n) for n in notes)
        rows += (f"<tr><td>{esc(o.request_id)}</td><td>{esc(q['project_id'])}<br><span class='note'>{esc(q['site'])}</span></td>"
                 f"<td>{esc(q['machine_type'].replace('_', ' '))}</td><td>{o.days[0]:%a %d}–{o.days[-1]:%a %d %b}</td>"
                 f"<td>{how}</td><td class='n'>{money(o.cost)}</td><td class='note'>{why}</td></tr>")
    plan_t = f"""<h2>Recommended allocation — next week</h2><table><tr><th>Req.</th><th>Project</th><th>Machine</th><th>Dates</th>
<th>Allocation</th><th class='n'>Cost</th><th>Reason</th></tr>{rows}</table>
<p class="note">An operator is only allocated if they hold a current ticket for the machine, the client-site induction, and are
available. Owned cost = fuel + maintenance per engine hour + operator day rate. Hire = wet-hire rate + floats + fuel.
Fixed ownership costs are excluded from the comparison because they are incurred whether or not the machine works.</p>"""
    frows = "".join(
        f"<tr><td><b>{esc(f['asset_id'])}</b> {esc(f['description'])}</td><td class='n'>{f['utilisation']:.0%}</td>"
        f"<td class='n'>{f['breakdown_days']}</td><td class='n'>{money(f['internal_charge'])}</td>"
        f"<td class='n'>{money(f['fixed_cost'] + f['running_cost'])}</td><td class='n'>{money(f['contribution'])}</td>"
        f"<td class='n'>{f['hours_to_service']:.0f}</td></tr>" for f in res["fleet"])
    fleet = f"""<h2>Fleet contribution — last 8 weeks</h2><table><tr><th>Asset</th><th class='n'>Utilisation</th>
<th class='n'>Breakdown days</th><th class='n'>Charged to projects</th><th class='n'>Ownership + running cost</th>
<th class='n'>Contribution</th><th class='n'>Hours to service</th></tr>{frows}</table>"""
    arows = "".join(f"<tr><td><span class='pill {'GREY' if a['severity'] == 'REVIEW' else a['severity']}'>{esc(a['severity'])}</span></td>"
                    f"<td>{esc(a['item'])}</td><td>{esc(a['owner'])}</td><td>{esc(a['due'])}</td></tr>" for a in res["actions"])
    acts = f"<h2>Actions generated</h2><table><tr><th></th><th>Item</th><th>Owner</th><th>Due</th></tr>{arows}</table>"
    return page("Plant & Operator Allocation", "Demo 2 · owned fleet vs external hire, gated by operator competency",
                kpis + plan_t + acts + fleet)


def main() -> dict:
    res = run()
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "plant_allocation.html").write_text(render(res), encoding="utf-8")
    (OUTPUT / "plant_allocation.json").write_text(json.dumps({
        "plan": [{"request": o.request_id, "kind": o.kind, "asset": o.asset_id, "operator": o.operator_id,
                  "service_on": o.service_on, "cost": round(o.cost, 2)} for o in res["plan"]],
        "total": res["total"], "all_hire": res["hire_all"], "actions": res["actions"], "fleet": res["fleet"]},
        indent=2, default=str), encoding="utf-8")
    print(f"Demo 2: plan {money(res['total'])} vs all-hire {money(res['hire_all'])}; "
          f"{sum(o.kind == 'OWNED' for o in res['plan'])}/{len(res['plan'])} owned; {len(res['actions'])} actions")
    return res


if __name__ == "__main__":
    main()
