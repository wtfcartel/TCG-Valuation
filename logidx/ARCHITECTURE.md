# LogiDx architecture

## Overview

```
                ┌──────────────────────── logidx serve (one process) ────────────────────────┐
                │                                                                            │
 APScheduler ──►│ service.execute ──► runner.run_discovery ──► post_run                      │
 (06/14/20 Mel) │        ▲                │                      ├─ ai.evaluate (Grok)        │
 Run now / CLI ─┘        │                │                      ├─ recall.evaluate_all       │
                         │                ▼                      └─ report.build → notify     │
                 idempotency key   ┌──────────────┐                                           │
                 + DB run lock     │ per source / │  RestrictedSource ─► NOT SEARCHED row      │
                                   │ per query    │  QuerySource  ─► Adzuna / Google-indexed   │
                                   │ try/except   │  BoardSource  ─► Workday, SmartRecruiters, │
                                   └──────┬───────┘                 Greenhouse, Lever, PageUp, │
                                          │ RawVacancy             Bullhorn, RSS               │
                                          ▼                                                    │
     pipeline.ingest: normalise → dedup (source id, reference, employer+title+location+text)   │
                      → salary → geography → taxonomy classification → Vacancy + VacancySource │
                                          ▼                                                    │
     lifecycle (_expire): success-guarded absence → NOT SEEN → EXPIRED (never deleted)        │
     verification: VERIFIED OPEN / LIKELY OPEN / RECRUITER CONFIRMATION / STALE / CLOSED      │
     audit: SourceSearch row per search · CategoryAudit row per discipline per run            │
                │                                                                            │
                │ FastAPI dashboard (Jinja) + /api JSON ── SQLAlchemy ── SQLite | PostgreSQL │
                └────────────────────────────────────────────────────────────────────────────┘
```

## Modules (`src/logidx/`)

| Module | Responsibility |
|---|---|
| `settings.py` | Environment-only configuration and secrets (pydantic-settings) |
| `models.py`, `migrations/` | SQLAlchemy 2 models; Alembic migrations (batch mode for SQLite) |
| `taxonomy.py` + `config/taxonomy.yaml` | Title families A–K, the nine audited disciplines, seniority, scope and knockout patterns, spelling variants, query rotation |
| `profile.py` + `config/profile.yaml` | Candidate profile; every evidence item records its source |
| `sources/` | `http.py` (timeouts, backoff, rate limit, robots.txt), `base.py` (interfaces), adapters, `registry.py` (restricted sources, coverage targets, watchlist) |
| `pipeline/` | `normalize`, `salary`, `location`, `dedup`, `ingest`, `runner` |
| `verification.py` | Status rules, URL checker, document-generation guard |
| `ai/` | `provider.py` (interface, Grok, static test provider), `schemas.py` (Pydantic output schema), `evaluate.py` (prompting, validation, deterministic scoring and overrides, budget) |
| `recall.py` + `config/recall_cases.yaml` | Known-vacancy cases, miss-cause diagnosis, taxonomy fixtures, metrics |
| `coverage.py` | Daily source and discipline matrices |
| `report.py`, `notify.py` | Daily report (HTML and text); SMTP delivery with retry and idempotency |
| `scheduler.py`, `schedule_config.py`, `locks.py`, `service.py` | Timezone-aware schedule, editable slots, cross-process lock, orchestration |
| `security.py` | scrypt password hashing, CSRF, login rate limiting, secret redaction, JSON logging |
| `web/` | Dashboard routes, templates and static files |

## Key design rules

1. **A failed search is not zero jobs.** Every search writes a `SourceSearch` row with one of: NATIVE SEARCHED,
   API SEARCHED, INDEXED FALLBACK ONLY, ACCESS BLOCKED, NOT SEARCHED or FAILED. Restricted sources and boards
   without identifiers write a NOT SEARCHED row on every run, with the reason.
2. **Failure isolation.** Each query, each board and each record is isolated (try/except, plus a savepoint per
   record). After three consecutive access refusals, a source stops for that run.
3. **Discipline audit.** Each run writes a `CategoryAudit` row for each of the nine disciplines. The daily matrix
   marks a discipline COMPLETE only when every planned query (core and rotating) succeeded on every keyword-search
   source that ran that day, and at least one source succeeded.
4. **Lifecycle without deletion.** A sighting goes absent only when its source *succeeded* with a *complete*
   listing (this success-guard idea comes from JobAggregator). Keyword-limited or page-capped sources retire
   sightings by age instead. A vacancy with no present sightings becomes NOT SEEN, then EXPIRED after 3 days. Rows,
   events, assessments and application history are never deleted.
5. **Deduplication** checks, in order: (source, source id); then the same advertiser reference; then same
   employer or agency plus a near-identical title, a compatible location and similar text. Identical boilerplate
   descriptions alone never merge two roles.
6. **Deterministic facts.** Salary, geography, dates and verification are computed by code. The AI receives them
   as read-only facts.
7. **AI output is validated.** Output must match `AssessmentOutput`. Evidence IDs must exist in the profile, and
   knockout quotes must appear in the advertisement. The overall score is a fixed weighting (capability 0.30,
   evidence 0.25, archetype 0.15, ATS 0.10, recruiter-read 0.20). Thresholds: Priority ≥ 8.5, Adjacent ≥ 7.0,
   Exploratory ≥ 6.0. Overrides: an unmet essential knockout caps the class at Low; specialist-dominated roles and
   roles without evidenced executive scope cap at Exploratory; a STRETCH conversion moves Priority down to
   Adjacent, and LONG_SHOT caps at Exploratory. Invalid outputs are stored for audit but never change scores.
8. **Verification.** Only an employer's live ATS listing, or a job-specific page explicitly stating that
   applications are open (or close on a future date), counts as VERIFIED OPEN. A generic careers page or an Apply
   button alone never does. The checker never logs in or submits anything, and it honours robots.txt.
9. **Scheduling.** Cron triggers use Melbourne wall-clock time (DST-safe). Each scheduled slot has an idempotency
   key `scheduled:<date>:<HH:MM>`, and a database lock prevents overlapping runs. The daily report is sent once per
   day, deduplicated in the `notifications` table.

## Data model (main tables)

`vacancies` (one row per real-world vacancy: all fields from §9 of the brief) · `vacancy_sources` (each sighting:
source, board, source id, access method, employer-requisition or agency flags, present, last seen) ·
`vacancy_events` (append-only audit trail) · `assessments` (every AI call, valid or not, with tokens and cost) ·
`runs` · `source_searches` · `category_audits` · `run_locks` · `recall_cases` / `recall_results` · `notifications` ·
`documents` · `agencies` / `recruiters` · `users` · `audit_log` · `settings_kv` (non-secret editable settings).

## Security

- A session cookie (signed, HttpOnly, SameSite=Strict, Secure in production) with a 12-hour lifetime. Passwords are
  hashed with scrypt.
- A CSRF token is required on every POST. Login failures are rate-limited to 5 per 15 minutes per IP and email.
- Security headers: CSP (`'self'` only, no inline script), frame-ancestors none, nosniff, no-referrer.
- Secrets come only from environment variables and are never shown in the UI or stored in the database. Logs pass
  through a redaction filter, and httpx request logging is silenced (its URLs carry API keys).
- Outbound requests have timeouts, per-host pacing and bounded retries. 401/403 responses are reported, never retried
  around. XML feeds are parsed with defusedxml.
- Interactive API documentation is disabled. All `/api` endpoints require a session.
