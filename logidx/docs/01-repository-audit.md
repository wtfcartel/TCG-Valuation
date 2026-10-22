# 01 — Candidate repository audit

Audit date: 2026-10-21. Method: each repository was cloned from GitHub into an isolated scratch
directory and inspected directly (licence files, manifests, source tree, tests, CI, git history).
Nothing was copied from any of them into LogiDx; where LogiDx adopts an *idea* the source is
credited inline in the code and in [ARCHITECTURE.md](../ARCHITECTURE.md).

Commit counts for JobAggregator and JobSync come from a full (unshallowed) clone. freehire was
inspected from a 50-commit shallow clone, so its activity figures are a lower bound.

## Summary

| | A. JobAggregator | B. JobSync | C. freehire |
|---|---|---|---|
| Repo | SammyUrfen/JobAggregator | Gsync/jobsync | strelov1/freehire |
| Stack | Python 3.11, FastAPI, Jinja, raw `sqlite3`, APScheduler 3 | TypeScript, Next.js 15, Prisma 6, NextAuth 5 beta, Vercel AI SDK | Go, PostgreSQL 18 + pgvector, Meilisearch, Redis, S3, SvelteKit |
| Licence | **No LICENSE file.** README and `pyproject.toml` say "MIT"; author in pyproject differs from repo owner | MIT (LICENSE present) | MIT (LICENSE present) |
| Size | 113 `.py` files, 51 test files | ~1,040 TS/TSX files, 321 test files | ~9,570 tracked files (3,140 Go), 6,000+ test files |
| History | 51 commits, 1 author, first commit 2026-07-15, 4 commits in last 90 days | 972 commits since 2024-05-21, 390 in last 90 days, release automation | 50 commits in the 2 days to 2026-10-21 (very high velocity) |
| Auth | **None** on the dashboard | NextAuth sessions, encrypted stored API keys | Full identity service, billing |
| DB / migrations | SQLite, hand-rolled schema versions | SQLite via Prisma migrations | Postgres + sqlc + SQL migrations |
| Vacancy sources | python-jobspy (LinkedIn guest / Indeed scraping), Adzuna, Jooble, Himalayas, RemoteOK, Jobicy, Internshala, Unstop, Greenhouse, Lever, Ashby, SmartRecruiters | Greenhouse, Lever, Ashby only | ~298 adapters incl. Workday, PageUp, SuccessFactors, SmartRecruiters, Bullhorn, Adzuna, SEEK |
| SEEK / LinkedIn / Indeed / Google Jobs | LinkedIn + Indeed via **unauthorised scraping** (jobspy) | None | SEEK via its **undocumented internal frontend API**, explicitly to get past the Cloudflare check on SEEK's public pages (see `internal/ingest/sources/seek.go`) |
| Deduplication | Content hash (company+title+location) + RapidFuzz title fuzz | Per-board job id | Stable key across reposts |
| Lifecycle | Per-source *success guard* before expiry (good), but **hard-deletes** stale jobs | Manual statuses | Liveness probing, "ghost job" signal |
| AI | Résumé tailoring (LaTeX), browser apply agent | Multi-provider via Vercel AI SDK (OpenAI, Google, DeepSeek, Ollama…); in-app chat; MCP server | LLM fit analysis, CV tailoring |
| Application tracking | None | **Strong**: jobs, stages, interviews, contacts, tasks, activities, documents, backups | Board with stages, mail inbox linking, append-only event ledger |
| CV / cover letter | LaTeX résumé tailoring | PDF résumé export, AI cover letters | ATS-safe CV builder |
| Scheduling / notify | In-process daily APScheduler; Telegram, email, RSS | Automations scheduler; in-app notifications | Outbox runner; email/Telegram digests |
| Deployment | `start.sh` + systemd user unit; Docker "retired" | One Docker image, SQLite volume | 6-service compose stack |
| Geography assumptions | India/remote; **all salary normalised to INR/month** | North America-leaning (TZ example `America/Edmonton`) | Global IT; SEEK limited to ICT sub-classifications |

## Candidate A — JobAggregator

Strengths
- Same language and framework as the brief's preferred stack.
- The stale-expiry design is the best of the three: only sources that *succeeded* in a run may
  expire their jobs, and page-capped ("windowed") sources expire on posting age instead of absence.
  That is exactly the "a failed search is not zero jobs" rule in the brief.
- Disciplined tests (85 % coverage gate), injected clock, strict mypy.

Blocking issues
- **Licensing**: no LICENSE file in the repository. A "MIT" string in metadata is a declaration, not
  a grant with the required copyright notice. Copying code is not safe until the owner adds one.
- **Compliance**: its main board coverage is python-jobspy scraping LinkedIn's guest endpoints and
  Indeed. That is unauthorised scraping under both sites' terms; the brief forbids it.
- **Data loss**: stale postings are hard-deleted. The brief requires that history is never deleted.
- **Auto-apply browser agent** (`apply/`) with cookie/session persistence. Even with the
  human-submit default, it is outside what the brief allows and a large security surface.
- India-specific assumptions throughout (INR/month salary, Naukri/Internshala/Unstop sources,
  "India" location gate), no authentication, one maintainer, three months old.

## Candidate B — JobSync

Strengths
- Most mature application tracker of the three: stages, interviews, contacts linked to jobs,
  tasks, documents, AI cover letters, data backup/restore, encrypted API-key storage, MCP server.
- Actively maintained with release automation and a real test suite (Vitest + Playwright).
- MIT licensed.

Weaknesses for this brief
- Discovery covers only Greenhouse, Lever and Ashby. These are US tech-startup ATSs; Australian
  logistics/industrial employers mostly use Workday, SuccessFactors, PageUp and agency ATSs
  (Bullhorn, JobAdder). Discovery would be rebuilt almost entirely.
- No source audit model, no category coverage, no verification workflow, no recall testing —
  the core of this brief.
- TypeScript/Next.js server actions; adopting it means the discovery engine (the hard part) is
  written in the stack the brief did *not* prefer, against Prisma/SQLite.
- `next-auth` 5 is still a beta dependency.

## Candidate C — freehire

Strengths
- Broadest legitimate ATS coverage, including the Australian-relevant **Workday, PageUp,
  SuccessFactors, SmartRecruiters and Bullhorn** adapters, plus an Adzuna adapter.
- Thoughtful engineering: stable dedup keys, liveness probing, append-only ledgers, SECURITY.md.
- MIT licensed, very active.

Weaknesses for this brief
- **Operational weight**: Postgres+pgvector, Meilisearch, Redis, S3 mock, Go API and SvelteKit web
  for a single-user tool. Upgrades at ~25 commits/day would be a constant merge burden for a fork.
- Built to crawl *millions* of IT jobs; the domain dictionaries (seniority, specialisation, skills)
  are IT-specific. Executive logistics/strategy taxonomy, geography rules for Melbourne, and the
  audit/recall model would all be new.
- The SEEK adapter's approach (internal API used because the human pages sit behind an anti-bot
  interstitial) is not acceptable under this brief. Any fork would need that removed.

## Ability to integrate SEEK, LinkedIn, Indeed and Google Jobs through authorised methods

None of the three has an *authorised* integration for any of these four. The honest position,
which LogiDx implements and displays as source statuses, is:

| Source | Authorised automated route available to an individual job seeker? | LogiDx status |
|---|---|---|
| SEEK | No public candidate search API. SEEK's APIs are for hirers/ATS partners. | NOT SEARCHED; compliant routes: SEEK saved-search alert emails (Gmail, Phase 4), manual import |
| LinkedIn Jobs | No public job-search API. Partner programmes are for ATSs/employers. | NOT SEARCHED; alert emails (Phase 4), manual import, optional Google-indexed fallback labelled as such |
| Indeed | The Publisher job-search API is closed to new users. | NOT SEARCHED; alert emails, manual import |
| Google Jobs | No public API for the Google Jobs search experience. | NOT SEARCHED; Google Programmable Search (official API) may be configured as an *indexed fallback* |
| Adzuna | **Yes — official, keyed API (free tier).** Adzuna aggregates many AU boards. | API SEARCHED when keys present |

## Recommendation

**Build a modular application from scratch in Python/FastAPI, borrowing designs (not code)
from all three:**

- From JobAggregator: the per-source success guard and windowed-source expiry rule.
- From freehire: the public endpoint shapes for Workday CXS, PageUp, SmartRecruiters and Bullhorn
  (documented public APIs used by those vendors' own career portals), and stable source keys.
- From JobSync: the application-tracking data model (stages, contacts linked to jobs, documents).

Why not fork one:

1. The brief's critical success criterion is **auditable discovery coverage** (per-source and
   per-discipline audit, verification states, recall regression). None of the candidates models
   it, so it would be written fresh regardless of base.
2. A JobAggregator fork would start by deleting its main sources, its delete-on-stale behaviour,
   its apply agent and its India/INR assumptions — and it has no licence file.
3. A freehire fork carries five extra services and a fast-moving upstream for one user.
4. A JobSync fork gives a tracker but leaves discovery (the hard part) to be built in TypeScript
   on top of 3 US-centric ATSs.

The from-scratch build keeps to the brief's preferred stack (FastAPI, SQLAlchemy, Alembic,
Pydantic, APScheduler), runs as one process on SQLite or Postgres, and can be deployed with a
two-service Docker Compose file.

See [ADR-0001](adr/0001-foundation.md) for the decision record.

## Risks recorded

| Risk | Mitigation |
|---|---|
| Employer ATS identifiers (Workday tenant/site, PageUp institution id, Bullhorn corp token) must be discovered per employer | Watchlist ships with names only; identifiers are added when confirmed; unconfigured entries are shown as NOT CONFIGURED, never as "searched" |
| SEEK/LinkedIn/Indeed coverage gap is structural | Shown on every coverage matrix and daily report; alert-email ingestion is the Phase 4 compliant route |
| Adzuna descriptions are truncated snippets and some salaries are *predicted* | Snippet flag stored; predicted salaries are discarded, never shown as advertised |
| Vendor public endpoints can change without notice | Each adapter is isolated; failures are logged as FAILED for that source only |
