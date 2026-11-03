"""One-page review: the front page, laid out like a Power BI report.

One canvas, one main chart and a side panel per tab, with report page tabs along the bottom. Charts use Chart.js
(MIT, vendored). Every figure comes from the same engines as the detail pages, so the two always agree:
  ROIC and service efficiency   demo4_seasonality
  customers, pipeline, cash     demo1_project_control (+ data/projects/customers.csv)
  plant and compliance          demo2_plant_allocation
"""

from __future__ import annotations

import csv
import json
from datetime import date

from common.report import DATA, REPORT_DATE, esc
from demo1_project_control.engine import run as run_projects
from demo2_plant_allocation.engine import run as run_plant
from demo4_seasonality.engine import run as run_season


def _customers() -> dict[str, str]:
    with (DATA / "projects" / "customers.csv").open(newline="", encoding="utf-8") as f:
        return {r["project_id"]: r["customer"] for r in csv.DictReader(f)}


def _tickets() -> dict:
    with (DATA / "plant" / "tickets.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    expired = sum(1 for r in rows if date.fromisoformat(r["expires"]) < REPORT_DATE)
    soon = sum(1 for r in rows if 0 <= (date.fromisoformat(r["expires"]) - REPORT_DATE).days <= 30)
    return {"total": len(rows), "expired": expired, "soon": soon}


def data() -> dict:
    season = run_season()
    proj = run_projects()
    plant = run_plant()
    cust = _customers()

    ic = {m: sum(x["invested_capital"] for x in season["monthly"] if x["month"] == m) for m in season["months"]}
    months = [{"m": b["month"], "s": b["season"], "nopat": b["nopat"], "ic": ic[b["month"]], "rev": b["revenue"],
               "util": b["utilisation"], "ot": b["on_time"]} for b in season["business"]]
    units = {u: [{"m": x["month"], "s": x["season"], "nopat": x["nopat"], "ic": x["invested_capital"]}
                 for x in season["monthly"] if x["unit"] == u] for u in season["units"]}

    jobs = []
    for r in proj["results"]:
        margin_pct = r.quoted_margin if r.stale else r.forecast_margin
        jobs.append({"id": r.p["project_id"], "job": r.p["name"], "customer": cust.get(r.p["project_id"], r.p["name"]),
                     "type": r.p["client_type"], "value": r.revised_revenue, "complete": float(r.p["pct_complete"]),
                     "quoted": r.quoted_margin, "margin_pct": margin_pct, "margin": r.revised_revenue * margin_pct,
                     "stale": r.stale, "status": r.rag, "slip": r.slip_days, "not_invoiced": max(r.under_billed, 0)})
    customers: dict[str, dict] = {}
    for j in jobs:
        c = customers.setdefault(j["customer"], {"customer": j["customer"], "type": j["type"], "value": 0.0,
                                                  "margin": 0.0, "quoted_margin": 0.0, "jobs": 0, "stale": False})
        c["value"] += j["value"]
        c["margin"] += j["margin"]
        c["quoted_margin"] += j["value"] * j["quoted"]
        c["jobs"] += 1
        c["stale"] = c["stale"] or j["stale"]
    for c in customers.values():
        c["margin_pct"] = c["margin"] / c["value"]
        c["quoted_pct"] = c["quoted_margin"] / c["value"]

    fleet = [{"asset": f["asset_id"], "desc": f["description"], "util": f["utilisation"],
              "contribution": f["contribution"], "breakdowns": f["breakdown_days"]} for f in plant["fleet"]]
    actions = [{"sev": a["severity"], "item": a["item"].replace(" — ", ": ", 1).replace(" — ", "; "), "owner": a["owner"],
                "due": a["due"]} for a in plant["actions"]]
    return {"months": months, "units": units, "unitAnnual": season["annual"], "jobs": jobs,
            "customers": sorted(customers.values(), key=lambda c: -c["margin"]),
            "ageing": proj["portfolio"]["ageing"], "fleet": fleet, "actions": actions, "tickets": _tickets()}


TABS = [
    ("roic", "ROIC", "/season.html",
     "Return on invested capital by month. Peak carries the year and the dead months run at a loss, which is why change "
     "is timed for June and July, never for peak."),
    ("customers", "Customer profitability", "/plan-3.html",
     "Forecast margin by customer on the committed work. This is the conversation with Dean about which work we want "
     "more of, by margin and fit."),
    ("pipeline", "Pipeline delivery", "/plan-2.html",
     "Each committed job: what's been earned, what's still to deliver, and its status. Priority 1 is getting all of it "
     "over the line."),
    ("service", "Service efficiency", "/season.html",
     "Crew utilisation and on-time completion by month. Utilisation peaks just as on-time drops, because crews are "
     "stretched."),
    ("cash", "Cash and invoicing", "/plan-4.html",
     "Work done but not invoiced, and what's owed to us by age. Invoicing milestones as they're completed is a Level 2 "
     "quick win."),
    ("plant", "Plant and compliance", "/plan-2.html",
     "Fleet utilisation and contribution, with the ticket, induction and servicing actions that keep live sites safe."),
]

JS = r"""
(() => {
const D = __DATA__;
const META = __META__;
const BLUE = '#2a78d6', ORANGE = '#eb6834', RED = '#d03b3b', GREY = '#9aa39d', AMBER = '#e0a100', GREEN = '#0ca30c';
const pct = (v, dp = 1) => (v * 100).toFixed(dp) + '%';
const money = v => Math.abs(v) >= 1e6 ? '$' + (v / 1e6).toFixed(2) + 'm' : (v < 0 ? '−' : '') + '$' + Math.round(Math.abs(v) / 1000) + 'k';
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'})[c]);
const STATUS = {RED: ['At risk', '✕', RED], AMBER: ['Action needed', '!', AMBER], GREEN: ['On track', '✓', GREEN],
  'NOT REPORTED': ['No cost data', '○', GREY]};
const chip = (s, t) => { const [l, i, c] = STATUS[s] || STATUS.AMBER; return `<span class="chip" style="--c:${c}"><b>${i}</b>${esc(t || l)}</span>`; };
const card = (l, v, s) => `<div class="kc"><span>${esc(l)}</span><b>${v}</b><small>${s || ''}</small></div>`;
Chart.defaults.font.family = '"Segoe UI", system-ui, -apple-system, Roboto, Arial, sans-serif';
Chart.defaults.font.size = 12; Chart.defaults.color = '#605e5c';
Chart.defaults.plugins.tooltip.backgroundColor = '#252423'; Chart.defaults.plugins.tooltip.padding = 9;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
let chart = null, tab = 'roic', season = '';
const opt = {};
const pctAxis = (min, max) => ({ min, max, ticks: { callback: v => Math.round(v * 100) + '%' }, grid: { color: '#edebe9' } });
const moneyAxis = () => ({ ticks: { callback: v => money(v) }, grid: { color: '#edebe9' }, beginAtZero: true });
const noGrid = { grid: { display: false } };
const inSeason = m => !season || m.s === season;
const roicOf = rows => rows.reduce((a, r) => a + r.nopat, 0) * 12 / rows.length / (rows.reduce((a, r) => a + r.ic, 0) / rows.length);
const draw = cfg => { if (chart) chart.destroy(); chart = new Chart(document.getElementById('chart'), cfg); };
const ctl = html => { document.getElementById('vCtl').innerHTML = html; };
const controls = (name, values, cur) => values.map(v => `<button type="button" data-${name}="${esc(v)}"${v === cur ? ' class="on"' : ''}>${esc(v)}</button>`).join('');

const PAGES = {
  roic() {
    const unit = opt.unit || 'Whole business';
    const src = (unit === 'Whole business' ? D.months : D.units[unit]).filter(inSeason);
    const vals = src.map(m => m.nopat * 12 / m.ic);
    ctl(controls('unit', ['Whole business', ...Object.keys(D.units)], unit));
    draw({ type: 'bar', data: { labels: src.map(m => m.m), datasets: [{ label: 'ROIC (annualised)', data: vals,
        backgroundColor: vals.map(v => v < 0 ? RED : BLUE), borderRadius: 4, maxBarThickness: 46 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false },
        tooltip: { callbacks: { title: i => src[i[0].dataIndex].m + ' | ' + src[i[0].dataIndex].s,
          label: i => ' ROIC ' + pct(i.raw) + (i.raw < 0 ? ' (loss month)' : '') + ' | NOPAT ' + money(src[i.dataIndex].nopat) } } },
        scales: { y: pctAxis(-0.4, 0.6), x: noGrid } } });
    const loss = src.filter(m => m.nopat < 0).length;
    const best = src.reduce((a, m) => (m.nopat / m.ic > a.nopat / a.ic ? m : a), src[0]);
    const rows = D.unitAnnual.map(u => `<tr class="pick${u.unit === unit ? ' on' : ''}" data-unit="${esc(u.unit)}"><td>${esc(u.unit)}</td>
      <td class="n">${pct(u.roic)}</td><td class="n">${u.loss_months}</td></tr>`).join('');
    return card('ROIC | ' + (season || 'full year'), pct(roicOf(src)), esc(unit)) +
      card('Best month', best.m, pct(best.nopat * 12 / best.ic) + ' annualised') +
      card('Loss months', String(loss), 'in the selection') +
      `<table class="st"><tr><th>Unit (full year)</th><th class="n">ROIC</th><th class="n">Loss mths</th></tr>${rows}</table>
       <p class="fn">Click a unit to chart it.</p>`;
  },
  customers() {
    const mode = opt.mode || 'Margin $';
    const dollars = mode === 'Margin $';
    const c = [...D.customers].sort((a, b) => dollars ? b.margin - a.margin : b.margin_pct - a.margin_pct);
    ctl(controls('mode', ['Margin $', 'Margin %'], mode));
    const ds = dollars
      ? [{ label: 'Forecast margin', data: c.map(x => x.margin), backgroundColor: BLUE, borderRadius: 4 },
         { label: 'Quoted margin', data: c.map(x => x.quoted_margin), backgroundColor: ORANGE, borderRadius: 4 }]
      : [{ label: 'Forecast margin', data: c.map(x => x.margin_pct), backgroundColor: BLUE, borderRadius: 4 },
         { label: 'Quoted margin', data: c.map(x => x.quoted_pct), backgroundColor: ORANGE, borderRadius: 4 }];
    draw({ type: 'bar', data: { labels: c.map(x => x.customer), datasets: ds },
      options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { position: 'top', align: 'end' },
        tooltip: { callbacks: { label: i => ' ' + i.dataset.label + ': ' + (dollars ? money(i.raw) : pct(i.raw)),
          afterBody: i => { const x = c[i[0].dataIndex]; return [x.type + ' | ' + x.jobs + ' job' + (x.jobs > 1 ? 's' : '') +
            ' | revenue ' + money(x.value)].concat(x.stale ? ['No current cost data: quoted margin shown'] : []); } } } },
        scales: { x: dollars ? moneyAxis() : pctAxis(0, 0.3), y: noGrid } } });
    const total = c.reduce((a, x) => a + x.margin, 0), rev = c.reduce((a, x) => a + x.value, 0);
    const below = c.filter(x => x.margin_pct < x.quoted_pct - 0.001);
    const rows = c.map(x => { const d = (x.margin_pct - x.quoted_pct) * 100; return `<tr><td>${esc(x.customer)}${x.stale ? ' *' : ''}</td>
      <td class="n">${money(x.value)}</td><td class="n">${pct(x.margin_pct)}</td>
      <td class="n ${d < -0.05 ? 'neg' : 'pos'}">${(d >= 0 ? '+' : '−') + Math.abs(d).toFixed(1)}</td></tr>`; }).join('');
    return card('Forecast margin', money(total), pct(total / rev) + ' of ' + money(rev) + ' revenue') +
      card('Below quoted margin', String(below.length), below.map(x => esc(x.customer)).join(', ') || 'none') +
      `<table class="st"><tr><th>Customer</th><th class="n">Revenue</th><th class="n">Margin</th><th class="n">vs quote</th></tr>${rows}</table>
       <p class="fn">* No current cost data, so the quoted margin is shown. "vs quote" is in percentage points.</p>`;
  },
  pipeline() {
    ctl('');
    const j = [...D.jobs].sort((a, b) => b.value - a.value);
    draw({ type: 'bar', data: { labels: j.map(x => x.job), datasets: [
        { label: 'Earned to date', data: j.map(x => x.value * x.complete), backgroundColor: BLUE, borderRadius: 4, stack: 's' },
        { label: 'Still to deliver', data: j.map(x => x.value * (1 - x.complete)), backgroundColor: '#b7d3f6', borderRadius: 4, stack: 's' }] },
      options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { position: 'top', align: 'end' },
        tooltip: { callbacks: { label: i => ' ' + i.dataset.label + ': ' + money(i.raw),
          afterBody: i => { const x = j[i[0].dataIndex]; return [pct(x.complete, 0) + ' complete of ' + money(x.value),
            (STATUS[x.status] || STATUS.AMBER)[0] + (x.slip ? ' | ' + x.slip + ' days behind' : '')]; } } } },
        scales: { x: { ...moneyAxis(), stacked: true }, y: { ...noGrid, stacked: true } } } });
    const total = j.reduce((a, x) => a + x.value, 0), earned = j.reduce((a, x) => a + x.value * x.complete, 0);
    const rows = j.map(x => `<tr><td>${esc(x.job)}</td><td>${chip(x.status)}</td></tr>`).join('');
    return card('Committed pipeline', money(total), j.length + ' jobs') +
      card('Delivered by value', pct(earned / total, 0), money(total - earned) + ' still to deliver') +
      `<table class="st"><tr><th>Job</th><th>Status</th></tr>${rows}</table>`;
  },
  service() {
    ctl('');
    const src = D.months.filter(inSeason);
    draw({ type: 'line', data: { labels: src.map(m => m.m), datasets: [
        { label: 'Crew utilisation', data: src.map(m => m.util), borderColor: BLUE, backgroundColor: BLUE, borderWidth: 2, pointRadius: 4, tension: .25 },
        { label: 'On-time completion', data: src.map(m => m.ot), borderColor: ORANGE, backgroundColor: ORANGE, borderWidth: 2, pointRadius: 4, tension: .25 }] },
      options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top', align: 'end' }, tooltip: { callbacks: {
          title: i => src[i[0].dataIndex].m + ' | ' + src[i[0].dataIndex].s, label: i => ' ' + i.dataset.label + ': ' + pct(i.raw, 0) } } },
        scales: { y: pctAxis(0.2, 1), x: noGrid } } });
    const avg = k => src.reduce((a, m) => a + m[k], 0) / src.length;
    const worst = src.reduce((a, m) => (m.ot < a.ot ? m : a), src[0]);
    return card('Utilisation', pct(avg('util'), 0), season || 'full year') +
      card('On-time completion', pct(avg('ot'), 0), season || 'full year') +
      card('Lowest on-time', worst.m, pct(worst.ot, 0) + ' of jobs on time') +
      `<p class="fn">Utilisation is the billable share of paid crew hours. Use the season filter to compare peak with the quiet months.</p>`;
  },
  cash() {
    const view = opt.view || 'Not yet invoiced';
    ctl(controls('view', ['Not yet invoiced', 'Debtor ageing'], view));
    const j = D.jobs.filter(x => x.not_invoiced > 0).sort((a, b) => b.not_invoiced - a.not_invoiced);
    const age = Object.entries(D.ageing);
    if (view === 'Not yet invoiced') {
      draw({ type: 'bar', data: { labels: j.map(x => x.job), datasets: [{ label: 'Work done, not invoiced', data: j.map(x => x.not_invoiced),
          backgroundColor: BLUE, borderRadius: 4, maxBarThickness: 40 }] },
        options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { display: false },
          tooltip: { callbacks: { label: i => ' Not invoiced: ' + money(i.raw) } } }, scales: { x: moneyAxis(), y: noGrid } } });
    } else {
      draw({ type: 'bar', data: { labels: age.map(a => a[0] + ' days'), datasets: [{ label: 'Owed to us', data: age.map(a => a[1]),
          backgroundColor: age.map((a, i) => i < 2 ? BLUE : ORANGE), borderRadius: 4, maxBarThickness: 70 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false },
          tooltip: { callbacks: { label: i => ' Owed: ' + money(i.raw) } } }, scales: { y: moneyAxis(), x: noGrid } } });
    }
    const ni = D.jobs.reduce((a, x) => a + x.not_invoiced, 0), owed = age.reduce((a, x) => a + x[1], 0);
    const over60 = age.filter(a => ['61-90', '90+'].includes(a[0])).reduce((a, x) => a + x[1], 0);
    return card('Work done, not invoiced', money(ni), j.length + ' jobs') + card('Owed to us', money(owed), 'invoices issued, unpaid') +
      card('Over 60 days', money(over60), over60 ? 'to chase this week' : 'nothing overdue');
  },
  plant() {
    const view = opt.pview || 'Utilisation';
    const util = view === 'Utilisation';
    ctl(controls('pview', ['Utilisation', 'Contribution'], view));
    const f = [...D.fleet].sort((a, b) => util ? b.util - a.util : b.contribution - a.contribution);
    draw({ type: 'bar', data: { labels: f.map(x => x.asset), datasets: [{ label: view, data: f.map(x => util ? x.util : x.contribution),
        backgroundColor: f.map(x => (util ? x.util < 0.4 : x.contribution < 0) ? ORANGE : BLUE), borderRadius: 4, maxBarThickness: 46 }] },
      options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: {
        title: i => f[i[0].dataIndex].asset + ' | ' + f[i[0].dataIndex].desc,
        label: i => ' ' + (util ? 'Utilisation ' + pct(i.raw, 0) : 'Contribution ' + money(i.raw)),
        afterLabel: i => ' ' + f[i.dataIndex].breakdowns + ' breakdown days in 8 weeks' } } },
        scales: { y: util ? pctAxis(0, 1) : moneyAxis(), x: noGrid } } });
    const t = D.tickets;
    const acts = D.actions.slice(0, 6).map(a => `<li>${chip(a.sev === 'RED' ? 'RED' : 'AMBER', a.sev === 'RED' ? 'Now' : 'Soon')}
      <span>${esc(a.item)}</span></li>`).join('');
    return card('Ticket compliance', Math.round((t.total - t.expired) / t.total * 100) + '%', t.expired + ' expired, ' + t.soon + ' due in 30 days') +
      `<ul class="acts">${acts}</ul><p class="fn">Orange: under 40% utilised, or negative contribution.</p>`;
  },
};

function render() {
  const m = META[tab];
  document.getElementById('vTitle').innerHTML = esc(m.title) + ` <a class="drill" href="${m.href}">Details ↗</a>`;
  document.getElementById('vAbout').textContent = m.about;
  document.getElementById('side').innerHTML = PAGES[tab]();
  document.querySelectorAll('.tabs button').forEach(b => { const on = b.dataset.tab === tab; b.classList.toggle('on', on); b.setAttribute('aria-selected', on); });
  document.querySelectorAll('.slicer button').forEach(b => b.classList.toggle('on', b.dataset.s === season));
  document.getElementById('report').classList.toggle('noseason', !['roic', 'service'].includes(tab));
}
document.querySelector('.tabs').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { tab = b.dataset.tab; render(); } });
document.querySelector('.slicer').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { season = b.dataset.s; render(); } });
document.getElementById('report').addEventListener('click', e => {
  const b = e.target.closest('[data-unit],[data-mode],[data-view],[data-pview]'); if (!b) return;
  if (b.dataset.unit) opt.unit = b.dataset.unit;
  if (b.dataset.mode) opt.mode = b.dataset.mode;
  if (b.dataset.view) opt.view = b.dataset.view;
  if (b.dataset.pview) opt.pview = b.dataset.pview;
  render();
});
render();
})();
"""


def build() -> str:
    d = data()
    tabs = "".join(f"<button type='button' role='tab' data-tab='{k}'>{esc(t)}</button>" for k, t, _, _ in TABS)
    meta = json.dumps({k: {"title": t, "href": h, "about": a} for k, t, h, a in TABS})
    seasons: list[str] = []
    for m in d["months"]:
        if m["s"] not in seasons:
            seasons.append(m["s"])
    slicer = "".join(f"<button type='button' data-s='{esc(s)}'>{esc(s.replace(' (assumed)', ''))}</button>" for s in seasons)
    js = JS.replace("__DATA__", json.dumps(d)).replace("__META__", meta)
    return f"""<style>{CSS}</style>
<div class="report" id="report">
  <div class="rhead">
    <div><b>Green Turf | 90-Day Plan review</b><span>Illustrative data</span></div>
    <div class="slicer" role="group" aria-label="Season filter"><span>Season</span>
      <button type="button" data-s="">All</button>{slicer}</div>
  </div>
  <div class="page">
    <div class="main">
      <div class="vhead"><h3 id="vTitle"></h3><div class="vctl" id="vCtl"></div></div>
      <p class="about" id="vAbout"></p>
      <div class="chartbox"><canvas id="chart" role="img" aria-label="Report chart"></canvas></div>
    </div>
    <aside class="side" id="side"></aside>
  </div>
  <div class="tabs" role="tablist" aria-label="Report pages">{tabs}</div>
</div>
<p class="note">All figures are illustrative, calculated from sample data to show how I'd review the business. Click a
tab to change the page, hover a bar or point for the figures, and click a legend item to hide a series. The season filter
applies to the ROIC and service efficiency tabs.</p>
<script src="/vendor/chart.umd.min.js"></script>
<script>{js}</script>"""


CSS = """
.report{background:#f3f2f1;border:1px solid #d6dbd5;border-radius:12px;overflow:hidden;margin:6px 0 10px;
  font-family:"Segoe UI",system-ui,-apple-system,Roboto,Arial,sans-serif;box-shadow:0 8px 24px -16px rgba(20,60,30,.35)}
.rhead{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;background:#0f5f2b;color:#fff;
  padding:10px 16px}
.rhead b{font-size:16px;display:block}.rhead span{font-size:12px;opacity:.85}
.report button{all:unset;box-sizing:border-box;cursor:pointer}
.report button:focus-visible{outline:2px solid #1fb43e;outline-offset:2px}
.rhead .slicer{display:flex;gap:4px;flex-wrap:wrap;align-items:center;transition:opacity .2s;width:auto;margin:0;box-shadow:none;border:0}
.slicer span{font-size:11px;text-transform:uppercase;letter-spacing:.06em;margin-right:4px;opacity:.85}
.slicer button{font-size:12px;padding:3px 10px;border-radius:999px;border:1px solid rgba(255,255,255,.45);color:#fff}
.slicer button.on{background:#fff;color:#0f5f2b;border-color:#fff}
.report.noseason .slicer{opacity:.4;pointer-events:none}
.page{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:10px;padding:12px;min-height:480px}
.main,.side{background:#fff;border:1px solid #e1dfdd;border-radius:6px;padding:12px 14px;min-width:0}
.vhead{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.vhead h3{font-size:15px;font-weight:600;color:#252423;margin:0}
.drill{font-size:12px;font-weight:400;color:#0a6aa1;text-decoration:none;margin-left:8px}.drill:hover{text-decoration:underline}
.vctl{display:flex;gap:4px;flex-wrap:wrap}
.vctl button{font-size:12px;padding:3px 10px;border-radius:4px;border:1px solid #c8c6c4;color:#252423;background:#fff}
.vctl button.on{background:#0f5f2b;border-color:#0f5f2b;color:#fff}
.about{font-size:12.5px;color:#605e5c;margin:6px 0 8px;max-width:760px}
.chartbox{position:relative;height:370px}
.kc{border:1px solid #edebe9;border-top:3px solid #1fb43e;border-radius:6px;padding:8px 12px;margin-bottom:8px}
.kc span{display:block;font-size:11.5px;color:#605e5c}.kc b{display:block;font-size:22px;color:#252423;line-height:1.25}
.kc small{font-size:11.5px;color:#605e5c}
.st{font-size:12px;border:0;box-shadow:none;margin-top:4px}.st th{background:#f3f2f1;font-size:11px;padding:5px 6px}
.st td{padding:5px 6px}.st tr.pick{cursor:pointer}.st tr.pick:hover td{background:#f3f9f4}
.st tr.pick.on td{background:#e4f6e8;font-weight:600}.st .neg{color:#b52f2e}.st .pos{color:#14813a}
.chip{display:inline-flex;gap:4px;align-items:center;font-size:11px;font-weight:600;color:#252423;white-space:nowrap;
  padding:1px 8px 1px 2px;border-radius:999px;background:color-mix(in srgb,var(--c) 12%,#fff)}
.chip b{display:inline-grid;place-items:center;width:15px;height:15px;border-radius:50%;background:var(--c);color:#fff;font-size:10px}
.acts{list-style:none;padding:0;margin:4px 0 0}.acts li{display:flex;gap:8px;align-items:flex-start;font-size:12px;padding:5px 0;
  border-bottom:1px solid #f0f0ee;margin:0}.acts li>span:not(.chip){flex:1}.acts .chip{flex:none}
.fn{font-size:11.5px;color:#605e5c;margin:8px 0 0}
.tabs{display:flex;gap:2px;flex-wrap:wrap;background:#e8e6e4;border-top:1px solid #d2d0ce;padding:4px 8px 0}
.tabs button{font-size:12.5px;padding:7px 14px;color:#252423;border-bottom:3px solid transparent;border-radius:4px 4px 0 0}
.tabs button:hover{background:#f3f2f1}.tabs button.on{border-bottom-color:#1fb43e;font-weight:600;background:#fff}
@media(max-width:900px){.page{grid-template-columns:1fr}.chartbox{height:320px}}
"""
