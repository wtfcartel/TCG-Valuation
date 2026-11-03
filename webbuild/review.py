"""One-page review: the front page, laid out like a Power BI report page.

Each visual summarises one section of the plan and drills through to it. Figures come from the same engines as the
detail pages (projects, plant, seasonality); progress counts that only exist once in the role come from
data/review/tracker.csv and are set at an example day 45.
"""

from __future__ import annotations

import csv
import json
from datetime import date

from common.report import DATA, REPORT_DATE, esc
from demo1_project_control.engine import RULE_LABEL, run as run_projects
from demo4_seasonality.engine import run as run_season

BLUE, ORANGE = "#2a78d6", "#eb6834"
STATUS = {"GREEN": ("On track", "✓", "#0ca30c"), "AMBER": ("Action needed", "!", "#b87700"),
          "RED": ("At risk", "✕", "#d03b3b"), "GREY": ("Not due yet", "○", "#7a8580")}


def chip(status: str, text: str | None = None) -> str:
    label, icon, colour = STATUS[status]
    return (f"<span class='chip' style='--c:{colour}'><b>{icon}</b>{esc(text or label)}</span>")


def money_m(v: float) -> str:
    return f"${v / 1e6:,.2f}m" if v >= 1e6 else f"${v / 1000:,.0f}k"


def pct(v: float, dp: int = 1) -> str:
    return f"{v * 100:.{dp}f}%"


def tracker() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    with (DATA / "review" / "tracker.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["group"], []).append({"item": r["item"], "done": int(r["done"]), "planned": int(r["planned"])})
    return out


def tickets() -> dict:
    with (DATA / "plant" / "tickets.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    expired = [r for r in rows if date.fromisoformat(r["expires"]) < REPORT_DATE]
    soon = [r for r in rows if 0 <= (date.fromisoformat(r["expires"]) - REPORT_DATE).days <= 30]
    return {"total": len(rows), "expired": len(expired), "soon": len(soon)}


def visual(title: str, href: str, body: str, cls: str = "") -> str:
    return (f"<section class='vis {cls}'><header><h3>{esc(title)}</h3><a href='{href}' class='drill' "
            f"title='Drill through to the detail'>Details ↗</a></header>{body}</section>")


def bars(rows: list[dict]) -> str:
    out = ""
    for r in rows:
        share = r["done"] / r["planned"] if r["planned"] else 0
        out += (f"<div class='pb' data-tip='{esc(r['item'])}: {r['done']} of {r['planned']}'><span>{esc(r['item'])}</span>"
                f"<i><em style='width:{share * 100:.0f}%'></em></i><b>{r['done']}/{r['planned']}</b></div>")
    return out


def build() -> str:
    proj = run_projects()
    season = run_season()
    trk = tracker()
    tk = tickets()
    results = proj["results"]
    port = proj["portfolio"]
    pipeline = sum(r.revised_revenue for r in results)
    weighted_complete = sum(r.revised_revenue * float(r.p["pct_complete"]) for r in results) / pipeline
    slipping = [r for r in results if r.slip_days > 0]
    stale = [r for r in results if r.stale]
    counts = port["counts"]

    # Priority status, calculated where the data allows
    prio = [
        ("1", "Deliver the existing pipeline of mandates", "RED" if len(slipping) > 1 else "AMBER" if slipping else "GREEN",
         f"{len(slipping)} job slipping" if slipping else None),
        ("1", "Keep every live site safe and compliant", "RED" if tk["expired"] else "GREEN",
         f"{tk['expired']} expired ticket" if tk["expired"] else None),
        ("2", "Protect margin and cash on committed work",
         "AMBER" if port["forecast_gm_pct"] < port["quoted_gm_pct"] or port["under_billed"] > 0 else "GREEN",
         f"{money_m(port['under_billed'])} not invoiced"),
        ("2", "Light weekly rhythm to support delivery", "GREEN", None),
        ("3", "Prepare the next stage, without starting it", "GREY", "From day 61"),
    ]
    prio_html = "".join(f"<div class='row'><span class='lv L{lv}'>Level {lv}</span><span class='t'>{esc(t)}</span>"
                        f"{chip(s, note)}</div>" for lv, t, s, note in prio)

    # Pipeline table
    rag = {"RED": "RED", "AMBER": "AMBER", "GREEN": "GREEN", "NOT REPORTED": "GREY"}
    rows = ""
    for r in sorted(results, key=lambda r: -r.revised_revenue):
        fm = "No cost data" if r.stale else pct(r.forecast_margin)
        rows += (f"<tr data-tip='{esc(r.p['name'])}: {pct(float(r.p['pct_complete']), 0)} complete, quoted margin "
                 f"{pct(r.quoted_margin)}, forecast {fm}'><td>{esc(r.p['name'])}</td><td class='n'>{money_m(r.revised_revenue)}</td>"
                 f"<td><i class='mini'><em style='width:{float(r.p['pct_complete']) * 100:.0f}%'></em></i></td>"
                 f"<td class='n'>{pct(r.quoted_margin)}</td><td class='n'>{fm}</td>"
                 f"<td>{chip(rag[r.rag], 'No data' if r.rag == 'NOT REPORTED' else None)}</td></tr>")
    pipeline_html = (f"<table class='pt'><tr><th>Job</th><th class='n'>Value</th><th>Complete</th><th class='n'>Quoted</th>"
                     f"<th class='n'>Forecast</th><th>Status</th></tr>{rows}</table>")

    # Exceptions by type
    by_type: dict[str, dict[str, int]] = {}
    for e in proj["exceptions"]:
        by_type.setdefault(RULE_LABEL[e.rule], {}).setdefault(e.severity, 0)
        by_type[RULE_LABEL[e.rule]][e.severity] += 1
    exc = ""
    sev_colour = {"RED": "#d03b3b", "AMBER": "#e0a100", "NOT REPORTED": "#9aa39d"}
    for label, sev in sorted(by_type.items(), key=lambda kv: -sum(kv[1].values())):
        segs = "".join(f"<em style='width:{n * 34}px;background:{sev_colour[s]}' title='{s}'></em>" for s, n in sev.items())
        exc += (f"<div class='eb' data-tip='{esc(label)}: "
                f"{', '.join(f'{n} {s.lower()}' for s, n in sev.items())}'><span>{esc(label)}</span><i>{segs}</i>"
                f"<b>{sum(sev.values())}</b></div>")
    wins = trk.get("win", [])
    wins_done = sum(1 for w in wins if w["done"] >= w["planned"])

    meet = trk.get("meet", [])
    meet_html = "".join(f"<div class='row'><span class='t'>{esc(m['item'])}</span><b class='n'>{m['done']} of {m['planned']}</b>"
                        f"{chip('GREEN' if m['done'] >= m['planned'] else 'AMBER', 'Held' if m['done'] >= m['planned'] else 'Behind')}</div>"
                        for m in meet)

    # Leadership: day-90 measures
    lead = [
        ("Pipeline delivered or on an agreed path", "AMBER" if slipping else "GREEN",
         f"{pct(weighted_complete, 0)} complete by value"),
        ("No disruption to crews or office", "GREEN", "No changes to how crews work"),
        ("Milestones invoiced as completed", "AMBER" if port["under_billed"] > 0 else "GREEN",
         f"{money_m(port['under_billed'])} still to invoice"),
        ("Next-stage options agreed", "GREY", "Due at day 90"),
    ]
    lead_html = "".join(f"<div class='row'><span class='t'>{esc(t)}</span>{chip(s, n)}</div>" for t, s, n in lead)

    # Assumptions
    assume = [(a["item"], "GREEN" if a["done"] else "GREY", "Confirmed" if a["done"] else "Testing") for a in trk.get("assume", [])]
    assume.insert(2, ("Job cost and cash data sits partly in spreadsheets", "AMBER" if stale else "GREEN",
                      f"Cost data stale on {len(stale)} job" if stale else "Confirmed"))
    assume.append(("Tickets and inductions current on live sites", "RED" if tk["expired"] else "GREEN",
                   f"{tk['expired']} expired, {tk['soon']} due within 30 days"))
    assume_html = "".join(f"<div class='row'><span class='t'>{esc(t)}</span>{chip(s, n)}</div>" for t, s, n in assume)

    # Season data for the slicer
    biz = season["business"]
    ic = {m: sum(x["invested_capital"] for x in season["monthly"] if x["month"] == m) for m in season["months"]}
    season_json = json.dumps([{"m": b["month"], "s": b["season"], "nopat": b["nopat"], "ic": ic[b["month"]],
                               "util": b["utilisation"], "ot": b["on_time"]} for b in biz])
    hi, lo = 0.5, -0.3
    cols = ""
    for i, b in enumerate(biz):
        v = b["roic_annualised"]
        h = abs(v) / (hi - lo) * 120
        top = (hi / (hi - lo)) * 120 - (h if v >= 0 else 0)
        cols += (f"<g class='mcol' data-season='{esc(b['season'])}' data-tip='{b['month']} ({esc(b['season'])}): ROIC "
                 f"{pct(v)}, utilisation {pct(b['utilisation'], 0)}, on-time {pct(b['on_time'], 0)}'>"
                 f"<rect x='{i * 30 + 4}' y='0' width='26' height='140' fill='transparent'/>"
                 f"<rect class='bar' x='{i * 30 + 7}' y='{top + 4:.1f}' width='20' height='{max(h, 1):.1f}' rx='3' "
                 f"fill='{BLUE if v >= 0 else '#d03b3b'}'/><text x='{i * 30 + 17}' y='138' text-anchor='middle'>{b['month'][0]}"
                 f"</text></g>")
    zero = (hi / (hi - lo)) * 120 + 4
    season_svg = (f"<svg viewBox='0 0 364 142' class='minichart' role='img' aria-label='ROIC by month'>"
                  f"<line x1='0' x2='364' y1='{zero:.1f}' y2='{zero:.1f}' stroke='#8a8886'/>{cols}</svg>")
    seasons = []
    for b in biz:
        if b["season"] not in seasons:
            seasons.append(b["season"])
    slicer = "".join(f"<button type='button' data-s='{esc(s)}'>{esc(s.replace(' (assumed)', ''))}</button>" for s in seasons)

    kpis = [
        ("Committed pipeline", money_m(pipeline), f"{len(results)} jobs, {pct(weighted_complete, 0)} complete by value"),
        ("Forecast margin", pct(port["forecast_gm_pct"]), f"against {pct(port['quoted_gm_pct'])} quoted"),
        ("Not yet invoiced", money_m(port["under_billed"]), "work done, not billed"),
        ("Open exceptions", str(sum(counts.values())), f"{counts.get('RED', 0)} at risk, {counts.get('AMBER', 0)} to action"),
        ("Ticket compliance", f"{(tk['total'] - tk['expired']) / tk['total'] * 100:.0f}%",
         f"{tk['expired']} expired, {tk['soon']} due in 30 days"),
        ("Business ROIC", pct(season["business_roic"]), "<span id='roicSel'>full year</span>"),
    ]
    kpi_html = "".join(f"<div class='kcard'><span>{esc(l)}</span><b>{v}</b><small>{s}</small></div>" for l, v, s in kpis)

    tabs = [("index.html", "One-page review"), ("approach.html", "Approach"), ("plan-1.html", "1 Get to know"),
            ("plan-2.html", "2 Priorities"), ("plan-3.html", "3 Partnering"), ("plan-4.html", "4 Risks"),
            ("plan-5.html", "5 Leadership"), ("season.html", "Season"), ("assumptions.html", "Assumptions")]
    tab_html = "".join(f"<a href='/{u}'{' class=\"on\"' if u == 'index.html' else ''}>{t}</a>" for u, t in tabs)

    return f"""<style>{CSS}</style>
<div class="report">
<div class="rhead"><div><b>Green Turf | 90-Day Plan</b><span>One-page review | example at day 45</span></div>
<div class="slicer" role="group" aria-label="Season filter"><span>Season</span><button type="button" data-s="" class="on">All</button>{slicer}</div></div>
<div class="canvas">
<div class="kpis">{kpi_html}</div>
{visual("Committed pipeline: progress and margin", "/plan-2.html", pipeline_html, "w7")}
{visual("Priorities", "/plan-2.html", prio_html, "w5")}
{visual("Getting to know the business (first 30 days)", "/plan-1.html", bars(trk.get("know", [])), "w4")}
{visual("Working with Mick and Dean", "/plan-3.html", meet_html, "w4")}
{visual("Open exceptions by type", "/plan-4.html", exc + f"<p class='foot'>Quick wins done: <b>{wins_done} of {len(wins)}</b></p>", "w4")}
{visual("Season: ROIC by month", "/season.html", season_svg + "<p class='foot' id='seasonFoot'></p>", "w4")}
{visual("Day-90 measures", "/plan-5.html", lead_html, "w4")}
{visual("Assumptions", "/assumptions.html", assume_html, "w4")}
</div>
<nav class="tabs" aria-label="Report pages">{tab_html}</nav>
</div>
<p class="note">Illustrative figures throughout. Job, margin, invoicing, exception, ticket and season figures are
calculated from sample data; meeting and progress counts are set at an example day 45. Laid out as a Power BI report
page, with each visual linking through to the detail.</p>
<div id="tip" role="tooltip"></div>
<script>
(() => {{
  const data = {season_json};
  const fmt = v => (v * 100).toFixed(1) + '%';
  const tip = document.getElementById('tip');
  document.querySelectorAll('[data-tip]').forEach(el => {{
    el.addEventListener('mousemove', e => {{ tip.textContent = el.dataset.tip; tip.style.display = 'block';
      tip.style.left = Math.min(e.clientX + 14, innerWidth - 310) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; }});
    el.addEventListener('mouseleave', () => tip.style.display = 'none');
  }});
  const apply = s => {{
    document.querySelectorAll('.slicer button').forEach(b => b.classList.toggle('on', b.dataset.s === s));
    document.querySelectorAll('.mcol').forEach(g => g.classList.toggle('dim', !!s && g.dataset.season !== s));
    const rows = s ? data.filter(d => d.s === s) : data;
    const avg = k => rows.reduce((a, d) => a + d[k], 0) / rows.length;
    const roic = avg('nopat') * 12 / avg('ic');   /* NOPAT annualised over average invested capital */
    document.getElementById('seasonFoot').innerHTML = (s ? s : 'Full year') + ': ROIC <b>' + fmt(roic) +
      '</b>, utilisation <b>' + fmt(avg('util')) + '</b>, on-time <b>' + fmt(avg('ot')) + '</b>';
    document.getElementById('roicSel').textContent = s ? s.toLowerCase() + ': ' + fmt(roic) + ' annualised' : 'full year';
  }};
  document.querySelectorAll('.slicer button').forEach(b => b.addEventListener('click', () => apply(b.dataset.s)));
  apply('');
}})();
</script>"""


CSS = """
.report{background:#eef0ee;border:1px solid #d6dbd5;border-radius:12px;overflow:hidden;margin:6px 0 10px;
  font-family:"Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;box-shadow:0 8px 24px -16px rgba(20,60,30,.35)}
.rhead{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;background:#0f5f2b;color:#fff;
  padding:10px 16px}
.rhead b{font-size:16px;display:block}.rhead span{font-size:12px;opacity:.85}
.slicer{display:flex;gap:4px;flex-wrap:wrap;align-items:center}.slicer span{font-size:11px;text-transform:uppercase;
  letter-spacing:.06em;margin-right:4px;opacity:.85}
.slicer button{all:unset;cursor:pointer;font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid rgba(255,255,255,.45);
  color:#fff}.slicer button.on{background:#fff;color:#0f5f2b;border-color:#fff}
.slicer button:focus-visible{outline:2px solid #fff;outline-offset:2px}
.canvas{display:grid;grid-template-columns:repeat(12,1fr);gap:10px;padding:12px}
.kpis{grid-column:span 12;display:grid;grid-template-columns:repeat(6,1fr);gap:10px}
.kcard{background:#fff;border:1px solid #e1dfdd;border-radius:6px;padding:10px 12px;border-top:3px solid #1fb43e}
.kcard span{display:block;font-size:11.5px;color:#605e5c}.kcard b{display:block;font-size:24px;color:#252423;line-height:1.2;
  margin:2px 0}.kcard small{font-size:11.5px;color:#605e5c}
.vis{background:#fff;border:1px solid #e1dfdd;border-radius:6px;padding:10px 12px;min-width:0}
.vis header{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
.vis h3{font-size:13px;font-weight:600;color:#252423;margin:0}
.drill{font-size:11.5px;color:#0a6aa1;text-decoration:none;white-space:nowrap}.drill:hover{text-decoration:underline}
.w7{grid-column:span 7}.w5{grid-column:span 5}.w4{grid-column:span 4}
.pt{border:0;font-size:12px;box-shadow:none}.pt th{background:#f3f2f1;font-size:11px;padding:5px 6px}.pt td{padding:5px 6px}
.mini{display:inline-block;width:70px;height:8px;background:#e8ebe7;border-radius:4px;overflow:hidden;vertical-align:middle}
.mini em{display:block;height:100%;background:#2a78d6}
.row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #f0f0ee;font-size:12.5px}
.row:last-child{border-bottom:0}.row .t{flex:1;min-width:0}.row .n{font-variant-numeric:tabular-nums;white-space:nowrap}
.chip{display:inline-flex;gap:4px;align-items:center;font-size:11px;font-weight:600;color:#252423;white-space:nowrap;
  padding:1px 8px 1px 2px;border-radius:999px;background:color-mix(in srgb,var(--c) 12%,#fff)}
.chip b{display:inline-grid;place-items:center;width:15px;height:15px;border-radius:50%;background:var(--c);color:#fff;
  font-size:10px}
.pb{display:grid;grid-template-columns:1fr 80px 44px;gap:8px;align-items:center;font-size:12.5px;padding:5px 0}
.pb i{height:8px;background:#e8ebe7;border-radius:4px;overflow:hidden}.pb em{display:block;height:100%;background:#2a78d6;
  border-radius:4px}.pb b{text-align:right;font-variant-numeric:tabular-nums}
.eb{display:grid;grid-template-columns:1fr auto 20px;gap:8px;align-items:center;font-size:12.5px;padding:4px 0}
.eb i{display:flex;gap:2px}.eb em{display:block;height:12px;border-radius:3px}.eb b{text-align:right}
.foot{font-size:12px;color:#605e5c;margin:8px 0 0}
.minichart{width:100%;height:auto}.minichart text{font-size:10px;fill:#605e5c}
.mcol .bar{transition:opacity .15s}.mcol.dim .bar{opacity:.18}
.tabs{display:flex;gap:2px;flex-wrap:wrap;background:#f3f2f1;border-top:1px solid #e1dfdd;padding:4px 8px 0}
.tabs a{font-size:12px;padding:6px 12px;color:#252423;text-decoration:none;border-bottom:3px solid transparent}
.tabs a:hover{background:#e8ebe7}.tabs a.on{border-bottom-color:#1fb43e;font-weight:600;background:#fff}
#tip{position:fixed;pointer-events:none;background:#252423;color:#fff;font-size:12px;padding:6px 9px;border-radius:4px;
  display:none;z-index:20;max-width:300px}
@media(max-width:1000px){.kpis{grid-template-columns:repeat(3,1fr)}.w7,.w5,.w4{grid-column:span 12}}
@media(max-width:560px){.kpis{grid-template-columns:repeat(2,1fr)}.pt td:nth-child(3),.pt th:nth-child(3),.pt td:nth-child(4),.pt th:nth-child(4){display:none}.pt .chip{white-space:normal}}
"""
