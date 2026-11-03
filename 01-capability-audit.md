# Deliverable 1 — Existing Capability Audit

Audit date: 3 November 2026. Scope: everything reachable from this session.

## What was audited, and what was not

| Source | Status |
|---|---|
| GitHub `wtfcartel/Trial-1-Cartel-v1` (branches `claude/transport-nursing-services-app-28kxim`, `claude/logisticsdx-listening-reader-h1mdk7`) | Cloned and inspected |
| GitHub `wtfcartel/TCG-Valuation` (branches `main`, `claude/cardcore-tcg-valuation-2t2kzz`, `claude/logidx-executive-search-qes5yy` — the last is already merged into `main`) | Cloned and inspected |
| Local Claude Code projects on James's computer | **Not audited** — the computer was not connected to this session |
| Any other LogisticsDx repositories | None exist in the GitHub account (`list_repos` returned only the two above) |

**Testing limitation.** This environment cannot reach npm or PyPI, so applications whose dependencies are not
preinstalled (Next.js, Prisma, SQLAlchemy, rapidfuzz) could not be installed, built or run. Only the Cardcore
valuation engine could be executed. Everything else below is from code inspection, and is marked as such.

## Capabilities not found

The brief lists capabilities that are **not present in any accessible code**. They may exist on James's computer or
elsewhere, but cannot be claimed from this audit:

- Management/BI reporting over operational or financial data (revenue, margin, WIP, debtors).
- Executive KPI dashboards over business data.
- Business valuation or commercial modelling (Cardcore values *collectible cards*, not businesses).
- Transport/logistics workflow automation (dispatch, fleet, freight).
- Project costing, budget-vs-actual or forecast-at-completion logic.

## Application inventory

### 1. ShiftReady — credential-gated shift marketplace
`Trial-1-Cartel-v1`, branch `claude/transport-nursing-services-app-28kxim`, one commit (`1cac697`).

| | |
|---|---|
| Built | Next.js 16 + Prisma/SQLite app: facilities post shifts; workers claim; facility confirms one claim. Admin verifies uploaded credentials; workers complete induction modules; availability blocks; `.ics` calendar invites. |
| Works / demonstrable | **Not run** (dependencies unavailable here). README documents `npm install → db:push → db:seed → dev` with seeded demo accounts. |
| Verified in code | Eligibility rule in `lib/nurse-status.ts` (verified credentials AND all induction modules complete). Enforced server-side in `lib/actions/shifts.ts:72`, not just hidden in the UI. Calendar export in `lib/ics.ts`. |
| Reusable | The competency-gated allocation pattern; data model for credentials, inductions, availability and assignments. |
| Green Turf modification | Workers → plant operators; credentials → tickets/licences (e.g. HR licence, high-risk work, site inductions) with expiry dates; shifts → machine-day allocations on projects. |
| Gaps | No expiry dates on credentials, no plant/asset model, no cost data. Healthcare-specific wording throughout. |
| Maturity | MVP prototype, single commit, untested in this audit. |

### 2. LogisticsDx Market Intelligence publisher
`Trial-1-Cartel-v1`, branch `claude/logisticsdx-listening-reader-h1mdk7` (`3171fb6`), ~3,000 lines added.

| | |
|---|---|
| Built | One JSON report per day (`data/intelligence/<date>.json`) rendered as web reader, PDF (`pdfkit`), HTML/text email (Resend or SMTP) and narrated audio (OpenAI TTS). Evidence labels on every item (`SUPPORTED CONCLUSION` … `INSUFFICIENT EVIDENCE`). Cron-secured publish endpoint. |
| Works / demonstrable | **Not run.** Only sample data exists (`2026-09-20.json`, flagged `isSampleData: true`, all entities fictional). |
| Important limit | The research step is **not built**. `app/api/logistics/generate/route.ts` states it only publishes a JSON file that an upstream research step must already have written. |
| Reusable | "One source of truth → many derived views" reporting pattern; evidence-confidence labelling; scheduled email distribution. |
| Green Turf modification | Weekly management report generated from project/plant/action data instead of market news. |
| Maturity | Working-pattern prototype on sample data. |

### 3. LogiDx Executive Search
`TCG-Valuation/logidx` (Python/FastAPI, ~6,900 lines, 10 test modules).

| | |
|---|---|
| Built | Scheduled vacancy discovery (06:00/14:00/20:00 Melbourne), source adapters, normalisation, salary/location parsing, de-duplication, AI fit assessment with evidence validation and daily cost budget, application tracking, daily email report, dashboard. |
| Works / demonstrable | **Not run here** (SQLAlchemy, rapidfuzz unavailable). Its own `TASKS.md` records live source verification and live AI tests as **BLOCKED**; the pipeline has only run on synthetic payloads. |
| Verified in code | Coverage matrix (`coverage.py`) reports each source and category as COMPLETE / INCOMPLETE / NOT SEARCHED — a failed search is never reported as "no results". |
| Reusable | The exception-reporting discipline (missing data shown as missing, not as zero); scheduler; daily report builder; AI-with-evidence guardrails. |
| Green Turf relevance | Pattern only. The domain (job search) is not relevant. |
| Maturity | Substantial, well-documented prototype; not live-verified. |

### 4. Cardcore — collection valuation and insurance ledger
`TCG-Valuation` (`packages/engine`, `apps/api`, `apps/web`).

| | |
|---|---|
| Built | Rules-based valuation engine (documented methodology CSM-1.0.0/1.1.0), Fastify API with Postgres, React PWA, PDF reports, append-only insurance ledger. |
| Works / demonstrable | **Engine executed: 13 of 13 unit tests pass** (run with a minimal test-runner shim because vitest could not be installed). API and web app not run (needs Postgres + npm install). |
| Verified in code | Append-only enforcement by database trigger (`migrations/001_init.sql:26`); hash-chained events, each storing the previous event's hash (`services/insurance.ts:104–122`); confidence rated High/Moderate/Limited by published rules (`engine/src/confidence.ts`). |
| Reusable | Tamper-evident audit trail for approvals, variations and corrective-action close-outs; rules-based confidence rating. |
| Green Turf relevance | Audit-trail pattern only. The valuation domain is not relevant. |
| Maturity | Most mature code in the account (tests, CI workflow, migrations, docs). |

## Capability-to-requirement map

| Green Turf area | Best reusable asset | Reuse type | Reuse strength |
|---|---|---|---|
| A. Executive visibility & exceptions | LogiDx coverage/exception discipline; Market Intelligence report pipeline | Pattern | Medium |
| B. Project profitability & early warning | None directly | New, small | Low reuse — needs new logic |
| C. Fleet, equipment & operators | ShiftReady eligibility gating | Logic adaptation | Medium–High |
| D. Governance, approvals, actions | Cardcore append-only, hash-chained ledger | Pattern | Medium |

## Conclusion

None of the existing applications can be pointed at Green Turf as-is. What is genuinely reusable is a set of proven
*patterns* — competency-gated allocation, exception reporting that never hides missing data, single-source report
generation, and a tamper-evident approval trail. The honest positioning is: "I have built these mechanisms before;
here they are adapted to a turf-construction business," not "I have a system ready to install."

## Addendum — what was built from this audit

Three demonstrations were selected and built in `greenturf-modernisation-showcase` (see README for setup and
execution evidence). At James's direction, the OCR invoice and remittance reader is the flagship. Reuse was at the
pattern level: ShiftReady's eligibility gate (Demo 2), LogiDx's "never report missing data as nothing found" (Demo 1),
Cardcore's hash-chained ledger (Demo 1 action trail), and the Market Intelligence confidence labelling (Demo 3).
No existing repository was modified.
