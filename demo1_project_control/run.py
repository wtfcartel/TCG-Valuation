"""Run Demo 1 and write output/project_control.html, output/project_control.json and output/action_log.jsonl.

    python -m demo1_project_control.run      (from the showcase folder)
"""

from __future__ import annotations

import json
from datetime import date

from common.report import OUTPUT, esc, money, page, pct, verify_chain
from demo1_project_control.engine import RULE_LABEL, RULES, run


def _svg_history(hist: list[dict], quoted: float) -> str:
    W, H, L, R, T, B = 560, 250, 46, 36, 34, 34
    lo, hi = 0.10, 0.23
    xs = [L + i * (W - L - R) / (len(hist) - 1) for i in range(len(hist))]
    y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)  # noqa: E731
    col = {"GREEN": "#2f6b3f", "AMBER": "#a5640c", "RED": "#a8322d"}
    parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Forecast margin by month">']
    for v in (0.12, 0.16, 0.20):
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="#e4e7e2"/>'
                     f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end" font-size="11" fill="#5d6b62">{v:.0%}</text>')
    for lx, (v, lab, c) in zip((L, L + 165, L + 320), ((quoted, "Quoted margin", "#1d2a22"), (quoted - RULES["FADE_AMBER"], "Amber trigger", "#a5640c"),
                      (quoted - RULES["FADE_RED"], "Red trigger", "#a8322d"))):
        parts.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{c}" stroke-dasharray="4 4"/>'
                     f'<line x1="{lx:.0f}" x2="{lx + 22:.0f}" y1="12" y2="12" stroke="{c}" stroke-dasharray="4 4"/>'
                     f'<text x="{lx + 27:.0f}" y="16" font-size="11" fill="{c}">{lab} {v:.0%}</text>')
    pts = " ".join(f"{x:.1f},{y(h['forecast_margin']):.1f}" for x, h in zip(xs, hist))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="#33433a" stroke-width="2"/>')
    for x, h in zip(xs, hist):
        m = date.fromisoformat(h["month_end"]).strftime("%b")
        parts.append(f'<circle cx="{x:.1f}" cy="{y(h["forecast_margin"]):.1f}" r="5.5" fill="{col[h["flag"]]}"/>'
                     f'<text x="{x:.1f}" y="{y(h["forecast_margin"]) + (20 if h is hist[-1] else -10):.1f}" text-anchor="middle" font-size="11.5" '
                     f'font-weight="600" fill="{col[h["flag"]]}">{h["forecast_margin"]:.1%}</text>'
                     f'<text x="{x:.1f}" y="{H - 16}" text-anchor="middle" font-size="11.5" fill="#33433a">{m}</text>'
                     f'<text x="{x:.1f}" y="{H - 3}" text-anchor="middle" font-size="10.5" fill="#5d6b62">'
                     f'{h["pct_complete"]:.0%} done</text>')
    parts.append("</svg>")
    return "".join(parts)


def render(res: dict) -> str:
    pf, excs, status, results = res["portfolio"], res["exceptions"], res["status"], res["results"]
    c = pf["counts"]
    ok, bad = verify_chain(res["log"])
    over60 = pf["ageing"]["61-90"] + pf["ageing"]["90+"]

    kpis = f"""<div class="grid k4">
<div class="card kpi"><div class="l">Contract value (reporting projects)</div><div class="v">{money(pf['revised_revenue'])}</div>
<div class="s">{pf['projects'] - len(pf['excluded_stale'])} of {pf['projects']} projects · {', '.join(pf['excluded_stale']) or 'none'} not reported</div></div>
<div class="card kpi"><div class="l">Forecast gross margin</div><div class="v">{pct(pf['forecast_gm_pct'])}</div>
<div class="s">vs {pct(pf['quoted_gm_pct'])} at quote · {money(pf['forecast_gm'] - pf['quoted_gm'], True)}</div></div>
<div class="card kpi"><div class="l">Work done, not invoiced</div><div class="v">{money(pf['under_billed'])}</div>
<div class="s">earned value less invoices issued</div></div>
<div class="card kpi"><div class="l">Open exceptions</div><div class="v">{c['RED']} red · {c['AMBER']} amber</div>
<div class="s">{c['NOT REPORTED']} not reported · debtors &gt;60 days {money(over60)}</div></div></div>"""

    rows = "".join(
        f"<tr><td><span class='pill {'GREY' if e.severity == 'NOT REPORTED' else e.severity}'>{esc(e.severity)}</span></td>"
        f"<td>{esc(e.project_id)}</td><td><b>{esc(RULE_LABEL[e.rule])}</b><br><span class='note'>{esc(e.finding)}</span></td>"
        f"<td>{esc(e.owner)}</td><td>{esc(e.escalate_to or '—')}</td><td>{e.due:%a %d %b}</td>"
        f"<td>{esc(status.get(e.key, 'RAISED').title())}</td></tr>" for e in excs)
    register = f"""<h2>Exceptions register — what needs a decision, and who owns it</h2>
<table><tr><th>Severity</th><th>Project</th><th>Issue</th><th>Owner</th><th>Escalate to</th><th>Due</th><th>Status</th></tr>{rows}</table>"""

    prow = ""
    for r in results:
        p, st = r.p, r.stale
        rag = "GREY" if st else r.rag
        prow += (f"<tr><td><b>{esc(p['project_id'])}</b> {esc(p['name'])}<br><span class='note'>{esc(p['scope'])}</span></td>"
                 f"<td>{esc(p['project_manager'])}</td><td class='n'>{money(r.revised_revenue)}</td>"
                 f"<td class='n'>{float(p['pct_complete']):.0%}</td>"
                 f"<td class='n'>{'—' if st else f'{r.cpi:.2f}'}</td><td class='n'>{pct(r.quoted_margin)}</td>"
                 f"<td class='n'>{'not reported' if st else pct(r.forecast_margin)}</td>"
                 f"<td class='n'>{'—' if st else f'{-r.fade * 100:+.1f} pts'}</td>"
                 f"<td class='n'>{money(max(r.under_billed, 0))}</td><td class='n'>{r.slip_days}d</td>"
                 f"<td><span class='pill {rag}'>{esc(r.rag)}</span></td></tr>")
    projects = f"""<h2>Project position — quote to completion</h2>
<table><tr><th>Project</th><th>PM</th><th class='n'>Contract (incl. approved var.)</th><th class='n'>Complete</th>
<th class='n'>CPI</th><th class='n'>Quoted margin</th><th class='n'>Forecast margin</th><th class='n'>Margin movement</th>
<th class='n'>Not invoiced</th><th class='n'>Slip</th><th>Status</th></tr>{prow}</table>
<p class="note">CPI = earned value ÷ actual cost. Below 1.00 means work is costing more than budgeted for the progress achieved.</p>"""

    hist = res["history"]
    first = next(h for h in hist if h["flag"] != "GREEN")
    last = hist[-1]
    p101 = next(r for r in results if r.p["project_id"] == "P-101")
    early = f"""<h2>Early warning — would we have seen it in time? (P-101, monthly history)</h2>
<div class="grid k2"><div class="card">{_svg_history(hist, p101.quoted_margin)}</div>
<div class="card"><h3>What the numbers say</h3>
<p>The amber trigger trips at the <b>{date.fromisoformat(first['month_end']):%B} month-end</b>, when the project is
<b>{first['pct_complete']:.0%} complete</b> and <b>{first['budget_remaining_share']:.0%} of the budget is still unspent</b>
— enough remaining cost to act on. By {date.fromisoformat(last['month_end']):%B} the forecast margin is
{last['forecast_margin']:.1%} against {p101.quoted_margin:.0%} quoted.</p>
<p>Two drivers are visible in the source data: plant hire is {next(c for c in p101.categories if c['category'] == 'Plant hire')['over_share']:.0%} over its budget once
commitments are included, and a ${p101.pending_var_revenue:,.0f} subgrade variation has been worked but not approved.
If that variation is approved in full, forecast margin moves to
<b>{pct(p101.forecast_margin_if_pending_approved)}</b>.</p>
<p class="note">Management action generated: variation submission escalated (Commercial Manager), plant-hire review against
owned-fleet availability (see Demo 2), recovery plan from the PM within 2 business days.</p></div></div>"""

    ag = pf["ageing"]
    mx = max(ag.values()) or 1
    bars = "".join(f"<tr><td>{k} days</td><td class='n'>{money(v)}</td><td style='width:55%'><div style='height:12px;"
                   f"background:{'#a8322d' if k in ('61-90', '90+') else '#7a9a82'};width:{v / mx * 100:.0f}%'></div></td></tr>"
                   for k, v in ag.items())
    log_rows = "".join(f"<tr><td>{esc(e['date'])}</td><td>{esc(e['exception_key'])}</td><td>{esc(e['event'])}</td>"
                       f"<td>{esc(e['by'])}</td><td class='mono'>{esc(e['hash'][:12])}…</td></tr>" for e in res["log"][-6:])
    lower = f"""<div class="grid k2" style="margin-top:6px"><div><h2>Debtor ageing (unpaid invoices)</h2><table>{bars}</table></div>
<div><h2>Action trail — latest entries</h2><table><tr><th>Date</th><th>Exception</th><th>Event</th><th>By</th><th>Hash</th></tr>{log_rows}</table>
<p class="note">{len(res['log'])} entries, each sealed with the previous entry's hash. Integrity check:
<b>{'PASSED' if ok else f'FAILED at entry {bad}'}</b>. Editing any past entry breaks the chain.</p></div></div>"""

    rules = "".join(f"<tr><td class='mono'>{k}</td><td class='n'>{v}</td></tr>" for k, v in RULES.items())
    method = f"""<h2>Trigger thresholds (to be agreed with management)</h2><table style="max-width:420px">{rules}</table>"""
    return page("Project Control & Margin Early-Warning",
                "Demo 1 · quote → delivery → invoicing, with exceptions routed to an accountable owner",
                kpis + register + early + projects + lower + method)


def main() -> dict:
    res = run()
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "project_control.html").write_text(render(res), encoding="utf-8")
    with (OUTPUT / "action_log.jsonl").open("w", encoding="utf-8") as f:
        for e in res["log"]:
            f.write(json.dumps(e) + "\n")
    summary = {
        "portfolio": res["portfolio"],
        "exceptions": [{"key": e.key, "severity": e.severity, "finding": e.finding, "owner": e.owner,
                        "escalate_to": e.escalate_to, "due": e.due.isoformat()} for e in res["exceptions"]],
        "p101_history": res["history"],
    }
    (OUTPUT / "project_control.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    pf = res["portfolio"]
    print(f"Demo 1: {len(res['results'])} projects, {len(res['exceptions'])} exceptions "
          f"({pf['counts']}); forecast GM {pf['forecast_gm_pct']:.1%} vs quoted {pf['quoted_gm_pct']:.1%}; "
          f"action log {len(res['log'])} entries, chain ok={verify_chain(res['log'])[0]}")
    return res


if __name__ == "__main__":
    main()
