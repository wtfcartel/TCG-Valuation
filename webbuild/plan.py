"""The "First 90 Days" presentation, as navigable web pages.

One page per area of the final-round brief, in the order the brief lists them, plus a Q&A preparation page.
Every page has previous/next links and responds to the left/right arrow keys, so it can be presented directly.

The plan is written as hypotheses to test, not as facts about the company: nothing here claims knowledge of
Green Turf's internal performance.
"""

from __future__ import annotations

from common.report import CSS, esc

PLAN_CSS = """
.lede{font-size:16px;max-width:820px;margin:0 0 14px}
.step{display:flex;gap:10px;align-items:baseline}.step b{min-width:92px;color:var(--green)}
.phase{border-top:4px solid var(--green)}.phase.p2{border-top-color:#5b8f3e}.phase.p3{border-top-color:#8bb04a}
.phase .when{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.prio{display:grid;grid-template-columns:44px 1fr;gap:12px}.prio .num{font-size:26px;font-weight:700;color:var(--green)}
ul.tight{margin:6px 0 0;padding-left:18px}ul.tight li{margin:3px 0}
.pager{display:flex;justify-content:space-between;gap:10px;margin-top:26px}
.pager span{flex:1}.pager a{flex:1;padding:12px 14px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);text-decoration:none}
.pager a:hover{border-color:var(--green)}.pager .r{text-align:right}.pager small{display:block;color:var(--muted)}
.say{background:var(--green-l);border-left:4px solid var(--green);padding:10px 14px;border-radius:0 6px 6px 0;margin:14px 0;max-width:860px}
.qa details{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:8px 0}
.qa summary{cursor:pointer;font-weight:600}.qa details p{margin:8px 0 0}
.slidecount{font-size:12px;color:var(--muted)}
@media(max-width:800px){.k4,.k3,.k2{grid-template-columns:1fr}.pager{flex-direction:column}.lede{font-size:15px}}
"""

PLAN_BANNER = ("Plan for discussion. Written from outside the business, so every priority is a hypothesis I would test in "
               "the first 30 days, not a conclusion. The linked prototypes run on invented data.")


def shell(title: str, subtitle: str, body: str, nav: str, extra_css: str = "") -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<style>{CSS}{PLAN_CSS}{extra_css}</style></head>
<body><div class="wrap">{nav}<header><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></header>
<div class="banner" style="background:#eef5ef;border-color:#b9d3bf">{esc(PLAN_BANNER)}</div>{body}
<footer>James Fischer-Myall · Business Operations Director, final round · Green Turf</footer>
</div></body></html>"""


# --- Section content ---------------------------------------------------------------------------------------------

def overview() -> str:
    phases = [
        ("p1", "Days 1–30", "Listen and learn",
         ["Meet every team, on site and in the office", "Follow real jobs from quote to cash",
          "Baseline the numbers that exist, and note the ones that don't",
          "Day 30: share what I found with Mick and Dean, and agree the priorities"]),
        ("p2", "Days 31–60", "Prioritise and deliver quick wins",
         ["Start a weekly operations meeting with owners and dates", "Weekly margin check on the largest live jobs",
          "Tighten invoicing and debtor follow-up", "Ticket and induction expiry register"]),
        ("p3", "Days 61–90", "Embed and plan ahead",
         ["Monthly KPI pack that Mick, Dean and I all use", "Monthly sales-and-capacity review with Dean",
          "Business case for the one or two system changes worth funding",
          "Day 90: review against the scorecard and agree the next 12 months"]),
    ]
    cards = "".join(
        f"<div class='card phase {c}'><div class='when'>{w}</div><h3 style='margin-top:4px'>{t}</h3>"
        f"<ul class='tight'>{''.join(f'<li>{x}</li>' for x in items)}</ul></div>" for c, w, t, items in phases)
    agenda = [
        ("plan-1.html", "1 · How I would get to know the business", "~3 min"),
        ("plan-2.html", "2 · My priorities for the first 90 days", "~5 min"),
        ("plan-3.html", "3 · Partnering with Mick and Dean", "~3 min"),
        ("plan-4.html", "4 · Early risks, opportunities and quick wins", "~4 min"),
        ("plan-5.html", "5 · My leadership approach", "~3 min"),
        ("qa.html", "Q&A preparation (not presented)", "20 min"),
    ]
    rows = "".join(f"<tr><td><a href='/{u}'>{t}</a></td><td class='n'>{m}</td></tr>" for u, t, m in agenda)
    return f"""
<p class="lede">Green Turf is a hands-on business that is growing. The job of a Business Operations Director in the first
90 days is not to arrive with answers. It is to understand how work really flows, protect what already works, and put in
the few disciplines that let the business grow without losing margin, cash or people.</p>
<div class="say"><b>In one line:</b> listen first, fix what is costing money or risking safety, and build an operating
rhythm that frees Mick to lead and gives Dean confidence that what he sells can be delivered well.</div>
<h2>The 90 days at a glance</h2><div class="grid k3">{cards}</div>
<h2>Agenda (15–20 minutes)</h2><table><tr><th>Section</th><th class="n">Time</th></tr>{rows}</table>
<h2>What I will measure myself against at day 90</h2>
<div class="grid k4">
<div class="card kpi"><div class="l">Visibility</div><div class="v" style="font-size:18px">Weekly margin view</div>
<div class="s">on every job above an agreed value</div></div>
<div class="card kpi"><div class="l">Cash</div><div class="v" style="font-size:18px">Invoicing on time</div>
<div class="s">and a falling debtor-day trend</div></div>
<div class="card kpi"><div class="l">Rhythm</div><div class="v" style="font-size:18px">Weekly + monthly</div>
<div class="s">meetings held, actions closed on time</div></div>
<div class="card kpi"><div class="l">People</div><div class="v" style="font-size:18px">Trust earned</div>
<div class="s">team leaders bring problems to me early</div></div></div>
<p class="note">Targets are set once the baseline is known in month one. Setting numbers before seeing the data would be guessing.</p>"""


def section1() -> str:
    return """
<p class="lede">I would spend most of the first month listening, on site as much as in the office. The aim is to understand
how a job really moves through the business, where it gets stuck, and what people already know needs fixing.</p>
<div class="grid k2">
<div class="card"><h3>People</h3><ul class="tight">
<li><b>Mick:</b> the history, what he wants to keep, what keeps him up at night, what he wants to hand over</li>
<li><b>Dean:</b> the pipeline, target markets, what customers say, where delivery has helped or hurt sales</li>
<li>One-to-ones with every manager, supervisor and the office team</li>
<li>Days on site with crews: installs, maintenance, plant yard. Same three questions everywhere: what works, what gets
in your way, what would you change first</li>
<li>Calls with 5–10 key clients and a few key suppliers and subcontractors</li></ul></div>
<div class="card"><h3>Process: follow the work</h3><ul class="tight">
<li>Trace three or four recent jobs end to end: enquiry → quote → win → schedule → plant and crew → install → variations →
handover → invoice → cash</li>
<li>Note every hand-off, every re-keying of data, every spreadsheet, and every approval that waits on one person</li>
<li>Walk the safety system: SWMS, tickets, inductions, incident reporting, toolbox talks</li></ul></div>
<div class="card"><h3>Numbers</h3><ul class="tight">
<li>Quoted vs actual margin on recent completed jobs</li>
<li>Work in hand and pipeline vs crew and plant capacity</li>
<li>Debtor days, unbilled work, cash forecast</li>
<li>Plant utilisation, owned vs hired, maintenance downtime</li>
<li>Safety: incidents, near misses, ticket expiries</li>
<li>Where a number doesn't exist, that is itself a finding</li></ul></div>
<div class="card"><h3>Systems</h3><ul class="tight">
<li>Map what is used today: accounting (e.g. Xero), job management, scheduling, timesheets, spreadsheets</li>
<li>What is entered twice, and what decisions are made without data</li>
<li>No new system is bought in the first 90 days. Fix process first, then choose tools</li></ul></div></div>
<h2>Output at day 30</h2>
<div class="say">A short written diagnostic for Mick and Dean: <b>what I heard, what the numbers say, and the three to five
priorities I propose</b>, with the evidence behind each. We agree it together before I change anything material.</div>"""


PRIORITIES = [
    ("Know which jobs make money, every week",
     "Growth hides margin problems until the job is finished and it is too late to act. A weekly check of forecast margin "
     "on the larger live jobs lets us fix overruns, chase variations and price the next quote better.",
     "Weekly margin view on every job above an agreed value; variations logged and claimed; a simple post-job review.",
     "/project-control.html", "See the margin early-warning prototype"),
    ("Protect cash: quote to invoice to payment",
     "Growing businesses usually run short of cash before they run short of work. Invoicing promptly at each milestone "
     "and following up debtors weekly is low-cost, fast and visible.",
     "Invoice within an agreed number of days of each milestone; weekly debtor list with owners; 13-week cash forecast.",
     "/reader.html", "See the invoice and remittance reader"),
    ("Match capacity to the pipeline: crews and plant",
     "If Dean wins more work than we can resource, quality and reputation suffer. If we over-hire, margin suffers. "
     "Crews, plant and subcontractors need to be planned a few weeks ahead against the pipeline.",
     "Rolling four-to-six-week resource plan; owned vs hired plant decisions based on utilisation data.",
     "/plant-allocation.html", "See the plant and operator allocation prototype"),
    ("Safety and compliance: confirm the baseline",
     "Non-negotiable. I need to know that tickets, inductions, SWMS and plant servicing are current before I change anything "
     "else on site. It is also the clearest way to show crews that I care about them, not just the numbers.",
     "Expiry register for tickets and inductions; no-one goes on site unqualified; incidents reviewed for causes, not blame.",
     None, None),
    ("An operating rhythm with clear owners",
     "Every other priority depends on it. A short weekly operations meeting, a monthly KPI pack and named owners with dates "
     "turn good intentions into follow-through, and let Mick step back from day-to-day firefighting.",
     "Weekly ops meeting with an action list; monthly business review with Mick and Dean; decision rights written down.",
     "/power-bi.html", "See how the KPI data could feed Power BI or Excel"),
]


def section2() -> str:
    cards = ""
    for i, (title, why, done, link, label) in enumerate(PRIORITIES, 1):
        more = f"<p class='note' style='margin:8px 0 0'><a href='{link}'>{label} →</a></p>" if link else ""
        cards += (f"<div class='card prio'><div class='num'>{i}</div><div><h3>{title}</h3>"
                  f"<p style='margin:0 0 6px'><b>Why it matters:</b> {why}</p>"
                  f"<p style='margin:0'><b>What good looks like by day 90:</b> {done}</p>{more}</div></div>")
    return f"""
<p class="lede">Five priorities, in order. The first four are where a growing contractor typically loses money or takes risk;
the fifth is what makes the other four stick. I would confirm or change this list at day 30, based on what I find.</p>
<div class="grid" style="gap:10px">{cards}</div>
<h2>What I would deliberately not do in 90 days</h2>
<ul class="tight"><li>Restructure the team, or change roles before I understand them</li>
<li>Buy a new ERP or job-management system</li>
<li>Introduce reporting nobody uses. Every report must change a decision</li></ul>"""


def section3() -> str:
    return """
<p class="lede">The business works because of Mick, and it will grow because of the work Dean brings in. My job is to make
both easier, not to add another layer.</p>
<div class="grid k2">
<div class="card"><h3>With Mick (Owner/MD)</h3><ul class="tight">
<li>Understand what he wants to keep close and what he wants to hand over; write the decision rights down by day 30</li>
<li>Weekly one-to-one: no surprises, bad news early, options with a recommendation</li>
<li>Respect the culture he has built; earn the right to change things by delivering first</li>
<li>Free his time from operational firefighting for customers, strategy and the people he wants to develop</li></ul></div>
<div class="card"><h3>With Dean (Marketing &amp; Growth)</h3><ul class="tight">
<li>Monthly sales-and-capacity review: pipeline against crews and plant, so we only promise what we can deliver well</li>
<li>Faster, more accurate quotes using real cost data from completed jobs</li>
<li>Feed delivery back into growth: completed-job case studies, photos, client feedback, repeat and maintenance work</li>
<li>Agree which work we want more of (by margin and fit), not just more work</li></ul></div></div>
<h2>How the three of us work together</h2>
<table><tr><th>Forum</th><th>Who</th><th>Purpose</th></tr>
<tr><td>Weekly one-to-one</td><td>Mick + me</td><td>Priorities, decisions, people, risks</td></tr>
<tr><td>Weekly operations meeting</td><td>Ops leads + me</td><td>This week and next: jobs, crews, plant, safety, actions</td></tr>
<tr><td>Monthly sales and capacity</td><td>Dean + me (+ Mick)</td><td>Pipeline vs capacity, pricing, what to chase</td></tr>
<tr><td>Monthly business review</td><td>Mick, Dean, me</td><td>KPI pack, margin, cash, safety, decisions needed</td></tr></table>
<div class="say">Where we disagree, I will say so in the room, with evidence, and then back the decision outside it.</div>"""


def section4() -> str:
    return """
<div class="grid k3">
<div class="card"><h3><span class="pill RED">Risks</span></h3><ul class="tight">
<li><b>Changing too much, too fast,</b> or looking "corporate" to a hands-on team. <i>Mitigation:</i> listen first, start on
site, small visible fixes</li>
<li><b>Key-person dependency</b> on Mick and a few long-serving staff. <i>Mitigation:</i> document how the critical
work gets done; build depth behind them</li>
<li><b>Growth outrunning capacity:</b> quality, safety and reputation slip. <i>Mitigation:</i> monthly sales and
capacity review</li>
<li><b>Cash squeeze</b> from slow invoicing and upfront materials. <i>Mitigation:</i> 13-week cash forecast</li>
<li><b>Data may be thin or inconsistent.</b> <i>Mitigation:</i> start with what exists; improve capture gradually</li></ul></div>
<div class="card"><h3><span class="pill GREEN">Quick wins (first 60 days)</span></h3><ul class="tight">
<li>Weekly margin snapshot on the five largest live jobs</li>
<li>Invoice-on-milestone rule and a weekly debtor call list</li>
<li>Ticket, licence and induction expiry register</li>
<li>One standard job handover checklist (sales → ops → site)</li>
<li>Fix one or two frustrations crews raise in week one, and tell them it was fixed</li>
<li>Weekly operations meeting with a visible action list</li></ul></div>
<div class="card"><h3><span class="pill AMBER">Opportunities (90 days +)</span></h3><ul class="tight">
<li>Use completed-job costs to price quotes more accurately</li>
<li>Automate supplier invoice processing and coding to cut admin time</li>
<li>Owned vs hired plant decisions from utilisation data</li>
<li>Grow recurring maintenance work for steadier revenue</li>
<li>A single KPI pack in Power BI or Excel from existing systems</li></ul></div></div>
<h2>Working examples</h2>
<p style="max-width:820px">To show how I think about the quick wins and opportunities, I built three small prototypes on
invented data. They are illustrations of the approach, not a proposal to buy or build software in the first 90 days.</p>
<div class="grid k3">
<a class="card" href="/project-control.html" style="text-decoration:none;color:inherit"><h3>Margin early-warning →</h3>
<p class="note" style="margin:0">Forecast margin at completion, exceptions with owners and due dates.</p></a>
<a class="card" href="/reader.html" style="text-decoration:none;color:inherit"><h3>Invoice reader, try it live →</h3>
<p class="note" style="margin:0">Reads a scanned invoice, checks ABN, GST, PO and duplicates, suggests the GL account.</p></a>
<a class="card" href="/plant-allocation.html" style="text-decoration:none;color:inherit"><h3>Plant allocation →</h3>
<p class="note" style="margin:0">Lowest-cost weekly plan across owned plant and hire, gated by tickets and inductions.</p></a>
</div>"""


def section5() -> str:
    return """
<p class="lede">People-centred, practical and calm. A growing, hands-on business needs a leader who is visible on site,
clear about priorities, and steady when things go wrong.</p>
<div class="grid k2">
<div class="card"><h3>How I lead</h3><ul class="tight">
<li><b>Listen before I act.</b> The people doing the work usually know what's wrong</li>
<li><b>Be visible.</b> On site regularly, not just in the office</li>
<li><b>Clarity.</b> Every action has one owner and a date; every meeting ends with decisions</li>
<li><b>Fix the system, not the person.</b> When something goes wrong, ask why the process allowed it</li>
<li><b>Coach.</b> Build the next layer of leaders so the business doesn't rely on a few people</li></ul></div>
<div class="card"><h3>How I make decisions</h3><ul class="tight">
<li>Use data where it exists, judgement where it doesn't, and say which is which</li>
<li>Small, reversible changes first; bigger changes with a business case</li>
<li>Safety and integrity are never traded for speed or margin</li>
<li>Change my mind when the evidence changes, and explain why</li></ul></div></div>
<h2>What the team should say about me at day 90</h2>
<div class="say">"James listened, was on site, fixed things we'd been asking about for years, and we know what's expected of us."</div>"""


QA = [
    ("Communicating with clarity and calmness",
     [("What if Mick disagrees with your priorities at day 30?",
       "Good: that's why the day-30 review exists. I'd ask what he's seeing that I'm not, test it against the evidence, and "
       "adjust. It is his business; my job is to give him the clearest picture and a recommendation, then commit to the "
       "decision."),
      ("What happens if you find the numbers you want don't exist?",
       "That is a finding in itself. I'd start with what can be pulled from accounting and job records, use a simple "
       "spreadsheet before any new system, and fix data capture at the source, usually timesheets and job costing.")]),
    ("Leadership and people",
     [("How would you handle a long-serving supervisor who resists change?",
       "Spend time with them first: they usually have the best knowledge of what really happens on site. Involve them in "
       "designing the fix, start with something that makes their job easier, and give them credit. If resistance continues "
       "after that, have a direct, respectful conversation about expectations."),
      ("You're coming from outside. How will you earn credibility with the crews?",
       "By turning up on site, asking good questions, fixing practical problems quickly, and never pretending to know the "
       "work better than they do. Credibility comes from follow-through.")]),
    ("Judgement, assumptions and ambiguity",
     [("What assumptions have you made in this plan?",
       "That the business is growing and some processes haven't kept pace; that margin and cash visibility can be improved; "
       "that data exists but is scattered. Each is tested in the first 30 days, and the plan changes if any is wrong."),
      ("If you could only do one thing in 90 days, what would it be?",
       "Weekly margin visibility on live jobs, because it protects profit now and improves every future quote. "
       "Safety comes first if the baseline check turns up gaps."),
      ("Where does technology fit in a hands-on business?",
       "Behind the process, never in front of it. The prototypes show what's possible, but nothing gets bought in the first "
       "90 days. Fix the process first, then use simple tools that save crews and office staff time.")]),
    ("Commercial awareness and growth",
     [("How do you balance Dean's growth targets against delivery capacity?",
       "With a monthly sales-and-capacity review: pipeline vs crews, plant and subcontractors over the next few months. "
       "That lets us choose which work to pursue on margin and fit, and gives early warning of when to hire or hire in plant."),
      ("How will we know you've succeeded at 90 days?",
       "Margin visible weekly on the larger jobs, invoicing on time and debtor days trending down, a meeting rhythm that "
       "runs without me pushing it, no safety compliance gaps, and team leaders who bring problems to me early.")]),
]


def qa() -> str:
    blocks = ""
    for theme, items in QA:
        blocks += f"<h2>{theme}</h2>" + "".join(
            f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in items)
    return f"""
<p class="lede">Likely questions in the 20-minute Q&amp;A, grouped by what the panel said they would explore. Each answer is
a short structure to speak to, not a script. Replace the generic points with your own examples.</p>
<div class="qa">{blocks}</div>
<p class="note" style="margin-top:14px">Tip: for any question you didn't expect, use this structure: what I would want to
understand first, what I would do, and how I would know it worked.</p>"""


SECTIONS = [
    ("index.html", "Green Turf — My First 90 Days", "Business Operations Director · final-round presentation", overview),
    ("plan-1.html", "1 · Getting to Know the Business", "Days 1–30: people, process, numbers, systems", section1),
    ("plan-2.html", "2 · Priorities for the First 90 Days", "Five priorities, in order, and why each matters", section2),
    ("plan-3.html", "3 · Partnering with the Owner/MD and the Marketing & Growth Director",
     "How I would work with Mick and Dean", section3),
    ("plan-4.html", "4 · Early Risks, Opportunities and Quick Wins", "What could go wrong, and what we can win early",
     section4),
    ("plan-5.html", "5 · My Leadership Approach", "How I lead, decide and earn trust", section5),
    ("qa.html", "Q&A Preparation", "Likely questions and how I would answer them", qa),
]

KEYS = """<script>
document.addEventListener('keydown', e => {
  if (e.target.closest('input,textarea,select') || e.metaKey || e.ctrlKey || e.altKey) return;
  const a = document.querySelector(e.key === 'ArrowRight' ? '.pager a.r' : e.key === 'ArrowLeft' ? '.pager a.l' : null);
  if (a) location.href = a.href;
});
</script>"""


def pages(nav_for) -> dict[str, str]:
    """Return {filename: html}. nav_for(filename) gives the site navigation for that page."""
    out = {}
    for i, (fname, title, sub, fn) in enumerate(SECTIONS):
        prev_ = SECTIONS[i - 1] if i > 0 else None
        next_ = SECTIONS[i + 1] if i + 1 < len(SECTIONS) else None
        pager = "<div class='pager'>"
        pager += (f"<a class='l' href='/{prev_[0]}'><small>← Previous</small>{esc(prev_[1])}</a>" if prev_ else "<span></span>")
        pager += (f"<a class='r' href='/{next_[0]}'><small>Next →</small>{esc(next_[1])}</a>" if next_ else "<span></span>")
        pager += "</div>"
        count = f"<p class='slidecount'>Section {i + 1} of {len(SECTIONS)} · use ← → keys to move between sections</p>"
        out[fname] = shell(title, sub, count + fn() + pager + KEYS, nav_for(fname))
    return out
