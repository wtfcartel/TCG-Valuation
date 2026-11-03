"""The "First 90 Days" presentation, as navigable web pages.

Built directly on the Green Turf final-round brief ("Your First 90 Days at Green Turf"): one page per area the
brief asks the presentation to cover, in the brief's order, plus two supporting pages (season timing, and
assumptions and what would change the plan) covering the areas
the brief says the panel will explore. Page titles follow the brief's own section headings.

Guiding principle, applied on every page: the business does not want dramatic change. The committed pipeline of
work already won is delivered first (Level 1). Light controls are added only where they help that delivery
(Level 2). Strategic change is prepared as recommendations for after the pipeline is delivered (Level 3).

Every page has previous/next links and responds to the left/right arrow keys, so it can be presented directly.
Nothing here claims knowledge of Green Turf's internal performance.
"""

from __future__ import annotations

from common.report import CSS, esc
from webbuild.season import section as season_section
from webbuild.integrations import section as integrations_section
from webbuild.review import build as review_page

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

PLAN_BANNER = ("Guiding principle: Green Turf doesn't want dramatic change. The existing pipeline of mandates gets "
               "delivered first. Anything new is added only where it helps that delivery, and strategic change waits "
               "until the pipeline is complete. I've written this from outside the business, so I'd test it and adjust "
               "it in the first 30 days.")

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
    """Kept so section bodies stay readable; the brief's wording now lives in each page title, not a quoted box."""
    return ""


def shell(title: str, subtitle: str, body: str, nav: str, extra_css: str = "") -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<style>{CSS}{PLAN_CSS}{extra_css}</style></head>
<body><div class="wrap">{nav}<header><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></header>
<div class="banner" style="background:#eef5ef;border-color:#b9d3bf">{esc(PLAN_BANNER)}</div>{body}
<footer>James Fischer-Myall | Business Operations Director, final round | Green Turf</footer>
</div></body></html>"""


LEVELS = f"""<div class="grid k3 levels">
<div class="card"><h3>{lv(1)} Deliver the existing mandates</h3><p style="margin:0">My first job. Every committed job in
the current pipeline finishes safely, on time and at the margin it was quoted at. The only changes I'd make are to clear
blockers on live work.</p><p class="note" style="margin:6px 0 0">Days 1 to 90, and how I'd want to be measured.</p></div>
<div class="card c2"><h3>{lv(2)} Light controls that support delivery</h3><p style="margin:0">Only where they help the
pipeline land and cost the team very little: a weekly check-in on live jobs, a margin snapshot, invoicing as milestones
complete, and a ticket and induction register. Existing tools, no new systems.</p>
<p class="note" style="margin:6px 0 0">Introduced gradually from about day 30, with the team.</p></div>
<div class="card c3"><h3>{lv(3)} Strategic change, once the pipeline is delivered</h3><p style="margin:0">Systems,
automation, reporting, structure, capacity and growth planning. I'd prepare these as costed recommendations for Mick and
Dean. Nothing here gets implemented in the first 90 days.</p><p class="note" style="margin:6px 0 0">Put forward at day 90;
the timing is Mick's call.</p></div></div>"""


# --- Section content ---------------------------------------------------------------------------------------------

def overview() -> str:
    phases = [
        ("p1", "Days 1 to 30", "Learn the business through the live work",
         ["Sit down with Mick and agree the list of committed jobs and what \"complete\" means for each",
          "Meet every team, on site and in the office, and mostly listen",
          "Understand each live job: where it's at, the risks, who owns it and what's in the way",
          "Change nothing, other than clearing blockers on live jobs",
          "Day 30: take Mick and Dean through what I've found and confirm the plan"]),
        ("p2", "Days 31 to 60", "Get the pipeline over the line",
         ["Short weekly review of every live job with the people running them",
          "Clear obstacles: materials, plant, crews, approvals, client decisions",
          "Bring in Level 2 controls only where they help delivery",
          "Invoice each milestone as it's completed"]),
        ("p3", "Days 61 to 90", "Close out and recommend",
         ["Pipeline delivered, or on a clear and agreed path to completion",
          "Capture the lessons from completed jobs while they're fresh",
          "Write up the Level 3 options with costs and benefits",
          "Day 90: review with Mick and Dean, and they decide what comes next and when"]),
    ]
    cards = "".join(
        f"<div class='card phase {c}'><div class='when'>{w}</div><h3 style='margin-top:4px'>{t}</h3>"
        f"<ul class='tight'>{''.join(f'<li>{x}</li>' for x in items)}</ul></div>" for c, w, t, items in phases)
    agenda = [
        ("plan-1.html", "1 | How I would get to know the business", "3 min"),
        ("plan-2.html", "2 | My priorities for the first 90 days", "5 min"),
        ("plan-3.html", "3 | Partnering with Mick and Dean", "3 min"),
        ("plan-4.html", "4 | Early risks, opportunities and quick wins", "4 min"),
        ("plan-5.html", "5 | My leadership approach", "3 min"),
        ("season.html", "Supporting: timing across the season", "if time allows"),
        ("assumptions.html", "Supporting: assumptions and what would change the plan", "if time allows"),
    ]
    rows = "".join(f"<tr><td><a href='/{u}'>{esc(t)}</a></td><td class='n'>{m}</td></tr>" for u, t, m in agenda)
    return f"""
<p class="lede">The role is about growth, compliance and governance, and modernisation that push through the existing
mandate and are additive to future strategy once the current strategic plan is executed. My first 90 days would be about
helping the team deliver the existing pipeline of mandates well, without dramatic change. Improvements come in small steps and only
where they help delivery. Anything bigger gets prepared as options for Mick and Dean to consider once the pipeline is
complete.</p>
<div class="say">Deliver what's already been promised, protect its margin and cash, and only then look at what should
change.</div>
<h2>How the plan is sequenced</h2>{LEVELS}
<h2>The 90 days at a glance</h2><div class="grid k3">{cards}</div>
<h2>Agenda</h2>
<table><tr><th>Section</th><th class="n">Time</th></tr>{rows}</table>
<h2>How I'd measure myself at day 90</h2>
<div class="grid k4">
<div class="card kpi"><div class="l">{lv(1)} Delivery</div><div class="v" style="font-size:18px">Pipeline delivered</div>
<div class="s">or on an agreed path: on time, safely, at quoted margin</div></div>
<div class="card kpi"><div class="l">{lv(1)} Stability</div><div class="v" style="font-size:18px">No disruption</div>
<div class="s">crews and office kept on the work</div></div>
<div class="card kpi"><div class="l">{lv(2)} Cash</div><div class="v" style="font-size:18px">Milestones invoiced</div>
<div class="s">as they're completed</div></div>
<div class="card kpi"><div class="l">{lv(3)} Next stage</div><div class="v" style="font-size:18px">Options agreed</div>
<div class="s">Mick and Dean decide what comes next, and when</div></div></div>
"""


def section1() -> str:
    return f"""
{brief("How You Would Get to Know the Business", [C_JUDG, C_SEQ, C_FIT])}
<p class="lede">I'd get to know Green Turf through the work it's doing right now. That way I learn quickly, I don't pull
people off delivery to brief me, and I can start being useful straight away.</p>
<div class="grid k2">
<div class="card"><h3>{lv(1)} Start with the committed pipeline</h3><ul class="tight">
<li>Week one: sit down with Mick and list every committed job with its client, value, stage, deadline and owner</li>
<li>Agree what "complete" means for each: handover, client sign-off, final invoice, retention release</li>
<li>Walk each live job with the person running it: what's going well, what's at risk, what's in their way</li>
<li>Note the blockers I can clear without changing how anyone works</li></ul></div>
<div class="card"><h3>{lv(1)} People</h3><ul class="tight">
<li><b>Mick:</b> the history of the business, what must not change, what he's concerned about and how he likes to be kept
informed</li>
<li><b>Dean:</b> what's been promised to clients, what's coming through the pipeline and what clients are saying</li>
<li>One-on-ones with managers, supervisors and the office team, fitted around their workload</li>
<li>Time on site with the crews, asking the same three questions: what works, what gets in your way, and what should I
leave alone</li></ul></div>
<div class="card"><h3>{lv(1)} The numbers that already exist</h3><ul class="tight">
<li>For each live job: quoted versus actual cost to date, variations, invoiced and still to invoice</li>
<li>Cash: debtors, and when the committed work converts to cash</li>
<li>Safety: tickets, inductions and incidents on current sites</li>
<li>I'd use whatever reporting is already in place. Where a number doesn't exist, I'd note it for later rather than build
something new mid-delivery</li></ul></div>
<div class="card"><h3>{lv(3)} Noted for later</h3><ul class="tight">
<li>Double handling, spreadsheets and manual approvals</li>
<li>Gaps in systems and reporting</li>
<li>Structure and capacity questions</li>
<li>These go on a list for the day-90 recommendations and aren't touched while the pipeline is being delivered</li>
</ul></div></div>
<h2>Output at day 30</h2>
<div class="say">A short note for Mick and Dean covering <b>where each committed job is at, the risks to completing it
well, what I'm doing to help, and what I've noted for later.</b> We'd agree it together, and nothing material changes
without that agreement.</div>"""


PRIORITIES = [
    (1, "Deliver the existing pipeline of mandates",
     "This is work Green Turf has already won, so the revenue, client relationships and reputation are already on the "
     "line. The business has been clear that this comes before any strategic change, and I agree with that. Completing it "
     "well funds the next stage and gives us the evidence for what should change.",
     "Every committed job complete, or on an agreed path to completion: on time, to standard, safely, and signed off by "
     "the client.", None, None),
    (1, "Keep every live site safe and compliant",
     "Non-negotiable, and part of delivering well. I'd confirm tickets, inductions, SWMS and plant servicing are current "
     "on each live job using the records that already exist. Closing a gap here is basic duty of care, and doesn't need to "
     "become a project.",
     "No one on a live site without the right tickets and inductions, and any gaps closed quickly.", None, None),
    (2, "Protect the margin and cash on the committed work",
     "A job that finishes late or over budget loses the margin it was won on. A weekly look at cost to date against the "
     "quote on the larger live jobs, variations captured as they happen, and each milestone invoiced promptly protects "
     "the value of the pipeline without changing how the team works.",
     "Weekly margin snapshot on the larger live jobs, variations captured, and each milestone invoiced as it's completed.",
     None, None),
    (2, "A light weekly rhythm to support delivery",
     "A short weekly check-in on live jobs, with one owner and one date per action, using the tools already in place. It "
     "helps get the pipeline over the line and takes some of the day-to-day chasing off Mick. Nothing more formal than "
     "that in the first 90 days.",
     "Weekly check-in held, actions followed up, and Mick spending less time firefighting.", None, None),
    (3, "Prepare the next stage, without starting it",
     "While the pipeline is being delivered, I'd keep a running list of what could be improved: systems, reporting, "
     "automation, capacity planning and structure. At day 90 I'd set these out with costs and benefits. Mick and Dean "
     "decide what happens, and when, once the committed work is complete.",
     "A short, costed list of options agreed with Mick and Dean. Nothing implemented in the first 90 days.",
     None, None),
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
<p class="lede">Five priorities, in order. The first two are about completing the work already won. The next two are
light controls that protect it. The fifth prepares the next stage without starting it.</p>
<div class="grid" style="gap:10px">{cards}</div>
<h2>What I wouldn't do in the first 90 days</h2>
<ul class="tight"><li>Restructure the team, or change roles or reporting lines</li>
<li>Introduce new systems, software or reporting the team has to learn while they're delivering</li>
<li>Change how crews work on live jobs, other than to fix a safety gap</li>
<li>Commit to new work that would stretch delivery of the existing pipeline without a capacity check with Mick and
Dean</li></ul>"""


def section3() -> str:
    return f"""
{brief("How You Would Partner With the Owner/MD and Marketing & Growth Director", [C_LEAD, C_FIT, C_COMM])}
<p class="lede">The business works because of Mick, and it grows because of the work Dean brings in. In the first 90 days
my role is to help both of them get the committed pipeline delivered, without adding a layer of process.</p>
<div class="grid k2">
<div class="card"><h3>With Mick (Owner/MD)</h3><ul class="tight">
<li>{lv(1)} In week one, agree the list of committed jobs and what "complete" looks like for each</li>
<li>{lv(1)} Understand what he wants to keep close and where he wants support, and respect what he's built</li>
<li>{lv(1)} Weekly one-on-one: no surprises, bad news early, options with a recommendation</li>
<li>{lv(2)} Take the day-to-day chasing on live jobs off his plate so he can focus on clients and the business</li>
<li>{lv(3)} At day 90, put the next-stage options in front of him so the timing is his decision</li></ul></div>
<div class="card"><h3>With Dean (Marketing &amp; Growth)</h3><ul class="tight">
<li>{lv(1)} Understand exactly what's been promised to each client in the pipeline, and keep him updated on delivery</li>
<li>{lv(1)} Protect the pipeline by checking capacity before new work is committed that could stretch current jobs</li>
<li>{lv(2)} Turn completed jobs into material he can use: photos, client feedback and case studies</li>
<li>{lv(3)} Once the pipeline is delivered, use actual job costs to sharpen quoting, and plan capacity ahead of growth
together</li></ul></div></div>
<h2>How the three of us would work together in the first 90 days</h2>
<table><tr><th>Meeting</th><th>Who</th><th>Purpose</th></tr>
<tr><td>Weekly one-on-one</td><td>Mick and me</td><td>Pipeline status, decisions needed, risks, people</td></tr>
<tr><td>Weekly live-jobs check-in</td><td>Job leads and me</td><td>This week and next on each committed job: blockers and
actions</td></tr>
<tr><td>Fortnightly pipeline catch-up</td><td>Dean and me</td><td>What clients expect, what's coming, and capacity before
new commitments</td></tr>
<tr><td>Day-30 and day-90 reviews</td><td>Mick, Dean and me</td><td>Confirm the plan, then agree what comes next and
when</td></tr></table>
<div class="say">If I disagree with a decision, I'll say so in the room with the evidence, and then back the decision
outside it.</div>"""


def section4() -> str:
    return f"""
{brief("Early Risks, Opportunities & Quick Wins", [C_JUDG, C_COMM, C_SEQ])}
<div class="grid k3">
<div class="card"><h3><span class="pill RED">Risks</span></h3><ul class="tight">
<li><b>Change that distracts from delivery.</b> This is the biggest risk I'd bring as a new starter. <i>Mitigation:</i> no
new systems or restructures in 90 days, and Level 2 only where it helps live jobs</li>
<li><b>A committed job slipping</b> on time, cost or quality. <i>Mitigation:</i> weekly live-jobs check-in and clearing
blockers quickly</li>
<li><b>Over-committing:</b> new work stretching current crews and plant. <i>Mitigation:</i> capacity check with Dean before
new commitments</li>
<li><b>Cash gaps</b> if milestones aren't invoiced promptly. <i>Mitigation:</i> invoice as each milestone is completed</li>
<li><b>Losing the team's trust</b> by coming across as corporate. <i>Mitigation:</i> listen first, be on site, and help
before suggesting anything</li></ul></div>
<div class="card"><h3><span class="pill GREEN">Quick wins</span></h3>
<p class="note" style="margin:0 0 4px">Only things that help the current pipeline, using existing tools:</p><ul class="tight">
<li>{lv(1)} Clear the blockers job leads raise in week one, and let them know it's done</li>
<li>{lv(1)} Confirm tickets and inductions for everyone on live sites</li>
<li>{lv(2)} Invoice each milestone as it's completed and follow up overdue debtors weekly</li>
<li>{lv(2)} Capture variations on live jobs as they happen</li>
<li>{lv(2)} One short weekly check-in on live jobs, with owners and dates</li></ul></div>
<div class="card"><h3><span class="pill AMBER">Opportunities, once the pipeline is delivered</span></h3><ul class="tight">
<li>{lv(3)} Use actual costs from completed jobs to price future quotes more accurately</li>
<li>{lv(3)} Plan crews and plant ahead of the next pipeline</li>
<li>{lv(3)} Reduce manual admin, such as supplier invoice processing</li>
<li>{lv(3)} A simple KPI pack built from existing systems</li>
<li>{lv(3)} Grow recurring maintenance work off the back of completed jobs</li></ul>
<p class="note" style="margin:6px 0 0">Put forward at day 90. Mick and Dean decide the timing.</p></div></div>
<h2>Examples of the later opportunities</h2>
<p style="max-width:840px">To show how I'd approach the Level 3 opportunities, I put together three small prototypes on
invented data. They aren't proposals for the first 90 days. They're examples of what could be considered once the
committed pipeline is delivered, if Mick and Dean want to go down that path.</p>
<div class="grid k3">
<a class="card" href="/project-control.html" style="text-decoration:none;color:inherit"><h3>{lv(3)} Margin early warning →</h3>
<p class="note" style="margin:0">Forecast margin at completion, with exceptions, owners and due dates.</p></a>
<a class="card" href="/reader.html" style="text-decoration:none;color:inherit"><h3>{lv(3)} Invoice reader →</h3>
<p class="note" style="margin:0">Reads a scanned invoice, checks ABN, GST, PO and duplicates, and suggests the GL account.</p></a>
<a class="card" href="/plant-allocation.html" style="text-decoration:none;color:inherit"><h3>{lv(3)} Plant allocation →</h3>
<p class="note" style="margin:0">Lowest-cost weekly plan across owned plant and hire, checked against tickets and inductions.</p></a>
</div>"""


def section5() -> str:
    return f"""
{brief("Your Leadership Approach", [C_LEAD, C_FIT, C_CALM])}
<p class="lede">Green Turf is a hands-on business with work to deliver and no appetite for dramatic change. What it needs
from this role is someone who supports the people doing that work, keeps things calm, and makes improvements in the right
order.</p>
<div class="grid k2">
<div class="card"><h3>How I lead</h3><ul class="tight">
<li><b>Support delivery first.</b> I'd build credibility by making the work easier before suggesting changes to it</li>
<li><b>Listen before acting.</b> The people doing the work usually know what's wrong, and what should be left alone</li>
<li><b>Be on site.</b> Regularly, as well as in the office</li>
<li><b>Be clear.</b> Every action has one owner and a date</li>
<li><b>Look at the process before the person.</b> When something goes wrong, the first question is why the process allowed
it</li></ul></div>
<div class="card"><h3>How I make decisions</h3><ul class="tight">
<li>First question: does this help us deliver what we've already committed to? If not, it waits</li>
<li>Small, reversible steps, and nothing that unsettles crews mid-job</li>
<li>Safety and integrity aren't traded off for speed or margin</li>
<li>Use data where it exists and judgement where it doesn't, and be upfront about which is which</li>
<li>If the evidence changes, I'll change my position and explain why</li></ul></div></div>
<h2>What I'd want the team to be able to say at day 90</h2>
<div class="say">That I helped them get their jobs completed, sorted out what was getting in their way, and didn't change
things for the sake of it.</div>"""


ASSUMPTIONS = [
    ("There's an existing pipeline of committed mandates to deliver.",
     "List every committed job with Mick in week one.",
     "If the pipeline is thinner than expected, Level 1 shifts to working with Dean on filling it, still without "
     "changing how the crews work."),
    ("The business wants stability, not dramatic change.",
     "Ask Mick and Dean directly at the start, and confirm it at the day-30 review.",
     "If they want to move faster, I'd bring Level 3 items forward, but still keep them out of peak."),
    ("Job cost, variation and cash information sits partly with individuals and in spreadsheets.",
     "Walk each live job with the person running it and see what they use.",
     "If good reporting already exists, I'd use it and not build anything new."),
    ("The season runs slow in January and February, heavy March to May, quiet in June and July, and peaks August to "
     "November.",
     "Check against the last two years of revenue and crew hours by month.",
     "Re-time when the Level 2 controls go in and when any Level 3 change is made."),
    ("Tickets, inductions and plant servicing are broadly current on live sites.",
     "Check on every live site in the first fortnight.",
     "Any gap goes straight to the top of the list, ahead of everything else."),
]


def assumptions() -> str:
    rows = "".join(f"<tr><td>{a}</td><td>{t}</td><td>{w}</td></tr>" for a, t, w in ASSUMPTIONS)
    return f"""
<p class="lede">I've put this plan together from outside the business, so it rests on a handful of assumptions. Here's what
they are, how I'd test each one in the first 30 days, and what I'd do if one turns out to be wrong.</p>
<h2>Why delivery comes first</h2>
<p style="max-width:860px">The existing mandates are work Green Turf has already won. The revenue, the client
relationships and the reputation are already on the line. Changing how people work while they're delivering puts that at
risk, so the order is deliver, then light controls, then strategic change. It's also how I've worked before: at SILK I
stabilised the Victorian operations first, and the acquisition and integration work came after that.</p>
<h2>My assumptions, and how I'd test them</h2>
<table><tr><th style="width:34%">Assumption</th><th style="width:28%">How I'd test it</th><th>If it's wrong</th></tr>{rows}
</table>
<h2>Where things aren't clear</h2>
<div class="grid k2">
<div class="card"><h3>How I'd approach it</h3><ul class="tight">
<li>Work out what I need to understand first, and who already knows it</li>
<li>Make the smallest decision that keeps live jobs moving</li>
<li>Agree how we'll know whether it worked, and check back</li>
<li>Test it against one question: does this help us deliver what we've already committed to?</li></ul></div>
<div class="card"><h3>An example</h3><p style="margin:0">Dean wins a large new job that would stretch the current crews.
I'd welcome it, then do a quick capacity check with Dean and Mick before we commit to dates: crews, plant,
subcontractors and the impact on jobs already promised. We'd agree a start date that protects existing clients, or what
we'd need to bring in to take it on. Everything can be delivered; it's a question of cost and timing.</p></div></div>
<h2>Disagreement</h2>
<p style="max-width:860px">If Mick or Dean sees it differently at the day-30 review, I'd want to understand what they're
seeing that I'm not, and test it against what I've found on the live jobs. It's Mick's business. My job is to give him the
clearest picture I can and a recommendation, then back the decision once it's made.</p>
<h2>What would change the plan</h2>
<ul class="tight"><li><b>A committed job in trouble.</b> It goes to the top of the list straight away</li>
<li><b>A safety gap on a live site.</b> Fixed before anything else</li>
<li><b>A cash issue.</b> Invoicing and collections take priority over everything except safety</li>
<li><b>Mick and Dean deciding a Level 3 change is more urgent.</b> We'd agree how to do it without disrupting delivery,
and time it outside peak</li></ul>"""


SECTIONS = [
    ("index.html", "Green Turf | My First 90 Days", "Business Operations Director | final-round presentation", review_page),
    ("approach.html", "My Approach to the First 90 Days", "How the plan is sequenced, and the 90 days at a glance", overview),
    ("plan-1.html", "1 | How I Would Get to Know the Business", "Learning the business through the committed pipeline",
     section1),
    ("plan-2.html", "2 | My Priorities for the First 90 Days",
     "Five priorities, starting with delivery of the existing mandates", section2),
    ("plan-3.html", "3 | Partnering with the Owner/MD and the Marketing & Growth Director",
     "How I would work with Mick and Dean", section3),
    ("plan-4.html", "4 | Early Risks, Opportunities and Quick Wins",
     "Protect delivery now, and hold the bigger opportunities until the pipeline is complete", section4),
    ("plan-5.html", "5 | My Leadership Approach", "Support the people delivering the work, then improve it", section5),
    ("season.html", "Timing Across the Season", "How the year shapes when each part of the plan happens",
     lambda: season_section(lv)),
    ("assumptions.html", "Assumptions and What Would Change the Plan",
     "What the plan rests on, how I'd test it, and how I'd adapt", assumptions),
    ("integrations.html", "Integrations", "Systems this can connect to, with their published APIs and GitHub SDKs",
     integrations_section),
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
        out[fname] = shell(title, sub, fn() + pager + KEYS, nav_for(fname))
    return out
