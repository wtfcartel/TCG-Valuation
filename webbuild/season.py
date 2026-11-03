"""Season, ROIC and service efficiency page (demonstrative).

Charts are inline SVG generated here, so the page needs no chart library. Each chart has hover tooltips (data-tip) and
a table of the underlying numbers. Data comes from demo4_seasonality.engine, the same engine behind the Power BI feed.
"""

from __future__ import annotations

from demo4_seasonality.engine import run

from common.report import esc

SEASON_BG = {"Slow growth": "#eef6e8", "Heavy growth": "#d9f0de", "Dead": "#ecebe7", "Peak": "#dcefff",
             "Wind-down (assumed)": "#f4f3ef"}
SERIES_1, SERIES_2 = "#2a78d6", "#eb6834"      # validated categorical slots 1 and 2 (blue, orange)
INK, MUTED, GRID = "#1d2a22", "#5d6b62", "#e3e6e0"


def pct(v: float, dp: int = 0) -> str:
    out = f"{v * 100:.{dp}f}"
    return ("0" if float(out) == 0 else out.replace("-", "−")) + "%"


def money_k(v: float) -> str:
    return ("−" if v < 0 else "") + f"${abs(v) / 1000:,.0f}k"


def roic_fill(v: float) -> tuple[str, str]:
    """Diverging blue (positive) / red (negative), grey midpoint. Returns (fill, text colour)."""
    steps = [(-0.20, "#b52f2e", "#fff"), (-0.05, "#eea3a2", INK), (0.05, "#ecebe7", INK), (0.20, "#b7d3f6", INK),
             (0.35, "#6da7ec", INK), (0.50, "#2a78d6", "#fff")]
    for limit, fill, txt in steps:
        if v < limit:
            return fill, txt
    return "#184f95", "#fff"


def season_strip(r: dict) -> str:
    cells = ""
    groups: list[tuple[str, int, int]] = []
    for i, p in enumerate(r["profile"]):
        if groups and groups[-1][0] == p["season"]:
            groups[-1] = (p["season"], groups[-1][1], i)
        else:
            groups.append((p["season"], i, i))
    for season, a, b in groups:
        span = b - a + 1
        months = " ".join(r["months"][a:b + 1])
        cells += (f"<div class='sz' style='grid-column:span {span};background:{SEASON_BG[season]}'>"
                  f"<b>{esc(season)}</b><span>{months}</span></div>")
    return f"<div class='strip'>{cells}</div>"


def bands(r: dict, x0: float, step: float, top: float, h: float) -> str:
    out = ""
    for i, p in enumerate(r["profile"]):
        out += f"<rect x='{x0 + i * step:.1f}' y='{top}' width='{step:.1f}' height='{h}' fill='{SEASON_BG[p['season']]}'/>"
    return out


def roic_chart(r: dict) -> str:
    W, H, L, R, T, B = 760, 280, 52, 10, 14, 30
    pw, ph = W - L - R, H - T - B
    lo, hi = -0.30, 0.50
    y = lambda v: T + (hi - v) / (hi - lo) * ph  # noqa: E731
    step = pw / 12
    svg = bands(r, L, step, T, ph)
    for t in (-0.2, 0, 0.2, 0.4):
        svg += (f"<line x1='{L}' x2='{W - R}' y1='{y(t):.1f}' y2='{y(t):.1f}' stroke='{INK if t == 0 else GRID}' "
                f"stroke-width='{1.2 if t == 0 else 1}'/><text x='{L - 6}' y='{y(t) + 4:.1f}' text-anchor='end' "
                f"class='ax'>{pct(t)}</text>")
    for i, b in enumerate(r["business"]):
        v = b["roic_annualised"]
        x = L + i * step + step * 0.22
        w = step * 0.56
        top, bot = (y(v), y(0)) if v >= 0 else (y(0), y(v))
        fill = SERIES_1 if v >= 0 else "#d03b3b"
        tip = f"{b['month']} ({b['season']}): ROIC {pct(v, 1)} annualised, revenue {money_k(b['revenue'])}"
        svg += (f"<g class='hit' data-tip='{esc(tip)}'><rect x='{L + i * step:.1f}' y='{T}' width='{step:.1f}' "
                f"height='{ph}' fill='transparent'/><rect x='{x:.1f}' y='{top:.1f}' width='{w:.1f}' "
                f"height='{max(bot - top, 1):.1f}' rx='3' fill='{fill}'/></g>")
        svg += f"<text x='{L + i * step + step / 2:.1f}' y='{H - 10}' text-anchor='middle' class='ax'>{b['month']}</text>"
    peak = max(r["business"], key=lambda b: b["roic_annualised"])
    low = min(r["business"], key=lambda b: b["roic_annualised"])
    for b, dy in ((peak, -6), (low, 14)):
        i = r["months"].index(b["month"])
        svg += (f"<text x='{L + i * step + step / 2:.1f}' y='{y(b['roic_annualised']) + dy:.1f}' text-anchor='middle' "
                f"class='lbl'>{pct(b['roic_annualised'])}</text>")
    return f"<svg viewBox='0 0 {W} {H}' class='chart' role='img' aria-label='Business ROIC by month'>{svg}</svg>"


def efficiency_chart(r: dict) -> str:
    W, H, L, R, T, B = 760, 280, 52, 96, 14, 30
    pw, ph = W - L - R, H - T - B
    lo, hi = 0.2, 1.0
    y = lambda v: T + (hi - v) / (hi - lo) * ph  # noqa: E731
    step = pw / 12
    cx = lambda i: L + i * step + step / 2  # noqa: E731
    svg = bands(r, L, step, T, ph)
    for t in (0.2, 0.4, 0.6, 0.8, 1.0):
        svg += (f"<line x1='{L}' x2='{L + pw}' y1='{y(t):.1f}' y2='{y(t):.1f}' stroke='{GRID}'/>"
                f"<text x='{L - 6}' y='{y(t) + 4:.1f}' text-anchor='end' class='ax'>{pct(t)}</text>")
    for key, colour, name in (("utilisation", SERIES_1, "Utilisation"), ("on_time", SERIES_2, "On-time")):
        pts = " ".join(f"{cx(i):.1f},{y(b[key]):.1f}" for i, b in enumerate(r["business"]))
        svg += f"<polyline points='{pts}' fill='none' stroke='{colour}' stroke-width='2' stroke-linejoin='round'/>"
        for i, b in enumerate(r["business"]):
            svg += (f"<circle cx='{cx(i):.1f}' cy='{y(b[key]):.1f}' r='4' fill='{colour}' stroke='#fff' "
                    f"stroke-width='2'/>")
        last = r["business"][-1][key]
        svg += f"<text x='{L + pw + 8}' y='{y(last) + 4:.1f}' class='lbl'>{name}</text>"
    for i, b in enumerate(r["business"]):
        tip = (f"{b['month']} ({b['season']}): utilisation {pct(b['utilisation'])}, "
               f"on-time {pct(b['on_time'])}")
        svg += (f"<rect class='hit' data-tip='{esc(tip)}' x='{L + i * step:.1f}' y='{T}' width='{step:.1f}' "
                f"height='{ph}' fill='transparent'/>")
        svg += f"<text x='{cx(i):.1f}' y='{H - 10}' text-anchor='middle' class='ax'>{b['month']}</text>"
    return f"<svg viewBox='0 0 {W} {H}' class='chart' role='img' aria-label='Service efficiency by month'>{svg}</svg>"


def heatmap(r: dict) -> str:
    head = "".join(f"<th class='n'>{m}</th>" for m in r["months"])
    rows = ""
    for u in r["units"]:
        cells = ""
        for m in r["months"]:
            rec = next(x for x in r["monthly"] if x["unit"] == u and x["month"] == m)
            fill, txt = roic_fill(rec["roic_annualised"])
            tip = f"{u}, {m}: ROIC {pct(rec['roic_annualised'], 1)}, EBIT {money_k(rec['ebit'])}"
            cells += (f"<td class='hm hit' data-tip='{esc(tip)}' style='background:{fill};color:{txt}'>"
                      f"{pct(rec['roic_annualised'])}</td>")
        rows += f"<tr><th>{esc(u)}</th>{cells}</tr>"
    season_row = "".join(f"<td class='sr' style='background:{SEASON_BG[p['season']]}'></td>" for p in r["profile"])
    return (f"<div class='hmwrap'><table class='heat'><tr><th>Unit</th>{head}</tr><tr><th class='note'>Season</th>"
            f"{season_row}</tr>{rows}</table></div>"
            "<p class='note'>Colour: red is a loss month, grey is about break-even, deeper blue is a higher return. "
            "Values are annualised ROIC for that month.</p>")


def annual_bars(r: dict) -> str:
    W, rowh, L = 760, 34, 170
    H = rowh * len(r["annual"]) + 10
    hi = 0.40
    svg = ""
    for i, a in enumerate(sorted(r["annual"], key=lambda a: -a["roic"])):
        yy = 6 + i * rowh
        w = (W - L - 60) * a["roic"] / hi
        tip = (f"{a['unit']}: ROIC {pct(a['roic'], 1)}, NOPAT {money_k(a['nopat'])}, average capital "
               f"{money_k(a['avg_invested_capital'])}, {a['loss_months']} loss months")
        svg += (f"<g class='hit' data-tip='{esc(tip)}'><text x='{L - 10}' y='{yy + 17}' text-anchor='end' "
                f"class='lbl'>{esc(a['unit'])}</text><rect x='{L}' y='{yy + 4}' width='{w:.1f}' height='18' rx='3' "
                f"fill='{SERIES_1}'/><text x='{L + w + 6:.1f}' y='{yy + 17}' class='lbl'>{pct(a['roic'], 1)}</text></g>")
    return f"<svg viewBox='0 0 {W} {H}' class='chart' role='img' aria-label='Annual ROIC per unit'>{svg}</svg>"


def numbers_table(r: dict) -> str:
    rows = "".join(
        f"<tr><td>{b['month']}</td><td>{esc(b['season'])}</td><td class='n'>{b['activity_index']:.2f}</td>"
        f"<td class='n'>{money_k(b['revenue'])}</td><td class='n'>{money_k(b['nopat'])}</td>"
        f"<td class='n'>{pct(b['roic_annualised'], 1)}</td><td class='n'>{pct(b['utilisation'])}</td>"
        f"<td class='n'>{pct(b['on_time'])}</td></tr>" for b in r["business"])
    return ("<details><summary>Show the monthly numbers</summary><table><tr><th>Month</th><th>Season</th>"
            "<th class='n'>Activity</th><th class='n'>Revenue</th><th class='n'>NOPAT</th><th class='n'>ROIC (ann.)</th>"
            f"<th class='n'>Utilisation</th><th class='n'>On-time</th></tr>{rows}</table></details>")


CSS = """
.strip{display:grid;grid-template-columns:repeat(12,1fr);gap:4px;margin:6px 0 14px}
.sz{border-radius:8px;padding:8px 10px;font-size:12.5px;line-height:1.3}.sz b{display:block;font-size:13px}
.sz span{color:var(--muted)}
.chart{width:100%;height:auto;display:block;background:#fff;border:1px solid var(--line);border-radius:10px}
.chart .ax{font-size:11px;fill:#5d6b62}.chart .lbl{font-size:12px;fill:#1d2a22;font-weight:600}
.hit{cursor:default}
.hmwrap{overflow-x:auto}.heat{min-width:640px}.heat td.hm{text-align:center;font-size:12px;font-variant-numeric:tabular-nums;
border:2px solid #fff;padding:6px 2px}.heat td.sr{height:8px;padding:0;border:2px solid #fff}
.heat th{white-space:nowrap}
#tip{position:fixed;pointer-events:none;background:#1d2a22;color:#fff;font-size:12.5px;padding:6px 9px;border-radius:6px;
display:none;z-index:20;max-width:300px}
.legend{display:flex;gap:16px;font-size:12.5px;margin:6px 0}.legend i{display:inline-block;width:12px;height:12px;
border-radius:3px;margin-right:6px;vertical-align:-1px}
@media(max-width:800px){.strip{grid-template-columns:repeat(6,1fr)}.sz{grid-column:span 3!important}}
"""

TIP_JS = """<div id="tip" role="tooltip"></div><script>
(() => { const tip = document.getElementById('tip');
  document.querySelectorAll('[data-tip]').forEach(el => {
    el.addEventListener('mousemove', e => { tip.textContent = el.dataset.tip; tip.style.display = 'block';
      tip.style.left = Math.min(e.clientX + 14, innerWidth - 310) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; });
    el.addEventListener('mouseleave', () => tip.style.display = 'none');
  }); })();
</script>"""


def section(lv, brief_fn, criteria) -> str:
    r = run()
    biz = r["business"]
    peak = [b for b in biz if b["season"] == "Peak"]
    dead = [b for b in biz if b["season"] == "Dead"]
    avg = lambda rows, k: sum(b[k] for b in rows) / len(rows)  # noqa: E731
    best = max(r["annual"], key=lambda a: a["roic"])
    worst = min(r["annual"], key=lambda a: a["roic"])
    return f"""<style>{CSS}</style>
{brief_fn("Early Risks, Opportunities & Quick Wins", criteria)}
<p class="lede">A demonstration of how I'd read the business across the year. The season pattern is the one we've been
working with: slow growth in January and February, heavy growth March to May, no growth in June and July, and peak from
August to November. December wasn't specified, so I've assumed it winds down into the Christmas break. The units and
dollar figures are invented to show the method.</p>
<h2>The season</h2>{season_strip(r)}
<div class="grid k4">
<div class="card kpi"><div class="l">Business ROIC (year)</div><div class="v">{pct(r['business_roic'], 1)}</div>
<div class="s">NOPAT over average invested capital</div></div>
<div class="card kpi"><div class="l">Peak ROIC (Aug to Nov)</div><div class="v">{pct(avg(peak, 'roic_annualised'))}</div>
<div class="s">annualised, average of the four months</div></div>
<div class="card kpi"><div class="l">Dead months (Jun, Jul)</div><div class="v">{money_k(sum(b['nopat'] for b in dead))}</div>
<div class="s">NOPAT: crews and plant still cost money</div></div>
<div class="card kpi"><div class="l">On-time in peak</div><div class="v">{pct(avg(peak, 'on_time'))}</div>
<div class="s">against {pct(avg(dead, 'on_time'))} in quiet months</div></div></div>

<h2>Return on invested capital by month</h2>
<p class="note" style="margin:0 0 6px">Whole business, annualised. Blue is a positive return, red is a loss month. Shading
shows the season.</p>
{roic_chart(r)}

<h2>ROIC per unit, by month</h2>{heatmap(r)}

<h2>ROIC per unit, full year</h2>{annual_bars(r)}
<p class="note">{esc(best['unit'])} returns the most on its capital because it carries the least plant and its work holds
up through the quiet months. {esc(worst['unit'])} has {worst['loss_months']} loss months: it's the most exposed to the
season.</p>

<h2>Service efficiency by month</h2>
<div class="legend"><span><i style="background:{SERIES_1}"></i>Crew utilisation (billable share of paid hours)</span>
<span><i style="background:{SERIES_2}"></i>On-time completion</span></div>
{efficiency_chart(r)}
{numbers_table(r)}

<h2>What this tells me, and how it shapes the plan</h2>
<div class="grid k2">
<div class="card"><h3>{lv(1)} Peak, August to November</h3><p style="margin:0">Highest return and full crews, but on-time
completion drops to about {pct(min(b['on_time'] for b in peak))} as crews are stretched. This is when the existing mandates
are most at risk, so it's the wrong time for any change. All effort goes into delivery, variations and invoicing.</p></div>
<div class="card"><h3>{lv(1)}{lv(2)} Slow growth, January and February</h3><p style="margin:0">Carry-over work from peak
gets completed and the cash from peak gets collected. With activity at about 70 to 80% of an average month, this is
the right window to bring in the Level 2 controls without getting in the way of the crews.</p></div>
<div class="card"><h3>{lv(2)} Heavy growth, March to May</h3><p style="margin:0">Strong work and a second chance to fill the
pipeline. This is when I'd sit down with Dean on capacity: what's already committed for August, what we can still take
on, and when we'd need to hire in plant or labour.</p></div>
<div class="card"><h3>{lv(3)} Dead months, June and July</h3><p style="margin:0">Fixed costs keep running, so the business
makes a loss on most units. It's also the least disruptive time for any Level 3 change: systems, training, plant
servicing, ticket renewals and structure. If Mick and Dean decide to make a change, this is the window to do it in.</p></div>
</div>
<div class="say">If I started in late November or December, my first 90 days would run from the tail of peak through the
January and February slow period. That lines up with the plan: complete the existing mandates, collect the cash, put the
light controls in before March, and have the Level 3 options ready to decide on well ahead of June.</div>
<p class="note">The same figures are available as Power BI feeds: <a href="/api/powerbi?table=season_monthly&amp;format=csv">season_monthly</a>,
<a href="/api/powerbi?table=season_units&amp;format=csv">season_units</a> and
<a href="/api/powerbi?table=season_business&amp;format=csv">season_business</a>.</p>
{TIP_JS}"""
