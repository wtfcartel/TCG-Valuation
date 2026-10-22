# CLAUDE.md — LogiDx Executive Search

LogiDx lives in `logidx/`, inside a repository that also contains an unrelated app (Cardcore, under `apps/` and
`packages/`). Do not modify Cardcore when working on LogiDx.

## Read first
`README.md` (setup) · `ARCHITECTURE.md` (design rules; do not break them) · `TASKS.md` (current state) ·
`docs/02-sources.md` (which sources really work).

## Non-negotiables from the brief
- Never bypass CAPTCHAs, logins, anti-bot interstitials or robots.txt, and never use undocumented internal APIs
  meant to get around them. SEEK, LinkedIn, Indeed, Google Jobs, Jora, CareerOne and Workforce Australia stay
  restricted until an authorised route exists.
- Never report a failed or skipped search as zero results, and never claim complete coverage.
- Never invent candidate facts. AI may cite only profile evidence IDs or "CV"; validation rejects anything else.
- Never auto-submit applications or send messages. Only record that an email was sent when the provider confirmed it.
- Never delete vacancy history. Lifecycle changes are events.
- Never hard-code secrets. They come from environment variables only and are redacted from logs.
- Never guess employer ATS identifiers. Leave them blank until confirmed, and test with `logidx probe`.

## Conventions
- Python 3.12+, SQLAlchemy 2 typed models, Pydantic 2, ruff (line length 120; `ruff format`).
- Every timestamp is stored as aware UTC (`UTCDateTime`); display uses Australia/Melbourne.
- Shared vocabularies live in `enums.py`.
- Schema change: edit `models.py`, then
  `alembic -c alembic.ini revision --autogenerate -m "..."`, then review the file.
  `test_migrations_match_models` fails if you forget.
- Adapters return `FetchResult` and raise `SourceError(blocked=...)`. Set `truncated=True` for incomplete listings.
- Tests: offline only, with respx for HTTP and synthetic payloads in `tests/payloads.py` (employer names end in
  "(Fixture)"). Mark live tests `@pytest.mark.live`.
- Commands: `pip install -e '.[dev]'`, `ruff check src tests`, `pytest -p no:warnings`.

## Current state (2026-10-22)
Phases 0–2 are implemented. Phase 3 is largely implemented. Phase 4 is partly done (tracking, CV import, manual
import, recruiters). No live integration has been verified — see TASKS.md for the blocked items.
