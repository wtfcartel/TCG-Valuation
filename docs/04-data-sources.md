# 04 — Valuation data sources: access and legal reusability

The key distinction for Cardcore is **transaction-level completed-sale evidence** (usable as comparables) versus **aggregate price guides and asking prices** (context only). Most "free" TCG price feeds are aggregates, so they cannot serve as comparables under the methodology.

Status below reflects what is publicly known and what the reference projects actually use. Vendor terms change, so **every row marked (verify) needs written confirmation before commercial use.**

| Source | Data type | Access | Commercial reuse in a SaaS | Cardcore status |
|---|---|---|---|---|
| **TCGdex** (api.tcgdex.net) | Multilingual Pokémon catalogue; embeds Cardmarket and TCGplayer aggregate prices | Free, open REST API, no key | Card database is MIT-licensed (confirmed in CardScope's THIRD_PARTY_NOTICES). Artwork and trademarks are not licensed. Embedded prices come from third parties, so their reuse terms follow the original vendor **(verify)** | `tcgdex` adapter: catalogue search/import; prices stored as `price_guide` only |
| **Scryfall** (MTG) | Catalogue; TCGplayer/Cardmarket price snapshots | Free API with rate limits | Catalogue use is allowed under their guidelines; you may not paywall Scryfall data, and prices are indicative **(verify)** | Candidate MTG catalogue adapter (Phase 2) |
| **YGOPRODeck** (Yu-Gi-Oh!) | Catalogue; price aggregates | Free API; images must be cached locally | Terms restrict hot-linking; commercial terms unclear **(verify)** | Candidate catalogue adapter |
| **One Piece TCG** | No official API; community datasets | Varies | Unclear; treat as manual catalogue entry | Manual `card_identities` |
| **eBay Marketplace Insights API** | **Sold items, ~90 days, transaction-level** (best completed-sale source for raw and graded cards) | Limited Release; needs eBay business approval | Allowed within the licence; display and retention rules apply **(verify)**. The Browse API returns *active listings* (asking prices) only. Scraping sold listings breaches the User Agreement | Registered `restricted`; highest-priority licence to pursue |
| **Cardmarket API** | Price guide (trend/avg/low), listings | Approved partners/sellers only | Redistribution needs permission; aggregates are not transactions | `restricted`; aggregates → `price_guide` only |
| **TCGplayer API / tcgcsv mirror** | Market price (aggregate), listings | New API keys largely unavailable; tcgcsv is an unofficial daily mirror (used by The Tin) | tcgcsv carries no commercial licence, so it is high risk for a proprietary SaaS | `restricted` |
| **PriceCharting API** | Price guide by grade (derived from sales) | Paid subscription | Commercial redistribution needs agreement; scraping prohibited **(verify)** | `restricted` |
| **PSA Public API** | Cert verification (grade, card details) | Free token, low daily quota | Verification use fine; population and APR (auction prices) need a commercial agreement **(verify)** | `psa` `restricted`. Cert verification is the natural first integration, because it raises grading certainty in the confidence classification |
| **Auction houses** (Goldin, Heritage, Fanatics Collect, PWCC) | Hammer + buyer's premium, **transaction-level** | Public results pages, no open API | Citing individual lots (facts with URL) as evidence is low risk; systematic extraction may breach terms/database right. Heritage and others license data **(verify)** | `manual` entry and `csv_import` today; `auction_house` licensed feed later |
| **Commercial sales-data vendors** (e.g. Card Ladder, Alt, 130point, CardHedger, PokemonPriceTracker, JustTCG) | Varies: some provide transaction-level sold data, others aggregates | Paid APIs | Licence terms decide whether per-transaction data can go into reports **(verify each)** | Implement as new `SourceAdapter`s once licensed |
| **ECB euro reference rates** | Daily FX | Free, public | Free reuse with attribution | Recommended FX source; add a scheduled importer (Phase 2). Manual/API entry exists now (`POST /api/fx-rates`) |

## Unlicensed / scraped evidence (business-accepted risk)

On 2026-09-26 the product owner chose to use eBay sold-listing data without a licence from eBay, accepting the risk of a cease-and-desist.

- **`ebay_sold_scrape`** (licence status `unlicensed`). Ingests *saved* eBay "Sold items" result pages (`POST /api/assets/:id/evidence/ebay-page`, or the "Import saved eBay sold page" button in the UI). The parser handles both the older `s-item` and newer `s-card` markup. Titles are matched to the catalogue identity on name, card number, language and edition. Listings that don't match are dropped: lots, proxies, "PSA 10 candidate" raw cards, price ranges, wrong language or edition. The grade is parsed from the title; the raw condition only if the title states it.
- **Best Offer sales** are stored but marked `unverified`, so the engine rejects them. eBay shows the struck-through asking price, not the accepted price.
- **Labelling.** Every such comparable is tagged UNLICENSED/SCRAPED in the evidence schedule. Both the valuation report and the insurer adjustment report include an "Evidence provenance" disclosure giving the count. Insurers relying on the report can therefore see the provenance.
- **Not built:** an automated live fetcher. This environment's safety controls blocked contacting eBay/Whatnot, so it needs the owner to enable that access. Any fetcher would be limited to public pages, rate-limited, and would identify itself honestly. It would have no logins, CAPTCHA solving or bot-detection evasion. **Whatnot** is deferred until it is confirmed which sold data, if any, is visible publicly without logging in.
- The parser was built against a representative fixture. **Validate it against real saved pages** before relying on it; eBay changes its markup.

## What is genuinely usable today, without a commercial agreement

1. **Catalogue:** TCGdex (Pokémon), plus manual catalogue entries for every other game.
2. **Completed-sale evidence:** user- or valuer-recorded individual sales with source URL and reference (`manual`), and user-supplied auction-result exports (`csv_import`: `sale_date, venue, amount, currency, buyers_premium, source_reference, source_url, grading_company, grade, condition, arms_length, verified`).
3. **FX:** ECB reference rates.

Everything else needs a licence. The adapter interface (`apps/api/src/sources/types.ts`) means adding one is a new file plus a registry line; the valuation engine, ledger and reports stay unchanged.

## Per-observation metadata captured (all sources)

`source_id` (with licence status and reliability tier on `data_sources`), `source_reference` (transaction ID/lot), `source_url`, `observed_at` (sale date), `fetched_at`, `currency`, `amount_minor`, `buyers_premium_minor`, `arms_length`, `verification_status` (+ notes), `observation_kind`, and `raw_payload` (the unmodified source record).

## Note on this build

The development sandbox's network policy blocked `api.tcgdex.net`, so the TCGdex adapter was implemented against its documented response shape but **not exercised live**. It is enabled by `ENABLE_TCGDEX=true`; verify it in an environment with outbound access.
