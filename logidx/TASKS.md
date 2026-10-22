# LogiDx task checklist

Legend: [x] done and tested offline · [~] partly done · [ ] not started · **BLOCKED** needs something outside the code

## Phase 0 — audit and decision
- [x] Clone and inspect JobAggregator, JobSync and freehire (licence, maintenance, sources, security, architecture)
- [x] Comparison and recommendation (`docs/01-repository-audit.md`), ADR-0001

## Phase 1 — executable core
- [x] Project structure, settings, SQLAlchemy models, Alembic migration (test asserts the models match the migration)
- [x] Editable candidate profile (seeded from the brief only; evidence carries its source)
- [x] Configurable taxonomy: families A–K, nine disciplines, seniority/scope/negative/knockout signals, AU/US spelling, `&`/and
- [x] Source-adapter interface; restricted sources recorded as NOT SEARCHED
- [x] Adapters: Adzuna (API), Workday, SmartRecruiters, Greenhouse, Lever, PageUp, Bullhorn, RSS, Google-indexed fallback
- [ ] **BLOCKED** Live verification of every adapter: the build environment denied network access to all job hosts; no Adzuna key. Run `logidx probe`
- [ ] **BLOCKED** End-to-end search with real, attributable vacancies (same cause). The full pipeline has run end to end on synthetic vendor-shaped payloads only
- [x] Normalisation, salary parsing (super/TRP/day and hourly rates), geography relative to Melbourne, deduplication
- [x] Persistence, lifecycle with success guard (no deletion), run history, source and discipline audits
- [x] Scheduler (06:00/14:00/20:00 Melbourne, DST-safe, idempotent slots, DB lock), Run now button, CLI
- [x] Responsive dashboard: Overview, Job discovery, Priority, Disciplines, Applications, Recruiters, Coverage, Recall & QA, Daily report, Documents, Import, Runs, Settings

## Phase 2 — AI evaluation
- [x] Provider interface; xAI Grok provider (structured JSON-schema output, retries, cost tracking, daily budget)
- [x] Pydantic schema, evidence-ID and knockout-quote validation, deterministic scoring, fit classes and overrides
- [x] Mocked tests (request shape, auth failure, 429 retry, invalid output, overrides)
- [ ] **BLOCKED** Live Grok test: no `XAI_API_KEY`; `api.x.ai` blocked by the network policy. Confirm the model name (`XAI_MODEL`) and pricing

## Phase 3 — full discovery coverage
- [x] Daily discipline audit with rotating queries; INCOMPLETE / NOT SEARCHED flags
- [x] Verification workflow (5 statuses, evidence, URL checker, robots.txt, re-check guard before documents)
- [x] Recall framework: live cases A and B, miss-cause diagnosis, 13 taxonomy fixtures, metrics
- [~] Watchlist: 21 employers and 9 agencies listed — **identifiers to be confirmed** (deliberately not guessed)
- [ ] Confirm feeds for EthicalJobs and Pro Bono Australia
- [ ] Investigate Workforce Australia and JobAdder agency feeds
- [ ] Add more ATS adapters common in AU (SuccessFactors, JobAdder, LiveHire, ELMO, Workable) once employers are mapped
- [ ] PostgreSQL full-text search (currently LIKE filtering; fine for single-user volume)
- [ ] Live recall tests: record `first_published` for each case to measure discovery latency

## Phase 4 — applications and documents
- [x] Application statuses DISCOVERED … CLOSED, with audited status changes, notes and a Kanban view
- [x] Master CV import (DOCX/PDF → text, versioned), used as AI evidence
- [x] Manual / browser-assisted vacancy import for restricted sources
- [x] Recruiter directory (public contact information only, with source recorded)
- [ ] Gmail read-only OAuth (`gmail.readonly`): application confirmations, rejections, interviews, recruiter mail; reconcile with vacancies; ingest SEEK/LinkedIn/Indeed alert emails (the compliant route for those sources)
- [ ] Tailored CV (DOCX + PDF), cover letter, KSC response and alignment report for verified-open Priority roles, gated by `require_fresh_verification`
- [ ] Approval-gated outbound communication (never automatic)

## Phase 5 — production hardening
- [x] Vercel deployment (second project, Root Directory `logidx`): ASGI entry point, Neon URL support, advisory-locked migrate and seed on cold start, env-based first-user bootstrap, cron endpoint with `CRON_SECRET`, per-run time budget, synchronous Run now. `vercel build` and the built function on PostgreSQL verified locally
- [ ] Create the Vercel project and Neon database, then deploy (needs the owner's Vercel account — steps in `docs/03-deploy-vercel.md`)
- [x] Docker Compose (PostgreSQL, app, nightly backups), health endpoint, JSON logs with secret redaction
- [ ] **BLOCKED** `docker compose up` not exercised: no Docker daemon in the build environment
- [ ] CI run on GitHub (workflow added: `.github/workflows/logidx.yml`)
- [ ] Failure alerting (an email when a run fails or a source fails three runs in a row)
- [ ] Data-retention settings (expired-vacancy descriptions, assessment payloads)
- [ ] Multi-user: scope rows by user_id and add roles
- [ ] External security review; performance test with a large watchlist

## Known limitations
- Adzuna descriptions are snippets. Fuller text depends on the original advertiser's page.
- A Workday tenant that is too large to list in full is searched with executive keywords (it is marked truncated,
  so absence never expires its jobs).
- Bullhorn job pages use the REST entity URL unless `job_url_template` is set.
