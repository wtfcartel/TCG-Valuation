# 03 — Licensing and IP risk register

> This is an engineering risk assessment, not legal advice. Items marked **(verify)** need confirmation by counsel or the vendor before commercial launch.

## Code licences

| Risk | Detail | Mitigation in Cardcore |
|---|---|---|
| **AGPL contamination** (The Tin, PokéCollector) | Incorporating or modifying AGPL-3.0 code in a network service obliges Cardcore to offer the complete corresponding source of the combined work to all users (§13). | No code, schema DDL, UI text or assets were copied. Only general concepts are reused (collection tracking, snapshots, P&L), and those are not protected expression. Keep this rule: **engineers must not paste from AGPL repositories.** If a contributor studies AGPL code in depth, prefer that someone else implements the equivalent feature from a written functional spec. |
| **Unlicensed code** (Pokémon Card Tracking) | No licence means no permission to copy, modify or distribute. | Not used. Its scraping approach is also rejected on terms-of-service grounds (below). |
| **MIT code** (CardScope) | Reuse is permitted with the copyright notice. | Nothing reused. If code is ever reused, add it to `THIRD_PARTY_NOTICES.md`. |
| **Trademarks of the reference projects** | "The Tin" name and icon are expressly reserved. | Cardcore uses its own name and branding. |
| **Dependencies** | All runtime dependencies are MIT/BSD/Apache-style (Fastify, pg, zod, jose, pdfkit, React). | Add a licence check (e.g. `license-checker --onlyAllow`) to CI before launch **(to do)**. |

## Game IP (Pokémon, One Piece, MTG, Yu-Gi-Oh!)

| Risk | Mitigation |
|---|---|
| Card names, set names and logos are trademarks; card artwork is copyrighted by the publishers. | Cardcore stores factual identifiers (names, numbers) for identification, and displays **user-uploaded photographs** rather than hosting official artwork. Any catalogue image URLs from TCGdex are shown only as optional references and are not re-hosted **(verify before enabling)**. Include a non-affiliation notice in the UI and reports. |
| Implying endorsement | No publisher logos; "independent valuation service" wording. |

## Market-data rights

| Risk | Mitigation |
|---|---|
| **Scraping** marketplaces (eBay, Cardmarket, TCGplayer, PriceCharting, PSA APR, auction houses) breaches their terms. In the UK/EU, bulk extraction can also infringe the sui generis **database right**. | Cardcore contains **no scrapers**. Automated evidence comes only from adapters backed by a licence or an open API. Restricted sources are registered as `restricted` and fail closed. |
| Redistribution of licensed prices in reports and insurer payloads | Individual sale facts cited as evidence, with source and URL, are low risk. Redistributing a vendor's aggregate price guide usually requires permission. Price guides are stored as `price_guide` and are **never** placed in insurer evidence. Confirm redistribution rights in each data licence **(verify)**. |
| User-supplied evidence | Users warrant they may use the data they import. Their entries are scoped to their own valuations and are never shared across tenants. |

## Professional-representation risk

| Risk | Mitigation |
|---|---|
| Implying a CA/CPA certified every valuation when they only reviewed the methodology | The report generator always states that a methodology review addresses the **methodology only** and that the reviewer has not reviewed or certified the individual valuations unless the report says so. Responsibility for individual valuations is attributed to the named valuer. If no review exists, the report says "has not been independently reviewed". |
| Holding out as a licensed valuer / insurance intermediary | Cardcore reports values and changes; it does **not** calculate premiums, give cover advice or bind insurers. The disclaimer is in every insurer payload. Check local regulations on insurance distribution and valuation services before launch **(verify)**. |
| Personal data (email, collection value, photos) | Photos are stored privately and served only to their owner. Use access control and encryption at rest in production. A GDPR / Australian Privacy Act assessment is required before launch **(to do)**. |
