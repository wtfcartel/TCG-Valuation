/**
 * Registered market-data sources. Licence status is recorded on every observation's source
 * so a report can always state where evidence came from and on what terms it was used.
 * See docs/04-data-sources.md for the full legal/access assessment.
 */
export interface SourceDefinition {
  id: string;
  name: string;
  provides: Array<"catalogue" | "completed_sale" | "asking_price" | "price_guide" | "population" | "fx">;
  licenceStatus: "open" | "licensed" | "user_supplied" | "restricted" | "synthetic";
  licenceNotes: string;
  reliabilityTier: 1 | 2 | 3;
}

export const SOURCE_DEFINITIONS: SourceDefinition[] = [
  {
    id: "manual",
    name: "Manually recorded evidence",
    provides: ["completed_sale", "asking_price"],
    licenceStatus: "user_supplied",
    licenceNotes:
      "Individual sale facts recorded by the user or valuer with a source URL/reference. Visible only to the recording user's valuations.",
    reliabilityTier: 2,
  },
  {
    id: "csv_import",
    name: "Auction-result CSV import",
    provides: ["completed_sale"],
    licenceStatus: "user_supplied",
    licenceNotes:
      "User-supplied export of auction results (e.g. their own auction-house invoices or a licensed dataset). The user warrants they may use the data.",
    reliabilityTier: 2,
  },
  {
    id: "tcgdex",
    name: "TCGdex",
    provides: ["catalogue", "price_guide"],
    licenceStatus: "open",
    licenceNotes:
      "Open API; card database MIT-licensed. Card artwork/trademarks are NOT licensed. Embedded Cardmarket/TCGplayer figures are aggregate price guides, never completed-sale evidence.",
    reliabilityTier: 2,
  },
  {
    id: "demo",
    name: "Synthetic demo evidence",
    provides: ["completed_sale", "asking_price"],
    licenceStatus: "synthetic",
    licenceNotes: "Deterministic synthetic data for development and demos only. Disabled in production.",
    reliabilityTier: 3,
  },
  {
    id: "ebay_marketplace_insights",
    name: "eBay Marketplace Insights API",
    provides: ["completed_sale"],
    licenceStatus: "restricted",
    licenceNotes:
      "Sold-item data (≈90 days) is a Limited Release API requiring eBay business approval. Scraping eBay sold listings breaches the eBay User Agreement.",
    reliabilityTier: 1,
  },
  {
    id: "cardmarket",
    name: "Cardmarket API",
    provides: ["price_guide", "asking_price"],
    licenceStatus: "restricted",
    licenceNotes:
      "API access requires Cardmarket approval; the price guide is aggregate (trend/avg), not transaction-level. Redistribution needs written permission.",
    reliabilityTier: 2,
  },
  {
    id: "tcgplayer",
    name: "TCGplayer API",
    provides: ["price_guide", "asking_price"],
    licenceStatus: "restricted",
    licenceNotes:
      "New API keys have not been generally issued; market price is an aggregate. Third-party mirrors (e.g. tcgcsv) carry no licence for commercial reuse.",
    reliabilityTier: 2,
  },
  {
    id: "pricecharting",
    name: "PriceCharting API",
    provides: ["price_guide"],
    licenceStatus: "restricted",
    licenceNotes: "Paid API subscription; commercial redistribution requires agreement. Scraping prohibited by terms.",
    reliabilityTier: 2,
  },
  {
    id: "psa",
    name: "PSA Public API",
    provides: ["population"],
    licenceStatus: "restricted",
    licenceNotes:
      "Certificate verification via PSA Public API (token, rate-limited). Population and Auction Prices Realized data need a commercial agreement for SaaS reuse.",
    reliabilityTier: 1,
  },
  {
    id: "auction_house",
    name: "Auction-house results (licensed feed)",
    provides: ["completed_sale"],
    licenceStatus: "restricted",
    licenceNotes:
      "Goldin, Heritage, Fanatics Collect etc. publish results but offer no open API; bulk extraction may infringe terms and (UK/EU) database right. Use licensed feeds or cite individual lots manually.",
    reliabilityTier: 1,
  },
];
