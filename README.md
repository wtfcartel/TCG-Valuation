# Cardcore — TCG Collection Valuation & Insurance Ledger

Cardcore is a live **asset register and valuation ledger** for trading-card collectors (Pokémon, One Piece, MTG, Yu-Gi-Oh! and more). It combines collection tracking, a documented **Comparable Sales Method**, and an **insurance schedule** that records every change in declared value as an immutable, hash-chained adjustment event.

> Phase 1 MVP. No payments, underwriting or premium calculation. Cardcore reports value changes; insurers decide what they mean for cover.

## Documents

| | |
|---|---|
| [01 — Reference project review & build-vs-fork recommendation](docs/01-reference-review.md) | The Tin, PokéCollector, CardScope, Pokémon Card Tracking |
| [02 — Architecture, database schema, API](docs/02-architecture.md) | Three separated layers; append-only invariants; endpoint map |
| [03 — Licensing & IP risk register](docs/03-licensing-and-ip.md) | AGPL, game IP, market-data rights, professional representation |
| [04 — Data sources](docs/04-data-sources.md) | Which valuation sources are accessible and legally reusable |
| [Methodology CSM-1.0.0](docs/methodology/CSM-1.0.0.md) · [CSM-1.1.0](docs/methodology/CSM-1.1.0.md) | The valuation rules the engine implements (1.1.0 adds cross-source de-duplication) |

## Repository layout

```
packages/engine   Pure valuation engine (comparable selection, stats, escalation, confidence) + unit tests
apps/api          Fastify API, PostgreSQL migrations, pricing-source adapters, insurance ledger, reports, PDF
apps/web          React PWA (dashboard, add asset, valuation/evidence, insurance, reports)
docs/             Analysis, design and methodology
```

## Phase 1 scope delivered

User accounts · catalogue search/create (plus TCGdex import) · add physical card or sealed product · grade/condition · purchase info · import comparable-sale evidence (adapter, manual, CSV) · three-sale mean/median with dispersion warning and escalation · documented exclusions and overrides · collection totals and breakdowns · mark sold / lost · automatic portfolio and insurance updates · point-in-time history · valuation PDF · insurance adjustment report (JSON + PDF).

## Run locally

Requirements: Node 22+, PostgreSQL 14+.

```bash
npm install
cp .env.example .env            # adjust DATABASE_URL / JWT_SECRET
createdb cardcore               # or use docker compose below
npm run migrate
npm run seed                    # optional demo data: demo@cardcore.local / cardcore-demo-password
npm run dev:api                 # http://localhost:8080
npm run dev:web                 # http://localhost:5173 (proxies /api)
```

Tests (the API suite needs a disposable PostgreSQL database; it **drops and recreates** the `public` schema):

```bash
TEST_DATABASE_URL=postgres://cardcore:cardcore@localhost:5432/cardcore_test npm test
npm run typecheck
```

### Docker

```bash
JWT_SECRET=$(openssl rand -hex 32) docker compose up --build
# app on http://localhost:8080 — serves the PWA and the API; migrations run on start
```

`ENABLE_DEMO_SOURCE` defaults to `false` in production. The synthetic demo evidence source is for development only.

## Design principles

1. **Market data, valuation engine and insurance ledger are separate** (tables, code and calculations).
2. **Append-only.** Ledger, evidence, valuations, insurance events, reports and audit rows cannot be updated or deleted; database triggers enforce this.
3. **Asking prices are never evidence.** Every observation is typed; rejected evidence is stored with its reason.
4. **No fake precision.** Confidence is High / Moderate / Limited, derived by published rules from stored factors.
5. **Adapters, not dependencies.** Each pricing source implements `SourceAdapter`; unlicensed sources are registered but fail closed.
6. **Methodology validation ≠ valuation responsibility.** Reports always make this distinction explicit.
