"""Consulting-engagement copy of the site, written to public/c/.

The Green Turf interview version stays at the site root. This copy reframes the same pages as an example LogisticsDx
90-day consulting engagement for an unnamed sports-turf construction client: no Green Turf logo, no client staff
names, no interview wording. Links inside the copy stay inside /c/. demo.logisticsdx.com opens this copy (middleware.js).
"""

from __future__ import annotations

import re
from pathlib import Path

PAGES = r"(?:index|approach|plan-\d|season|assumptions|prototypes|reader|project-control|plant-allocation|invoice-reader-batch|power-bi)"

BRANDBAR = """<div class="brandbar"><a href="/c/index.html" class="ldx" aria-label="Back to the engagement overview">Logistics<b>Dx</b></a>
<div class="by">Example 90-day consulting engagement<br><b>James Fischer-Myall</b>, LogisticsDx · <a href="/api/logout">Sign out</a></div></div>"""

# Exact phrases first, longest and most specific first. Whitespace in the source HTML may include line breaks, so each
# phrase is matched with flexible whitespace.
PHRASES = [
    ("James Fischer-Myall | Business Operations Director, final round | Green Turf",
     "James Fischer-Myall | LogisticsDx | Example 90-day consulting engagement"),
    ("Guiding principle: Green Turf doesn't want dramatic change.", "Guiding principle: the client didn't want dramatic change."),
    ("I've written this from outside the business, so I'd test it and adjust it in the first 30 days.",
     "It's tested with the client and adjusted in the first 30 days."),
    ("Green Turf | My First 90 Days", "LogisticsDx | 90-Day Consulting Engagement"),
    ("Business Operations Director | final-round presentation", "Example engagement | sports-turf construction client"),
    ("My Approach to the First 90 Days", "Engagement Approach"),
    ("1 | How I Would Get to Know the Business", "1 | Getting to Know the Client's Business"),
    ("1 | How I would get to know the business", "1 | Getting to know the client's business"),
    ("2 | My Priorities for the First 90 Days", "2 | Engagement Priorities"),
    ("2 | My priorities for the first 90 days", "2 | Engagement priorities"),
    ("3 | Partnering with the Owner/MD and the Marketing &amp; Growth Director", "3 | Working with the Owner and General Manager"),
    ("3 | Partnering with the Owner/MD and the Marketing & Growth Director", "3 | Working with the Owner and General Manager"),
    ("3 | Partnering with Mick and Dean", "3 | Working with the owner and general manager"),
    ("5 | My Leadership Approach", "5 | How I Work with the Team"),
    ("5 | My leadership approach", "5 | How I work with the team"),
    ("Green Turf | 90-Day Plan review", "90-Day Engagement review"),
    ("Back to the 90-day plan", "Back to the engagement overview"),
    ("How I'd measure myself at day 90", "How the engagement is measured at day 90"),
    ("My first job.", "The first job."),
    ("The role is about growth", "The engagement is about growth"),
    ("My first 90 days would be about", "The 90-day engagement is about"),
    ("from this role is someone", "from this engagement is someone"),
    ("What I wouldn't do in the first 90 days", "What the engagement doesn't do in 90 days"),
    ("my role is to help both of them", "my job is to help both of them"),
    ("How the three of us would work together in the first 90 days", "How we work together during the engagement"),
    ("If I started in late November or December, my first 90 days would run",
     "Starting in late November or December, a 90-day engagement runs"),
    ("With Mick (Owner/MD)", "With the owner"),
    ("With Dean (Marketing &amp; Growth)", "With the general manager"),
    ("With Dean (Marketing & Growth)", "With the general manager"),
    ("<b>Mick:</b>", "<b>Owner:</b>"),
    ("<b>Dean:</b>", "<b>General manager:</b>"),
    ("Nothing here describes Green Turf's actual performance.", "Nothing here describes any client's actual performance."),
    ("Green Turf prototypes", "LogisticsDx prototypes"),
    ("Working prototypes prepared for a Business Operations Director interview.", "Working prototypes from LogisticsDx."),
    ("Green Turf's own numbers", "the client's own numbers"),
    ("Green Turf has already won", "the client has already won"),
    ("Green Turf is a hands-on business", "The client is a hands-on business"),
    ("get to know Green Turf through", "get to know the client through"),
    ("This is the conversation with Dean about", "This is the conversation with the general manager about"),
    ("Mick, Dean and me", "The owner, general manager and me"),
    ("Mick and me", "The owner and me"),
    ("Dean and me", "The general manager and me"),
    ("Mick and Dean", "the owner and general manager"),
    ("Dean and Mick", "the general manager and owner"),
    ("Mick or Dean", "the owner or general manager"),
    ("Mick's", "the owner's"),
    ("Business Operations Director, final round", "LogisticsDx"),
    ("First 90 days", "90-day engagement"),
    ("greenturf-demo.example", "client-demo.example"),
    ("Business Operations Director", "Operations Director"),
]
WORDS = [(r"\bMick\b", "the owner"), (r"\bDean\b", "the general manager"), (r"\bGreen Turf\b", "the client")]


def _flex(phrase: str) -> re.Pattern:
    """Match the phrase across line breaks, and with apostrophes either literal or HTML-escaped."""
    words = [re.escape(w).replace("'", "(?:'|&\\#x27;|&\\#39;)") for w in phrase.split()]
    return re.compile(r"\s+".join(words))


COMPILED = [(_flex(a), b) for a, b in PHRASES]


def _capitalise(text: str) -> str:
    """Capitalise 'the owner' / 'the general manager' / 'the client' where they start a sentence or an element."""
    return re.sub(r"(^|[.!?]\s+|>\s*|\"\s*)the (owner|general manager|client)\b",
                  lambda m: m.group(1) + "The " + m.group(2), text)


def convert(html: str) -> str:
    html = re.sub(r'<div class="brandbar">.*?</div></div>', BRANDBAR, html, count=1, flags=re.S)
    for pat, rep in COMPILED:
        html = pat.sub(rep, html)
    # names in visible text only (leave file names, CSS and scripts alone)
    parts = re.split(r"(<script.*?</script>|<style.*?</style>|<[^>]+>)", html, flags=re.S)
    for i, part in enumerate(parts):
        if part and not part.startswith("<"):
            for pat, rep in WORDS:
                part = re.sub(pat, rep, part)
            parts[i] = part
    html = _capitalise("".join(parts))
    html = re.sub(r"(['\"])/(" + PAGES + r"\.html)", r"\1/c/\2", html)          # keep links inside the copy
    return html


def build(public: Path) -> int:
    out = public / "c"
    out.mkdir(exist_ok=True)
    n = 0
    for f in public.glob("*.html"):
        if f.name == "login.html":
            continue
        (out / f.name).write_text(convert(f.read_text(encoding="utf-8")), encoding="utf-8")
        n += 1
    return n
