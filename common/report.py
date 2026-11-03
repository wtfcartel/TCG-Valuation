"""Shared helpers: CSV loading, money formatting, HTML page shell, hash-chained action log.

Standard library only, so every demo runs on a plain Python 3.10+ install.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
REPORT_DATE = date(2026, 10, 31)  # synthetic "as at" date for every demo

SYNTHETIC_BANNER = (
    "SYNTHETIC DEMONSTRATION DATA. Every project, person, client and figure is invented to test the calculations. "
    "Nothing here describes Green Turf's actual performance."
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def d(s: str) -> date:
    return date.fromisoformat(s)


def money(v: float, signed: bool = False) -> str:
    sign = "−" if v < 0 else ("+" if signed and v > 0 else "")
    return f"{sign}${abs(v):,.0f}"


def pct(v: float | None, dp: int = 1) -> str:
    return "—" if v is None else f"{v * 100:.{dp}f}%"


def esc(s: object) -> str:
    return html.escape(str(s))


CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1d2a22;--muted:#5d6b62;--line:#dfe3dc;--green:#2f6b3f;--green-l:#e3efe5;
--amber:#a5640c;--amber-l:#fbefd9;--red:#a8322d;--red-l:#f8e1df;--grey-l:#eceeea}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:24px 20px 48px}
header h1{font-size:22px;margin:0 0 2px}header p{margin:0;color:var(--muted)}
.banner{background:#fff4c7;border:1px solid #e6cf70;border-radius:6px;padding:8px 12px;margin:14px 0 18px;font-size:12.5px}
.grid{display:grid;gap:12px}.k4{grid-template-columns:repeat(4,1fr)}.k3{grid-template-columns:repeat(3,1fr)}.k2{grid-template-columns:1fr 1fr}
@media(max-width:800px){.k4,.k3,.k2{grid-template-columns:1fr 1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px}
.kpi .l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}.kpi .v{font-size:24px;font-weight:650;margin-top:2px}
.kpi .s{font-size:12px;color:var(--muted)}
h2{font-size:16px;margin:26px 0 8px}h3{font-size:14px;margin:0 0 8px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden;font-size:13px}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:#eef1ec;font-weight:600;font-size:12px;color:#33433a}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:none}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11.5px;font-weight:600;white-space:nowrap}
.RED{background:var(--red-l);color:var(--red)}.AMBER{background:var(--amber-l);color:var(--amber)}.GREEN{background:var(--green-l);color:var(--green)}
.GREY{background:var(--grey-l);color:#555}
.note{color:var(--muted);font-size:12.5px}.mono{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px}
footer{margin-top:28px;color:var(--muted);font-size:12px}
"""


def page(title: str, subtitle: str, body: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{CSS}</style></head>
<body><div class="wrap"><header><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></header>
<div class="banner"><b>Prototype.</b> {esc(SYNTHETIC_BANNER)}</div>{body}
<footer>Green Turf prototypes · reporting date {REPORT_DATE:%d %b %Y} · recalculates from the CSV files in /data on every run.</footer>
</div></body></html>"""


# ---------------------------------------------------------------- hash-chained action log
# Pattern adapted from Cardcore's insurance ledger (TCG-Valuation/apps/api/src/services/insurance.ts):
# every event stores the previous event's hash, so editing or deleting any past entry breaks the chain.


def _event_hash(prev_hash: str | None, payload: dict) -> str:
    body = json.dumps({"prev": prev_hash, **payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def chain_events(events: list[dict]) -> list[dict]:
    out, prev = [], None
    for e in events:
        h = _event_hash(prev, e)
        out.append({**e, "prev_hash": prev, "hash": h})
        prev = h
    return out


def verify_chain(events: list[dict]) -> tuple[bool, int | None]:
    """Return (ok, index_of_first_bad_event)."""
    prev = None
    for i, e in enumerate(events):
        payload = {k: v for k, v in e.items() if k not in ("prev_hash", "hash")}
        if e.get("prev_hash") != prev or e.get("hash") != _event_hash(prev, payload):
            return False, i
        prev = e["hash"]
    return True, None
