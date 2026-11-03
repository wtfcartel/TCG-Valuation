# Green Turf modernisation showcase

Interview demonstration material for the Business Operations Director role. It is kept separate from the
production applications in `wtfcartel/Trial-1-Cartel-v1` and `wtfcartel/TCG-Valuation`, and none of them was modified.

> **All data is synthetic.** Every supplier, ABN, project, person, rate and figure is invented to exercise the
> calculations. Nothing here connects to, or describes, Green Turf's systems or performance. Nothing is posted to
> Xero and no email is sent.

## Contents

| Path | What it is |
|---|---|
| `01-capability-audit.md` | Deliverable 1: what exists in the GitHub repositories, what was tested, and what is reusable |
| `demo3_invoice_reader/` | **Flagship.** OCR invoice and remittance reader: validation, GL suggestion, approval-email drafts, Xero-format export |
| `demo1_project_control/` | Project margin early-warning: forecast margin at completion, exceptions with owners, hash-chained action trail |
| `demo2_plant_allocation/` | Plant and operator allocation: lowest-cost weekly plan gated by tickets, inductions and service windows |
| `data/` | Synthetic inputs (CSV) and the generated inbox of scanned and emailed documents |
| `output/` | Generated pages, workbook, Xero CSV, draft emails, JSON, test results and run log |
| `screenshots/` | Captured pages, plus cropped versions used in the executive pack |
| `tests/test_demos.py` | 17 tests covering the calculations and controls |
| `demo4_seasonality/`, `data/seasonality/` | Season model: ROIC per unit and service efficiency by month (also feeds `season_*` Power BI tables) |
| `webbuild/brand.css`, `webbuild/vendor/` | Look and feel: Pico CSS v2.0.6 (MIT, github.com/picocss/pico) with a Green Turf brand layer |
| `webbuild/plan.py` | The 90-day plan pages (content lives here; edit and rebuild) |
| `api/`, `public/`, `webbuild/`, `vercel.json` | The Vercel deployment: Python functions, static site, and its build script |

The executive pack (Deliverable 3) and the presentation notes and implementation assessment (Deliverables 4 and 5,
plus the wider streamlining options) are Claude Docs, linked from the conversation.

## Live deployment (Vercel)

`public/` is the static site and `api/*.py` are standard-library Python functions, so Vercel needs no build or install
step (`vercel.json`). Every page carries the plan navigation and the Green Turf logo bar. The working examples are linked from section 4.

| Path | What it does |
|---|---|
| `/` (`index.html`) | **"My First 90 Days" presentation**: overview, timeline, agenda and day-90 scorecard |
| `/plan-1.html` … `/plan-5.html` | One page per area of the final-round brief; ← → keys move between them, so the site can be presented directly |
| `/season.html` | Season, ROIC per unit and service efficiency by month (demonstrative season: slow Jan–Feb, heavy growth Mar–May, dead Jun–Jul, peak Aug–Nov) |
| `/assumptions.html` | Assumptions, how each would be tested, and what would change the plan |
| `/prototypes.html` | Index of the working prototypes |
| `/reader.html` | Live reader: pick a sample scan or upload an image; OCR runs in the browser (tesseract.js, 3 layout passes), then `/api/read` validates, suggests the GL and drafts the approval email |
| `/api/read` | `POST {text, filename?, ocrConfidence?}` → extracted fields, checks, GL candidates, routing, draft email |
| `/api/powerbi?table=…&format=csv\|json` | Live tables for Power BI Desktop / Excel (Get Data → Web): projects, exceptions, margin_history, debtor_ageing, ap_queue, plant_plan, plant_fleet, plant_actions |
| `/power-bi.html` | How to connect Power BI, and the embedding options |

Rebuild the site after changing data: `./run_all.sh && python3 -m webbuild.build_site`, then commit and push.

## Setup

Requires Python 3.10+ and the Tesseract OCR engine.

```bash
# macOS:        brew install tesseract poppler
# Ubuntu:       sudo apt install tesseract-ocr poppler-utils
pip install pdfplumber pytesseract pillow reportlab openpyxl pytest
pip install playwright && playwright install chromium     # optional, for screenshots only

./run_all.sh
```

Or run each part on its own from this folder:

```bash
python3 -m demo3_invoice_reader.make_samples   # regenerate the synthetic inbox
python3 -m demo3_invoice_reader.run            # → output/invoice_reader/
python3 -m demo1_project_control.run           # → output/project_control.html
python3 -m demo2_plant_allocation.run          # → output/plant_allocation.html
python3 -m pytest -q tests
```

Open the `.html` files in `output/` in any browser. Change any CSV in `data/` and rerun: every figure recalculates.

## Evidence of execution (3 Nov 2026)

```
Demo 3: 10 documents → READY 5, NEEDS APPROVAL 3, EXCEPTION 2; 9 Xero lines; 5 email drafts; 18.6s
Demo 1: 6 projects, 9 exceptions (RED 3, AMBER 5, NOT REPORTED 1); forecast GM 18.4% vs quoted 20.3%; action log chain ok
Demo 2: plan $29,480 vs all-hire $41,900; 5/7 owned; 6 actions
17 passed
```

Full log: `output/run_evidence.txt`.

## What was reused from existing code

| Pattern | Source | Used in |
|---|---|---|
| Credential-and-induction gate, enforced server-side | `Trial-1-Cartel-v1` · `lib/nurse-status.ts`, `lib/actions/shifts.ts` | Demo 2 operator eligibility |
| Missing data reported as NOT SEARCHED, never as "nothing found" | `TCG-Valuation/logidx` · `coverage.py` | Demo 1 "not reported" projects |
| Hash-chained, append-only event ledger | `TCG-Valuation` · `apps/api/src/services/insurance.ts` | Demo 1 action trail |
| One data file feeding every report view; evidence-confidence labels | `Trial-1-Cartel-v1` · `lib/logistics/types.ts` | Demo 3 GL confidence and reasons |

These are reused as design patterns re-implemented in Python, not as imported code: the originals are TypeScript
and Python applications with different stacks and domains.

## Known limits

- OCR was tested on deliberately degraded synthetic scans. Accuracy on real supplier layouts must be measured.
- Xero output follows the bill-import column layout. It has not been imported into a live Xero organisation.
- The plant optimiser is an exhaustive search: suitable for tens of weekly requests, not hundreds.
- Thresholds, the chart of accounts and cost rates are placeholders to be agreed with management.
