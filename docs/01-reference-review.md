# 01 — Review of reference open-source projects

Reviewed 2026-09-26 from shallow clones of each project's default branch. I read the READMEs, licences, trademark and notice files, directory layouts, data-model class names and data-source adapters. **No code from any of these repositories was copied into Cardcore.** Cardcore takes only general, non-copyrightable ideas (for example, "record a portfolio snapshot") and implements them independently.

## Summary

| | **The Tin** (`the-tin-app/the_tin`) | **PokéCollector** (`Git-Romer/pokecollector`) | **CardScope** (`rhanka/pokemon-cards`) | **Pokémon Card Tracking** (`TomasPereiraa/Pokemon-Card-Tracking`) |
|---|---|---|---|---|
| **Licence** | AGPL-3.0; name, icon and store listing reserved (TRADEMARK.md) | AGPL-3.0 | **MIT** (not AGPL); third-party notices kept separately | **No licence file, so all rights are reserved.** No reuse is permitted. |
| **Shape** | Native iOS (SwiftUI, 339 Swift files), local-first, no accounts; Node/TS catalogue pipeline and a static catalogue server | Self-hosted web app: FastAPI + SQLAlchemy + PostgreSQL 18, React 18/Vite/Tailwind, Docker Compose | Svelte PWA + TypeScript Hono/Node API, SQLite, IndexedDB offline cache and outbox | Windows desktop Python script: SeleniumBase scraper, CSV/JSON files, matplotlib charts |
| **Games** | Pokémon | Pokémon | Pokémon | Anything listed on Cardmarket |
| **Multi-user** | No (on-device) | Yes (JWT, admin, reverse-proxy auth) | Yes (OIDC enrolment) | No |
| **Pricing data** | TCGdex, tcgcsv (TCGplayer mirror), Cardmarket trends; graded prices and population from a paid commercial API | TCGdex (which embeds Cardmarket/TCGplayer aggregates); Frankfurter FX | TCGdex catalogue only; market quotes **off by default** until data rights are confirmed | Scrapes Cardmarket, PSA certificate pages and PriceCharting |
| **Valuation approach** | Single "market price" per card and condition, plus graded prices | Latest price times quantity; portfolio snapshots; realised/unrealised P&L | Low/market/high quote with source, freshness and confidence | Cardmarket trend and 30-day average; PSA estimate |
| **Audit / immutability** | None beyond price history | Mutable rows; snapshot table; product ledger entries | Append-style collection events (zod schema) | Overwrites; deletes history when a card is removed from the CSV |
| **Insurance** | Printable "insurance report" PDF (collection × value) | None | None | None |
| **Maturity** | Shipping App Store product (v1.0.3) | Active; README calls it "unapologetically vibecoded" | Pilot/POC with strong documentation and data-rights discipline | Hobby script |

## Useful ideas (concepts only, re-implemented)

| Concept | Seen in | How Cardcore handles it |
|---|---|---|
| Card catalogue keyed by set, number, language and variant | All | `card_identities` with a natural-key unique index that also covers edition and product type |
| Variants and conditions per physical copy | The Tin, PokéCollector | `grading_records` (append-only) per asset: grading company, grade, cert number, raw condition |
| Purchase price vs market value, realised/unrealised P&L | PokéCollector | Derived at a point in time from `ownership_events` plus the valuation in force (`computePortfolio`) |
| Portfolio snapshots/history | PokéCollector | Not stored as snapshots. History is **recomputed** from immutable events and valuations, so it can never drift from the ledger |
| Sealed product tracking | PokéCollector, The Tin | `product_type = 'sealed'` plus `category` on the same identity table |
| Insurance PDF | The Tin | Replaced by a defensible valuation report and a hash-chained insurance adjustment report |
| Source, freshness and confidence on every quote; fail-closed data-rights switches | CardScope | Every observation carries source, reference, fetched time and verification status. Restricted sources are registered but fail closed until licensed |
| Offline PWA shell | CardScope | Service worker caches the shell only. Valuation/ledger data is never served stale |
| Docker Compose deployment with PostgreSQL | PokéCollector | `Dockerfile` + `docker-compose.yml` |
| Scanner (on-device OCR/fingerprints; LLM vision) | The Tin, PokéCollector | Deferred to a later phase (a mobile-friendly scanner is not in the Phase 1 scope) |
| Population data | The Tin (commercial API) | Registered as `psa` (restricted). Needs a commercial agreement |

## What none of them do (Cardcore's differentiation)

- A documented **comparable-sales methodology** that uses completed transactions only, with dispersion escalation, documented exclusions, a record of rejected evidence and a methodology version.
- A distinction between **Market**, **Insurance/Replacement** and **Historical** value.
- An **append-only ledger** enforced by the database, with point-in-time and "as known at" queries.
- An **insurance schedule as a hash-chained event log**: each Insurance Adjustment Event records the previous and revised declared value.
- Separation of methodology **validation** from individual valuation **responsibility** in reports.

## Recommendation: build new; do not fork

**Build Cardcore as a new, clean-room application. Borrow concepts, not code.**

1. **Licence fit.** The two most feature-rich candidates (The Tin, PokéCollector) are AGPL-3.0. AGPL §13 requires offering the complete corresponding source to every user who interacts with a modified version over a network. That conflicts with a proprietary SaaS that may later integrate with insurers. Forking would either force Cardcore to be open source or require a rewrite later.
2. **Architecture fit.** None of the four has the core Cardcore primitives: immutable evidence, comparable-sales valuation, a valuation audit trail or an insurance ledger. Retro-fitting append-only semantics onto PokéCollector's mutable ORM model would touch almost every table and service. That is a rewrite in all but name, while still carrying AGPL obligations.
3. **Platform fit.** The Tin is native iOS and deliberately account-less and local-first, which is the opposite of an insurer-facing multi-user register. Pokémon Card Tracking is an unlicensed scraper and must not be used.
4. **CardScope is MIT**, so its code *could* legally be reused with attribution. It is still a single-game Svelte/SQLite pilot whose value is mostly in its data-rights discipline, which Cardcore adopts as a design principle. Nothing was copied. If code is ever reused from it, keep its copyright notice in `THIRD_PARTY_NOTICES.md`.

The chosen stack is TypeScript end to end: a pure valuation-engine package, a Fastify API, PostgreSQL and a React PWA. It follows the brief's architecture preference and keeps the valuation engine independently testable and reviewable.
