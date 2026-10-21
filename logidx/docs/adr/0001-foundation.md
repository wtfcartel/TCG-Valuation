# ADR-0001 — Build LogiDx as a new modular Python application

Status: Accepted, 2026-10-21

## Context

The brief asks for an auditable executive job-discovery system for one Melbourne-based executive,
with independent source adapters, a nine-discipline daily coverage audit, verification states,
AI assessment through xAI Grok, and recall regression testing. Three open-source projects were
audited ([01-repository-audit.md](../01-repository-audit.md)).

## Decision

Build a new application, `logidx/`, in Python 3.12+ with FastAPI, SQLAlchemy 2, Alembic, Pydantic 2,
APScheduler 3 and httpx. Server-rendered Jinja templates provide the dashboard; every page has a JSON
equivalent under `/api` so a React front end can be added later without backend changes.

No code is copied from the audited repositories. Ideas adopted are credited where implemented.

## Consequences

- One process, one database. SQLite for local use, PostgreSQL in Docker Compose / production.
- Discovery quality depends on configuring employer ATS boards and an Adzuna key; the coverage
  matrix makes any gap visible.
- SEEK, LinkedIn, Indeed, Google Jobs, Jora, CareerOne and Workforce Australia are modelled as
  restricted sources that record NOT SEARCHED with a reason, until a compliant route exists.
- The application tracker is smaller than JobSync's at first; its data model leaves room for stages,
  contacts and documents (Phase 4).

## Alternatives rejected

- Fork JobAggregator: no licence file, scraping-based sources, deletes history, India-specific.
- Fork JobSync: discovery limited to Greenhouse/Lever/Ashby; TypeScript stack.
- Fork freehire: six-service stack and high upstream churn for a single-user tool; IT-focused
  dictionaries; SEEK adapter conflicts with the brief's access rules.
