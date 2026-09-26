# 02 — Architecture, database schema and API

## Components

```
apps/web          React PWA (responsive, installable, offline shell)
   │  HTTPS / JSON (Bearer JWT)
apps/api          Fastify API — auth, ledger, evidence ingestion, insurance, reports, PDF
   │                 │
   │                 └── sources/   pricing & catalogue ADAPTERS (demo, tcgdex, restricted stubs…)
   │
packages/engine   Pure, deterministic valuation engine (Comparable Sales Method) — no I/O
   │
PostgreSQL        append-only tables enforced by triggers
```

The engine has no database or network access. It takes evidence, FX quotes and methodology parameters, and returns a result plus an `inputsHash`. This keeps the methodology reviewable in isolation: a reviewer can read `packages/engine/src/engine.ts` and its tests without learning the rest of the system.

## The three separate layers

| Layer | Question it answers | Tables | Mutability |
|---|---|---|---|
| **Market data** | "What happened in the market?" | `data_sources`, `card_identities`, `price_observations` (+ view `comparable_sales`), `fx_rates` | Observations and FX rates are append-only |
| **Valuation engine** | "What is it worth, by our documented rules?" | `methodology_versions`, `reviewers`, `methodology_reviews`, `valuations`, `valuation_comparables`, `valuation_overrides` (+ view `valuations_effective`) | Append-only |
| **Ledger** | "What did the user own and insure, and when?" | `collections`, `assets`, `grading_records`, `ownership_events`, `asset_photos`, `insurance_schedules`, `insurance_events`, `insurance_event_lines`, `reports` | Append-only (except `users`, `collections`, `insurance_schedules` settings) |

They are joined only by foreign keys. There is no table or calculation that mixes raw prices, conclusions and ownership.

## Mapping to the suggested entities

| Suggested entity | Implementation |
|---|---|
| User | `users` (role: collector / valuer / admin) |
| Collection | `collections` |
| Asset / OwnedAsset | `assets`: the physical item, with a human-readable `asset_ref` (`CC-1000`) |
| CardIdentity | `card_identities` (singles and sealed products) |
| GradingRecord | `grading_records` (grading company, cert, grade, raw condition; effective-dated) |
| AcquisitionEvent / DisposalEvent | `ownership_events` with `event_type` ∈ acquisition, disposal, loss, damage |
| PriceObservation / ComparableSale | `price_observations`; `comparable_sales` is the view of `observation_kind = 'completed_sale'` |
| Valuation / ValuationComparable / ValuationOverride | `valuations`, `valuation_comparables` (used **and** rejected, with reason), `valuation_overrides` |
| MethodologyVersion / Reviewer | `methodology_versions`, `reviewers`, `methodology_reviews` |
| InsuranceSchedule / InsuranceEvent | `insurance_schedules`, `insurance_events` (hash-chained), `insurance_event_lines` |
| AuditEvent | `audit_events` |
| (report snapshot) | `reports`: immutable payload plus SHA-256 |

The full DDL is in [`apps/api/migrations/001_init.sql`](../apps/api/migrations/001_init.sql).

## Invariants

1. **Append-only.** `cardcore_make_append_only()` installs `BEFORE UPDATE OR DELETE` and `BEFORE TRUNCATE` triggers that raise an error. Corrections are new rows: a new grading record, a new valuation with `supersedes_valuation_id`, or an override row.
2. **Point in time.** Quantity held on date *D* = Σ acquisitions − Σ disposals/losses with `effective_date ≤ D`. Market value on *D* = the latest concluded market/historical valuation with `valuation_date ≤ D`. Every event also has `recorded_at`, so `?knownAt=` gives the bitemporal view ("what did we believe on that day").
3. **Evidence separation.** `observation_kind` separates completed sales, asking prices and price guides. The engine rejects the latter two with `NOT_COMPLETED_SALE`, and the rejection is stored.
4. **User-supplied evidence is private.** `manual` and `csv_import` observations are used only in valuations of assets owned by the user who recorded them. This prevents one user's entries from moving another user's values.
5. **Insurance events never overwrite.** Each event reads `previous_declared_minor` from the prior event, adds its line deltas, and stores `event_hash = sha256(canonical(event, lines, prev_hash))`. `GET /api/schedules/:id` re-verifies the chain.
6. **Reports are snapshots.** The payload is frozen at generation and hashed. The PDF is rendered deterministically from the stored payload.
7. **Money** is stored as integer minor units plus an ISO-4217 code. FX rates are stored with source and date, and each comparable records the rate, date and source used.

## API structure (all JSON; `Authorization: Bearer <jwt>`)

| Area | Endpoint | Purpose |
|---|---|---|
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/me` | Account; a default collection is created on registration |
| Catalogue | `GET /api/catalog/search?q=&game=` | Search local catalogue |
| | `POST /api/catalog/cards` | Create or find an identity (idempotent on natural key) |
| | `GET /api/catalog/remote?source=tcgdex&q=` · `POST /api/catalog/import` | Search an external catalogue adapter and import an identity (price-guide data is stored as `price_guide`) |
| Collection | `GET/POST /api/collections` | |
| | `GET/POST /api/collections/:id/assets` | Positions / add a physical asset (creates the asset, initial grading record and acquisition event) |
| | `GET /api/collections/:id/portfolio?date=&knownAt=` | Totals (market, insured, cost, unrealised, realised), value by set / grading company / category, largest assets |
| | `GET /api/collections/:id/portfolio/history?from=&to=&points=` | Time series for the chart |
| Asset | `GET /api/assets/:id` | Current state + full history |
| | `POST /api/assets/:id/grading` | Grading change (plus automatic insurance revaluation event) |
| | `POST /api/assets/:id/disposals` · `/losses` | Mark sold / lost (plus automatic insurance adjustment) |
| | `POST /api/assets/:id/photos` · `GET /api/photos/:id` | User photographs (SHA-256 recorded) |
| Evidence | `GET /api/assets/:id/evidence` | Observations for the asset's identity |
| | `POST /api/assets/:id/evidence/import {sourceId}` | Pull from an adapter (fails closed if unlicensed) |
| | `POST /api/assets/:id/evidence` · `/evidence/csv` | Manual sale record / auction-result CSV |
| Valuation | `POST /api/assets/:id/valuations {purpose, valuationDate?, exclusions[]}` | Run the engine; store the result and every comparable |
| | `GET /api/assets/:id/valuations` · `GET /api/valuations/:id` | History / full audit detail |
| | `POST /api/valuations/:id/overrides` | Override with reason and identity |
| FX | `GET/POST /api/fx-rates` | Documented rates |
| Insurance | `GET/POST /api/collections/:id/schedules` · `GET /api/schedules/:id` | Schedule, events, chain verification |
| | `POST /api/schedules/:id/reconcile` | Revalue held assets for insurance; append acquisition/initial-declaration and revaluation events |
| | `POST /api/schedules/:id/adjustments` | Insurer adjustment event |
| Reports | `POST /api/collections/:id/reports/valuation` · `POST /api/schedules/:id/reports/adjustment` | Generate immutable report |
| | `GET /api/reports/:id` · `GET /api/reports/:id/pdf` | Insurer JSON payload (with integrity check) / PDF |
| Reference | `GET /api/methodology` · `GET /api/sources` · `GET /api/audit` | Methodology versions and reviews; adapter registry with licence status; audit trail |

### Insurer payload (`cardcore.insurance-adjustment/1`)

`policy {insurer, policyReference, customerReference}`, `previousDeclaredValueMinor`, `revisedDeclaredValueMinor`, `netChangeMinor`, `effectiveDate`, `adjustments[] {seq, type, reason, previous, revised, eventHash, prevHash}`, `assetsAdded[]`, `assetsRemoved[]`, `assetsRevalued[]`, `evidence[] {valuationId, method, confidence, comparablesUsed, inputsHash}`, `methodology {id, reviewStatement}`, `insurerRules`, `disclaimer`, and the report `version` plus `sha256`. Consecutive reports cover consecutive event ranges (`eventRange.fromSeq/toSeq`), so an insurer can verify there are no gaps.

`notification_rules` (for example, ±10%, ±$2,500, quarterly) are **stored but not acted on**. Cardcore never computes premiums; the rules exist so a later notification service can tell the insurer when a threshold is crossed.

## Later phases (explicitly out of Phase 1)

Payments, underwriting and premium calculation · camera scanner · licensed eBay/auction feeds · PSA cert verification · notification service for insurer rules · valuer/reviewer workflow (assignment review sign-off) · object storage for photos (S3-compatible) · per-insurer API credentials and webhooks.
