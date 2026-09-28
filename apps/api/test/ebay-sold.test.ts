import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ebayPageToObservations, parseEbaySoldPage, parseGrading, parsePrice, parseSoldDate } from "../src/sources/ebay-sold.js";
import type { CardIdentityRow } from "../src/sources/types.js";

const html = readFileSync(join(__dirname, "fixtures", "ebay-sold-charizard.html"), "utf8");
const charizard: CardIdentityRow = {
  id: "id-1",
  game: "pokemon",
  product_type: "single",
  category: "card",
  set_code: "base1",
  set_name: "Base Set",
  card_number: "4/102",
  card_name: "Charizard",
  language: "en",
  edition: "unlimited",
  variant: "holo",
  rarity: null,
  external_refs: {},
};

describe("eBay sold-page parsing", () => {
  it("parses dates, prices and currencies in US and international formats", () => {
    expect(parseSoldDate("Sold  Sep 20, 2026")).toBe("2026-09-20");
    expect(parseSoldDate("Sold 5 Sep 2026")).toBe("2026-09-05");
    expect(parsePrice("$1,050.00", "USD")).toEqual({ amountMinor: 105000, currency: "USD", isRange: false });
    expect(parsePrice("AU $1,620.50", "USD")).toEqual({ amountMinor: 162050, currency: "AUD", isRange: false });
    expect(parsePrice("EUR 1.234,56", "USD")).toEqual({ amountMinor: 123456, currency: "EUR", isRange: false });
    expect(parsePrice("$10.00 to $20.00", "USD").isRange).toBe(true);
  });

  it("parses grades but treats 'PSA 10 candidate' as raw", () => {
    expect(parseGrading("Charizard PSA 9 MINT")).toEqual({ gradingCompany: "PSA", grade: "9" });
    expect(parseGrading("Charizard Beckett 9.5")).toEqual({ gradingCompany: "BGS", grade: "9.5" });
    expect(parseGrading("Charizard NM PSA 10 Candidate")).toEqual({ gradingCompany: null, grade: null });
  });

  it("reads both legacy and new result markup and skips the placeholder card", () => {
    const listings = parseEbaySoldPage(html);
    expect(listings).toHaveLength(8);
    expect(listings[0]).toMatchObject({ itemId: "305123456789", title: "Charizard 4/102 Base Set Unlimited Holo PSA 9 MINT Pokemon", soldDate: "2026-09-20" });
    expect(listings.find((l) => l.itemId === "305123456790")?.bestOfferAccepted).toBe(true);
    expect(listings.find((l) => l.itemId === "306000000001")).toMatchObject({ currency: "AUD", amountMinor: 162050, soldDate: "2026-09-05" });
  });

  it("keeps only listings that describe the catalogue identity and labels them unlicensed", () => {
    const r = ebayPageToObservations(html, charizard);
    expect(r.skipped).toEqual({ edition_mismatch: 1, language_mismatch: 1, excluded_term: 1, price_range: 1 });
    const refs = r.observations.map((o) => o.sourceReference).sort();
    expect(refs).toEqual(["ebay:305123456789", "ebay:305123456790", "ebay:305123456794", "ebay:306000000001"]);
    const bestOffer = r.observations.find((o) => o.sourceReference === "ebay:305123456790")!;
    expect(bestOffer.verificationStatus).toBe("unverified"); // hidden accepted price → rejected by the engine
    const raw = r.observations.find((o) => o.sourceReference === "ebay:305123456794")!;
    expect(raw).toMatchObject({ gradingCompany: null, grade: null, condition: "NM" });
    expect(r.observations.every((o) => o.verificationNotes?.startsWith("UNLICENSED/SCRAPED"))).toBe(true);
  });
});
