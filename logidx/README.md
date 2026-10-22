# LogiDx Executive Search

A self-hosted system that searches for senior executive vacancies on a schedule, records exactly which sources and
disciplines were searched, checks whether each vacancy is still open, rates fit with an AI model, and tracks
applications. It is built for one Melbourne-based logistics, commercial, operations and transformation executive,
and structured to support more users later.

> **Coverage is never assumed.** SEEK, LinkedIn, Indeed, Google Jobs, Jora, CareerOne and Workforce Australia offer no
> authorised automated search for individuals. LogiDx does not scrape them. They appear on every coverage matrix as
> **NOT SEARCHED**, with the compliant alternatives listed. A failed search is never reported as "no jobs".

| Document | |
|---|---|
| [docs/01-repository-audit.md](docs/01-repository-audit.md) | JobAggregator vs JobSync vs freehire, and why LogiDx was built new |
| [docs/adr/0001-foundation.md](docs/adr/0001-foundation.md) | Architecture decision record |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Components, data flow, data model, scheduling, security |
| [docs/02-sources.md](docs/02-sources.md) | Every target source: status, access method, how to enable it |
| [TASKS.md](TASKS.md) | What is implemented, tested, blocked or planned |
| [CLAUDE.md](CLAUDE.md) | Conventions and state for future development sessions |

## Quick start (local, SQLite)

Requires Python 3.12+.

```bash
cd logidx
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env            # set LOGIDX_SECRET_KEY; LOGIDX_COOKIE_SECURE=false for plain http on localhost
logidx initdb                   # create the database, seed profile and recall cases
logidx create-user you@example.com
logidx serve                    # dashboard + scheduler on http://127.0.0.1:8780
```

Then, in this order:

1. **Add an Adzuna key** (`ADZUNA_APP_ID`, `ADZUNA_APP_KEY`; free at developer.adzuna.com). This is the broadest
   authorised Australian source available.
2. **Add employer and agency boards** to `config/watchlist.yaml`. The file explains how to read each identifier
   from a careers-page URL. Run `logidx probe` to test them live.
3. **Add `XAI_API_KEY`** to turn on Grok assessments, and set `LOGIDX_AI_DAILY_BUDGET_USD`.
4. **Upload your master CV** under Documents, and review the candidate profile under Settings.
5. **Configure SMTP** (for Gmail, use an App Password) to receive the daily report.

Run a cycle at any time with the **Run now** button or `logidx run`.

## Commands

| Command | Purpose |
|---|---|
| `logidx initdb` | Apply migrations; seed the candidate profile and recall cases |
| `logidx create-user EMAIL` | Create a dashboard user, or reset a password |
| `logidx serve [--host --port]` | Dashboard and in-process scheduler (06:00, 14:00, 20:00 Melbourne by default) |
| `logidx run [--report]` | One discovery cycle now (optionally build and send the daily report) |
| `logidx probe` | One live request per configured source and to the xAI API; shows what actually works |
| `logidx assess [--limit N]` | AI-assess pending relevant vacancies |
| `logidx recall` | Evaluate known-vacancy cases and taxonomy fixtures |
| `logidx report [--send]` | Print today's report, or email it |

## Production (Docker Compose, PostgreSQL)

```bash
cd logidx
cp .env.example .env     # set LOGIDX_SECRET_KEY, POSTGRES_PASSWORD and the integrations you use
docker compose up -d --build
docker compose exec app logidx create-user you@example.com
```

- The app listens on `127.0.0.1:8780` only. Put a TLS reverse proxy in front (for example, Caddy:
  `logidx.example.com { reverse_proxy 127.0.0.1:8780 }`), and keep `LOGIDX_COOKIE_SECURE=true`.
- The `backup` service writes a gzipped `pg_dump` to `./backups` at 02:15 every night and keeps 14 days.
  Restore with `gunzip -c backups/logidx-DATE.sql.gz | docker compose exec -T db psql -U logidx logidx`.
- `config/` is mounted, so changes to the taxonomy, watchlist or recall cases apply on the next run without a rebuild.
- Monitor `GET /healthz`, which returns the last run's time and status. The daily report lists failures and remediation.
- Run a single app instance. Scheduled slots carry idempotency keys and runs take a database lock, so duplicates
  are refused, but one instance avoids contention.

The Compose file has not been run end to end yet: the build environment had no Docker daemon (see TASKS.md).

## Tests

```bash
pytest -p no:warnings          # 139 offline tests; external services are mocked
pytest -m live                 # reserved for live integration tests (none written yet)
```

Passing unit tests are not the same as working live integrations. Each adapter's live status is recorded in
[docs/02-sources.md](docs/02-sources.md).
