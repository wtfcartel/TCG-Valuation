"""The "First 90 Days" presentation, as navigable web pages.

Built directly on the Green Turf final-round brief ("Your First 90 Days at Green Turf"): one page per area the
brief asks the presentation to cover, in the brief's order, plus a Q&A page organised by the four things the brief
says the panel will explore. Every page quotes the part of the brief it answers and shows which of the brief's
assessment criteria it addresses.

Guiding principle, applied on every page: the business does not want dramatic change. The committed pipeline of
work already won is delivered first (Level 1). Light disciplines are added only where they help that delivery
(Level 2). Strategic change is prepared as recommendations for after the pipeline is delivered (Level 3).

Every page has previous/next links and responds to the left/right arrow keys, so it can be presented directly.
Nothing here claims knowledge of Green Turf's internal performance.
"""

from __future__ import annotations

from common.report import CSS, esc

PLAN_CSS = """
.lede{font-size:16px;max-width:840px;margin:0 0 14px}
.phase{border-top:4px solid var(--green)}.phase.p2{border-top-color:#5b8f3e}.phase.p3{border-top-color:#8bb04a}
.phase .when{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.prio{display:grid;grid-template-columns:44px 1fr;gap:12px}.prio .num{font-size:26px;font-weight:700;color:var(--green)}
ul.tight{margin:6px 0 0;padding-left:18px}ul.tight li{margin:4px 0}
.pager{display:flex;justify-content:space-between;gap:10px;margin-top:26px}
.pager span{flex:1}.pager a{flex:1;padding:12px 14px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink);text-decoration:none}
.pager a:hover{border-color:var(--green)}.pager .r{text-align:right}.pager small{display:block;color:var(--muted)}
.say{background:var(--green-l);border-left:4px solid var(--green);padding:10px 14px;border-radius:0 6px 6px 0;margin:14px 0;max-width:880px}
.brief{background:#fff;border:1px dashed #b9c4bb;border-radius:8px;padding:10px 14px;margin:0 0 14px;font-size:13px}
.brief q{font-style:italic}.brief .crit{margin-top:6px}
.crit span{display:inline-block;font-size:11.5px;padding:1px 8px;border-radius:10px;background:#eef1ec;color:#33433a;margin:2px 4px 0 0}
.lv{display:inline-block;font-size:11px;font-weight:700;padding:1px 7px;border-radius:9px;margin-right:6px;vertical-align:1px;white-space:nowrap}
.L1{background:#2f6b3f;color:#fff}.L2{background:#cfe3c9;color:#23502f}.L3{background:#eceeea;color:#555;border:1px dashed #aab3ab}
.levels .card{border-top:4px solid var(--green)}.levels .c2{border-top-color:#8bb04a}.levels .c3{border-top-color:#b8bfb9}
.qa details{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:8px 0}
.qa summary{cursor:pointer;font-weight:600}.qa details p{margin:8px 0 0}
.slidecount{font-size:12px;color:var(--muted)}
@media(max-width:800px){.k4,.k3,.k2{grid-template-columns:1fr}.pager{flex-direction:column}.lede{font-size:15px}}
"""

PLAN_BANNER = ("Guiding principle: no dramatic change. The pipeline of work Green Turf has already committed to is "
               "delivered first. Anything new is added only if it helps that delivery, and strategic change waits until "
               "the pipeline is complete. Written from outside the business, so it is tested and adjusted in the first 30 days.")

# The brief's assessment criteria, verbatim ("What We Will Be Looking For").
C_PRIO = "Clear prioritisation"
C_JUDG = "Strong operational judgement"
C_SEQ = "Ability to diagnose and sequence change"
C_LEAD = "Leadership maturity"
C_COMM = "Commercial awareness"
C_FIT = "Fit with Green Turf's culture and growth stage"
C_CALM = "Ability to communicate with clarity and calmness"
ALL_CRITERIA = [C_PRIO, C_JUDG, C_SEQ, C_LEAD, C_COMM, C_FIT, C_CALM]


def lv(n: int) -> str:
    return f"<span class='lv L{n}'>Level {n}</span>"


def brief(asks: str, criteria: list[str]) -> str:
    tags = "".join(f"<span>{esc(c)}</span>" for c in criteria)
    return (f"<div class='brief'><b>The brief asks:</b> <q>{asks}</q>"
            f"<div class='crit'><b style='font-size:12px'>Assessed against:</b> {tags}</div></div>")


def shell(title: str, subtitle: str, body: str, nav: str, extra_css: str = "") -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<style>{CSS}{PLAN_CSS}{extra_css}</style></head>
<body><div class="wrap">{nav}<header><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></header>
<div class="banner" style="background:#eef5ef;border-color:#b9d3bf">{esc(PLAN_BANNER)}</div>{body}
<footer>James Fischer-Myall · Business Operations Director, final round · Green Turf</footer>
</div></body></html>"""


LEVELS = f"""<div class="grid k3 levels">
<div class="card"><h3>{lv(1)} Deliver what is already won</h3><p style="margin:0">The first job. Help every committed job in
the current pipeline finish safely, on time and at the margin it was quoted at. Changes are limited to clearing blockers on
live work.</p><p class="note" style="margin:6px 0 0">Days 1–90, and the measure of success.</p></div>
<div class="card c2"><h3>{lv(2)} Light disciplines that support delivery</h3><p style="margin:0">Only where they help the
pipeline land and cost the team very little: a weekly check-in on live jobs, a margin snapshot, invoicing as milestones
complete, a ticket and induction register. Existing tools, no new systems.</p>
<p class="note" style="margin:6px 0 0">Introduced gradually from about day 30, with the team.</p></div>
<div class="card c3"><h3>{lv(3)} Strategic change, later</h3><p style="margin:0">Systems, automation, reporting tools,
structure, capacity and growth plans. Prepared as recommendations for Mick and Dean, to decide on once the pipeline is
delivered. Not implemented in the first 90 days.</p><p class="note" style="margin:6px 0 0">Proposed at day 90; timing is
Mick's call.</p></div></div>"""


# --- Section content ---------------------------------------------------------------------------------------------

def overview() -> str:
    phases = [
        ("p1", "Days 1–30", "Learn the business through its live work",
         ["Agree with Mick the list of committed jobs and what \"done\" means for each",
          "Meet every team, on site and in the office; listen more than talk",
          "Understand each live job: status, risks, owner, what is in the way",
          "Change nothing, except clearing blockers on live jobs",
          "Day 30: share what I found with Mick and Dean and confirm the plan"]),
        ("p2", "Days 31–60", "Help the pipeline land",
         ["Short weekly review of every live job with the people running them",
          "Remove obstacles: materials, plant, crews, approvals, client decisions",
          "Introduce Level 2 disciplines only where they help delivery",
          "Invoice each milestone as it completes"]),
        ("p3", "Days 61–90", "Consolidate and recommend",
         ["Pipeline delivered, or on a clear track to completion",
          "Capture lessons from completed jobs while they are fresh",
          "Write up Level 3 options with costs and benefits",
          "Day 90: review with Mick and Dean; they decide what, if anything, comes next and when"]),
    ]
    cards = "".join(
        f"<div class='card phase {c}'><div class='when'>{w}</div><h3 style='margin-top:4px'>{t}</h3>"
        f"<ul class='tight'>{''.join(f'<li>{x}</li>' for x in items)}</ul></div>" for c, w, t, items in phases)
    mapping = [
        ("1. How You Would Get to Know the Business", "plan-1.html", "Learn the business through the live pipeline"),
        ("2. Your Priorities for the First 90 Days (top 3–5, and why they matter)", "plan-2.html",
         "Five priorities, led by delivering committed work"),
        ("3. How You Would Partner With the Owner/MD and Marketing & Growth Director", "plan-3.html",
         "Agree the pipeline with Mick; protect it with Dean"),
        ("4. Early Risks, Opportunities & Quick Wins", "plan-4.html", "Biggest risk is distraction from delivery"),
        ("5. Your Leadership Approach", "plan-5.html", "A steady hand: listen, support, then improve"),
        ("Q&A: reasoning, assumptions, challenge or ambiguity, adapting to new information", "qa.html",
         "Prepared answers in the brief's four areas"),
    ]
    rows = "".join(f"<tr><td>{esc(b)}</td><td><a href='/{u}'>{esc(a)}</a></td></tr>" for b, u, a in mapping)
    crit = [
        (C_PRIO, "One clear first priority: finish the work already won. Everything else is ranked behind it."),
        (C_JUDG, "Change is limited to what helps live jobs; nothing is introduced that distracts crews or the office."),
        (C_SEQ, "Three levels in a set order: deliver, then light disciplines, then strategic change after the pipeline."),
        (C_LEAD, "Listening before acting; earning trust by helping, not by changing."),
        (C_COMM, "Committed work is revenue and reputation already won. Protecting its margin and cash comes first."),
        (C_FIT, "Respects a hands-on business that does not want dramatic change, and its current growth stage."),
        (C_CALM, "One principle, one sequence, the same on every page."),
    ]
    crit_rows = "".join(f"<tr><td style='width:34%'><b>{esc(c)}</b></td><td>{t}</td></tr>" for c, t in crit)
    return f"""
{brief("Prepare a presentation outlining how you would approach your first 90 days as Business Operations Director.",
       ALL_CRITERIA)}
<p class="lede">Green Turf has a pipeline of work it has already committed to. My first 90 days are about helping the team
deliver that pipeline well, without dramatic change. Improvements come in small steps, and only where they help that
delivery. Bigger changes are prepared as options for Mick and Dean to decide on once the pipeline is complete.</p>
<div class="say"><b>In one line:</b> finish what we have already promised, protect its margin and cash, and earn the right
to suggest change by helping first.</div>
<h2>How every part of this plan is sequenced</h2>{LEVELS}
<h2>The 90 days at a glance</h2><div class="grid k3">{cards}</div>
<h2>How this answers the brief</h2>
<table><tr><th>What the brief asks the presentation to cover</th><th>Where it is answered</th></tr>{rows}</table>
<h2>What the panel said it will look for, and where this plan shows it</h2><table>{crit_rows}</table>
<h2>What I will measure myself against at day 90</h2>
<div class="grid k4">
<div class="card kpi"><div class="l">{lv(1)} Delivery</div><div class="v" style="font-size:18px">Pipeline delivered</div>
<div class="s">or on a clear track: on time, safely, at quoted margin</div></div>
<div class="card kpi"><div class="l">{lv(1)} Stability</div><div class="v" style="font-size:18px">No disruption</div>
<div class="s">crews and office not distracted by change</div></div>
<div class="card kpi"><div class="l">{lv(2)} Cash</div><div class="v" style="font-size:18px">Milestones invoiced</div>
<div class="s">promptly as they complete</div></div>
<div class="card kpi"><div class="l">{lv(3)} Next stage</div><div class="v" style="font-size:18px">Options agreed</div>
<div class="s">Mick and Dean decide what comes next, and when</div></div></div>
<p class="note">Agenda: about 3, 5, 3, 4 and 3 minutes across the five sections (15–20 minutes), then 20 minutes of Q&amp;A.</p>"""


def section1() -> str:
    return f"""
{brief("How You Would Get to Know the Business", [C_JUDG, C_SEQ, C_FIT])}
<p class="lede">I would get to know Green Turf through the work it is doing right now. Learning through the live pipeline
means I learn quickly, I don't pull people away from delivery, and I can start helping straight away.</p>
<div class="grid k2">
<div class="card"><h3>{lv(1)} Start with the committed pipeline</h3><ul class="tight">
<li>Week one: sit down with Mick and list every committed job, its client, value, stage, deadline and owner</li>
<li>Agree what "done" means for each: handover, sign-off, final invoice, retention release</li>
<li>Walk each live job with the person running it: what is going well, what is at risk, what is in their way</li>
<li>Note blockers I can clear without changing how anyone works</li></ul></div>
<div class="card"><h3>{lv(1)} People</h3><ul class="tight">
<li><b>Mick:</b> the history, what must not change, what he worries about, and how he likes to be kept informed</li>
<li><b>Dean:</b> what has been promised to clients, what is in the pipeline, and what clients say</li>
<li>One-to-ones with managers, supervisors and the office team, on their schedule, not in a workshop</li>
<li>Days on site with crews. Same three questions everywhere: what works, what gets in your way, what should I leave
alone</li></ul></div>
<div class="card"><h3>{lv(1)} Numbers that exist today</h3><ul class="tight">
<li>For each live job: quoted vs actual cost so far, variations, invoiced and still to invoice</li>
<li>Cash: debtors, and when the committed work will turn into cash</li>
<li>Safety: tickets, inductions and incidents on current sites</li>
<li>I would use whatever reports already exist. Where a number doesn't exist, I note it for later rather than build
something new now</li></ul></div>
<div class="card"><h3>{lv(3)} Noted for later, not acted on</h3><ul class="tight">
<li>Duplicated data entry, spreadsheets, manual approvals</li>
<li>System and reporting gaps</li>
<li>Structure and capacity questions</li>
<li>These go on a list for the day-90 recommendations. They are not changed while the pipeline is being delivered</li>
</ul></div></div>
<h2>Output at day 30</h2>
<div class="say">A short note for Mick and Dean: <b>the state of each committed job, the risks to finishing it well, what I
am doing to help, and what I have noted for later.</b> We agree it together. Nothing material changes without that
agreement.</div>"""


PRIORITIES = [
    (1, "Deliver the existing pipeline of committed work",
     "This is work Green Turf has already won: revenue, client relationships and reputation that are already promised. "
     "The business has been clear that this comes before any strategic change, and I agree. Finishing it well is what "
     "funds and earns everything after it.",
     "Every committed job delivered, or on a clear and agreed track: on time, to quality, safely, and signed off by the "
     "client.", None, None),
    (1, "Keep every live site safe and compliant",
     "Non-negotiable, and part of delivering well. I would confirm that tickets, inductions, SWMS and plant servicing are "
     "current on each live job, using whatever records already exist. Fixing a gap here is not a change programme; it is "
     "basic care for the crews.",
     "No one on a live site without the right tickets and inductions; any gaps closed quickly and quietly.", None, None),
    (2, "Protect the margin and cash of the committed work",
     "A job finished late or over cost loses what it was won for. A light weekly look at cost-to-date against the quote "
     "on the larger live jobs, variations claimed, and each milestone invoiced promptly protects the value of the "
     "pipeline without changing how the team works.",
     "Weekly margin snapshot on the larger live jobs; variations captured; each milestone invoiced as it completes.",
     "/project-control.html", "See an illustration of a margin snapshot (Level 3 tool, for later)"),
    (2, "A light weekly rhythm to support delivery",
     "A short weekly check-in on live jobs, one owner and one date per action, using the tools already in place. It "
     "helps the pipeline land and takes day-to-day chasing off Mick. Nothing more formal than that in the first 90 days.",
     "Weekly check-in held, actions followed up, and Mick less pulled into firefighting.", None, None),
    (3, "Prepare, not impose, the next stage",
     "While the pipeline is delivered I would keep a list of what could be improved: systems, reporting, automation, "
     "capacity planning, structure. At day 90 I would set these out with costs and benefits. Mick and Dean decide what "
     "happens, and when, once the committed work is complete.",
     "A short, costed list of options agreed with Mick and Dean. Nothing implemented in the first 90 days.",
     "/prototypes.html", "See illustrations of possible later improvements"),
]


def section2() -> str:
    cards = ""
    for i, (level, title, why, done, link, label) in enumerate(PRIORITIES, 1):
        more = f"<p class='note' style='margin:8px 0 0'><a href='{link}'>{label} →</a></p>" if link else ""
        cards += (f"<div class='card prio'><div class='num'>{i}</div><div><h3>{lv(level)}{title}</h3>"
                  f"<p style='margin:0 0 6px'><b>Why it matters:</b> {why}</p>"
                  f"<p style='margin:0'><b>What good looks like by day 90:</b> {done}</p>{more}</div></div>")
    return f"""
{brief("Your Priorities for the First 90 Days. Outline the top 3–5 priorities you would focus on, and why they matter.",
       [C_PRIO, C_COMM, C_SEQ])}
<p class="lede">Five priorities, in strict order. The first two are about finishing the work already won. The next two
are light disciplines that protect it. The fifth prepares the next stage without starting it.</p>
<div class="grid" style="gap:10px">{cards}</div>
<h2>What I would deliberately not do in the first 90 days</h2>
<ul class="tight"><li>Restructure the team, or change roles or reporting lines</li>
<li>Introduce new systems, software or reporting the team has to learn while delivering</li>
<li>Change how crews work on live jobs, except to fix a safety gap</li>
<li>Take on new commitments that would stretch delivery of the existing pipeline, without a capacity check with Dean and
Mick</li></ul>"""


def section3() -> str:
    return f"""
{brief("How You Would Partner With the Owner/MD and Marketing & Growth Director", [C_LEAD, C_FIT, C_COMM])}
<p class="lede">The business works because of Mick, and it will grow because of the work Dean brings in. In the first 90
days I am there to help both of them get the committed pipeline delivered, not to add a layer of process.</p>
<div class="grid k2">
<div class="card"><h3>With Mick (Owner/MD)</h3><ul class="tight">
<li>{lv(1)} Agree, in week one, the list of committed jobs and what "done" looks like for each</li>
<li>{lv(1)} Understand what he wants to keep close and what he wants help with; respect what he has built</li>
<li>{lv(1)} Weekly one-to-one: no surprises, bad news early, options with a recommendation</li>
<li>{lv(2)} Take day-to-day chasing on live jobs off his plate so he can focus on clients and the business</li>
<li>{lv(3)} At day 90, give him the options for the next stage, so the timing is his decision</li></ul></div>
<div class="card"><h3>With Dean (Marketing &amp; Growth)</h3><ul class="tight">
<li>{lv(1)} Understand exactly what has been promised to each client in the pipeline, and keep him informed on delivery</li>
<li>{lv(1)} Protect the pipeline: check capacity before new work is committed that could stretch current jobs</li>
<li>{lv(2)} Turn completed jobs into proof: photos, client feedback and case studies he can use</li>
<li>{lv(3)} After the pipeline: use real job costs to sharpen quotes, and plan capacity ahead of growth together</li>
</ul></div></div>
<h2>How the three of us work together in the first 90 days</h2>
<table><tr><th>Forum</th><th>Who</th><th>Purpose</th></tr>
<tr><td>Weekly one-to-one</td><td>Mick + me</td><td>Pipeline status, decisions needed, risks, people</td></tr>
<tr><td>Weekly live-jobs check-in</td><td>Job leads + me</td><td>This week and next on each committed job: blockers and
actions</td></tr>
<tr><td>Fortnightly pipeline catch-up</td><td>Dean + me</td><td>What clients expect, what is coming, capacity before new
commitments</td></tr>
<tr><td>Day-30 and day-90 reviews</td><td>Mick, Dean, me</td><td>Confirm the plan; then agree what comes next, and when</td>
</tr></table>
<div class="say">Where we disagree, I will say so in the room, with evidence, and then back the decision outside it.</div>"""


def section4() -> str:
    return f"""
{brief("Early Risks, Opportunities & Quick Wins", [C_JUDG, C_COMM, C_SEQ])}
<div class="grid k3">
<div class="card"><h3><span class="pill RED">Risks</span></h3><ul class="tight">
<li><b>Change that distracts from delivery.</b> The biggest risk I bring. <i>Mitigation:</i> no new systems or
restructures in 90 days; Level 2 only where it helps live jobs</li>
<li><b>A committed job slipping</b> on time, cost or quality. <i>Mitigation:</i> weekly live-jobs check-in; clear blockers
fast</li>
<li><b>Over-committing:</b> new work stretching current crews and plant. <i>Mitigation:</i> capacity check with Dean before
new commitments</li>
<li><b>Cash gaps</b> if milestones aren't invoiced promptly. <i>Mitigation:</i> invoice as each milestone completes</li>
<li><b>Losing trust</b> by looking "corporate". <i>Mitigation:</i> listen first, be on site, help before suggesting</li>
</ul></div>
<div class="card"><h3><span class="pill GREEN">Quick wins</span></h3>
<p class="note" style="margin:0 0 4px">Only things that help the current pipeline, using existing tools:</p><ul class="tight">
<li>{lv(1)} Clear the blockers job leads raise in week one, and tell them it is done</li>
<li>{lv(1)} Confirm tickets and inductions for everyone on live sites</li>
<li>{lv(2)} Invoice each milestone as it completes; chase overdue debtors weekly</li>
<li>{lv(2)} Capture variations on live jobs as they happen</li>
<li>{lv(2)} One short weekly check-in on live jobs, with owners and dates</li></ul></div>
<div class="card"><h3><span class="pill AMBER">Opportunities, after the pipeline</span></h3><ul class="tight">
<li>{lv(3)} Use completed-job costs to price future quotes more accurately</li>
<li>{lv(3)} Plan crews and plant ahead of the next pipeline</li>
<li>{lv(3)} Reduce manual admin, such as supplier invoice processing</li>
<li>{lv(3)} A simple KPI pack from existing systems</li>
<li>{lv(3)} Grow recurring maintenance work from completed jobs</li></ul>
<p class="note" style="margin:6px 0 0">Proposed at day 90. Mick and Dean decide the timing.</p></div></div>
<h2>Illustrations of the later opportunities</h2>
<p style="max-width:840px">To show how I think about the Level 3 opportunities, I built three small prototypes on invented
data. They are <b>not</b> proposals for the first 90 days. They show what could be considered once the committed pipeline is
delivered, if Mick and Dean want to.</p>
<div class="grid k3">
<a class="card" href="/project-control.html" style="text-decoration:none;color:inherit"><h3>{lv(3)} Margin early-warning →</h3>
<p class="note" style="margin:0">Forecast margin at completion, exceptions with owners and due dates.</p></a>
<a class="card" href="/reader.html" style="text-decoration:none;color:inherit"><h3>{lv(3)} Invoice reader →</h3>
<p class="note" style="margin:0">Reads a scanned invoice, checks ABN, GST, PO and duplicates, suggests the GL account.</p></a>
<a class="card" href="/plant-allocation.html" style="text-decoration:none;color:inherit"><h3>{lv(3)} Plant allocation →</h3>
<p class="note" style="margin:0">Lowest-cost weekly plan across owned plant and hire, gated by tickets and inductions.</p></a>
</div>"""


def section5() -> str:
    return f"""
{brief("Your Leadership Approach", [C_LEAD, C_FIT, C_CALM])}
<p class="lede">A steady hand. Green Turf is a hands-on business with work to deliver and no appetite for dramatic change.
It needs someone who supports the people doing that work, keeps things calm, and improves things in the right order.</p>
<div class="grid k2">
<div class="card"><h3>How I lead</h3><ul class="tight">
<li><b>Help first, change later.</b> Earn the right to suggest improvements by making delivery easier</li>
<li><b>Listen before I act.</b> The people doing the work usually know what is wrong, and what to leave alone</li>
<li><b>Be visible.</b> On site regularly, not just in the office</li>
<li><b>Clarity.</b> Every action has one owner and a date</li>
<li><b>Fix the system, not the person.</b> When something goes wrong, ask why the process allowed it</li></ul></div>
<div class="card"><h3>How I make decisions</h3><ul class="tight">
<li>Ask first: does this help us deliver what we have committed to? If not, it waits</li>
<li>Small, reversible steps; nothing that unsettles crews mid-job</li>
<li>Safety and integrity are never traded for speed or margin</li>
<li>Use data where it exists and judgement where it doesn't, and say which is which</li>
<li>Change my mind when the evidence changes, and explain why</li></ul></div></div>
<h2>What the team should say at day 90</h2>
<div class="say">"James helped us get our jobs finished, sorted out things that were in our way, and didn't change things
for the sake of it."</div>"""


QA = [
    ("Your reasoning", [
        ("Why put delivering the existing pipeline ahead of improvement?",
         "Because it is work already won: revenue, client relationships and reputation that are already promised. The "
         "business has said it wants that pipeline completed before strategic change, and I agree. Improvements made "
         "mid-delivery risk distracting the people doing the work. Finishing well also gives me the credibility and the "
         "evidence to recommend the right changes afterwards."),
        ("If you could only do one thing in 90 days, what would it be?",
         "Make sure every committed job finishes well: on time, safely, and at the margin it was quoted at. If the "
         "safety check on live sites turns up a gap, that comes first."),
        ("Why the order you have chosen?",
         "Deliver first, protect margin and cash second, light rhythm third, and prepare the next stage last. Each step "
         "only goes ahead if it helps the one before it."),
    ]),
    ("Your assumptions", [
        ("What assumptions have you made?",
         "That there is a committed pipeline to deliver; that the business wants steadiness rather than dramatic change; "
         "and that some information is scattered across people and spreadsheets. I test each in the first 30 days and "
         "adjust the plan at the day-30 review with Mick and Dean."),
        ("What if the numbers you want don't exist?",
         "In the first 90 days I work with what exists and ask the people running the jobs. I note the gaps for the "
         "day-90 recommendations rather than building new reporting while the team is delivering."),
    ]),
    ("How you handle challenge or ambiguity", [
        ("We don't want dramatic change. How does your plan reflect that?",
         "It is the organising principle. Level 1 is delivering what is already won. Level 2 is a few light disciplines, "
         "using existing tools, only where they help that delivery. Level 3, systems, structure and growth plans, is "
         "prepared as options and not implemented in 90 days. You decide what happens next, and when."),
        ("What if Mick disagrees with your priorities at day 30?",
         "That is why the day-30 review exists. I would ask what he is seeing that I am not, test it against what I have "
         "found on the live jobs, and adjust. It is his business; my job is to give him the clearest picture and a "
         "recommendation, then commit to the decision."),
        ("How would you handle a long-serving supervisor who is wary of you?",
         "By helping them deliver their jobs first: clearing what is in their way, without changing how they work. "
         "Their knowledge is exactly what I need. Trust comes from follow-through, not from new processes."),
        ("Dean wins a big new job that would stretch current crews. What do you do?",
         "Welcome it, then do a quick capacity check with Dean and Mick before committing dates: crews, plant, "
         "subcontractors, and the effect on jobs already promised. We agree a start date that protects existing clients, "
         "or what we would need to bring in."),
    ]),
    ("How you adapt to new information", [
        ("What would make you change this plan?",
         "A committed job in trouble, a safety gap, or a cash issue. Any of those moves to the top straight away. Or "
         "Mick and Dean telling me a Level 3 item is more urgent than I think, in which case we agree how to do it "
         "without disrupting delivery."),
        ("How will we know you've succeeded at 90 days?",
         "The committed pipeline delivered, or on a clear track, safely and at quoted margin; no disruption to crews or "
         "the office; milestones invoiced promptly; and an agreed list of next-stage options, with the timing in your "
         "hands."),
        ("Where does technology fit?",
         "Later, and behind the process. The prototypes show what could be considered once the pipeline is delivered. "
         "Nothing new is introduced in the first 90 days."),
    ]),
]


def qa() -> str:
    blocks = ""
    for theme, items in QA:
        blocks += f"<h2>{theme}</h2>" + "".join(
            f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in items)
    return f"""
{brief("Following your presentation, we will ask questions to explore: your reasoning; your assumptions; how you handle "
       "challenge or ambiguity; how you adapt your approach based on new information.", [C_CALM, C_LEAD, C_JUDG])}
<p class="lede">Likely questions, grouped under the four areas the brief says the Q&amp;A will explore. Each answer comes
back to the same principle: deliver the committed pipeline first, then add complexity only when it helps.</p>
<div class="qa">{blocks}</div>
<p class="note" style="margin-top:14px">For any question you didn't expect: say what you would want to understand first,
what you would do, and how you would know it worked. Then check it against the principle: does this help us deliver
what we have already committed to?</p>"""


SECTIONS = [
    ("index.html", "Green Turf — My First 90 Days", "Business Operations Director · final-round presentation", overview),
    ("plan-1.html", "1 · How I Would Get to Know the Business", "Learning the business through the committed pipeline",
     section1),
    ("plan-2.html", "2 · My Priorities for the First 90 Days", "Five priorities, led by delivering committed work",
     section2),
    ("plan-3.html", "3 · Partnering with the Owner/MD and the Marketing & Growth Director",
     "How I would work with Mick and Dean", section3),
    ("plan-4.html", "4 · Early Risks, Opportunities and Quick Wins",
     "Protect delivery now; hold bigger opportunities for later", section4),
    ("plan-5.html", "5 · My Leadership Approach", "A steady hand: help first, improve later", section5),
    ("qa.html", "Q&A Preparation", "The brief's four Q&A areas, with prepared answers", qa),
]

KEYS = """<script>
document.addEventListener('keydown', e => {
  if (e.target.closest('input,textarea,select') || e.metaKey || e.ctrlKey || e.altKey) return;
  const sel = e.key === 'ArrowRight' ? '.pager a.r' : e.key === 'ArrowLeft' ? '.pager a.l' : null;
  const a = sel && document.querySelector(sel);
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
