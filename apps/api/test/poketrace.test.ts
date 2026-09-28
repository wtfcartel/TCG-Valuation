import { describe, expect, it } from "vitest";
import { expectedVariant, PokeTraceAdapter } from "../src/sources/poketrace.js";
import type { CardIdentityRow, EvidenceQuery } from "../src/sources/types.js";

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

const cards = [
  { id: "pt-1st", name: "Charizard", cardNumber: "4", set: { slug: "base-set", name: "Base Set" }, variant: "1st_Edition_Holofoil", game: "pokemon", market: "US", currency: "USD", prices: {}, lastUpdated: null },
  {
    id: "pt-unl",
    name: "Charizard",
    cardNumber: "004/102",
    set: { slug: "base-set", name: "Base Set" },
    variant: "Unlimited_Holofoil",
    game: "pokemon",
    market: "US",
    currency: "USD",
    lastUpdated: "2026-09-27T00:00:00Z",
    prices: {
      ebay: { PSA_9: { avg: 1050.5, low: 900, high: 1200, lastUpdated: "2026-09-27T00:00:00Z", saleCount: 14 } },
      tcgplayer: { NEAR_MINT: { avg: 400, low: 350, high: 450, lastUpdated: "2026-09-27T00:00:00Z" } },
    },
  },
];

const listings = [
  { id: 1, sourceItemId: "305000000001", listingType: "Auction", title: "Charizard PSA 9", price: 1040, currency: "USD", listingUrl: "https://www.ebay.com/itm/305000000001", condition: null, grader: "PSA", grade: "9", soldAt: "2026-09-25T10:00:00Z", anomalyFlag: null, anomalyReason: null },
  { id: 2, sourceItemId: "305000000002", listingType: "BestOffer", title: "Charizard PSA 9", price: 1300, currency: "USD", listingUrl: "https://www.ebay.com/itm/305000000002", condition: null, grader: "PSA", grade: "9", soldAt: "2026-09-24T10:00:00Z", anomalyFlag: null, anomalyReason: null },
  { id: 3, sourceItemId: "305000000003", listingType: "FixedPrice", title: "Charizard PSA 9 lot", price: 99, currency: "USD", listingUrl: "https://www.ebay.com/itm/305000000003", condition: null, grader: "PSA", grade: "9", soldAt: "2026-09-23T10:00:00Z", anomalyFlag: "price_outlier", anomalyReason: "90% below median" },
];

function mockFetch(opts: { listingsStatus?: number; plan?: string } = {}) {
  const calls: string[] = [];
  const impl = (async (input: string | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    calls.push(`${url.pathname}?${url.searchParams.toString()}`);
    expect((init?.headers as Record<string, string>)["X-API-Key"]).toBe("pc_test");
    const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
    if (url.pathname === "/v1/auth/info") {
      return json(200, { data: { key: "pc_…", name: null, active: true, createdAt: "2026-09-28T00:00:00Z", user: { plan: opts.plan ?? "Pro", daily: { remaining: 9990, limit: 10000, resetsAt: "2026-09-29T00:00:00Z" } } } });
    }
    if (url.pathname === "/v1/cards") return json(200, { data: cards, pagination: { hasMore: false, nextCursor: null, count: 2 } });
    if (url.pathname.endsWith("/listings")) {
      if (opts.listingsStatus) return json(opts.listingsStatus, { error: "Plan upgrade required" });
      return json(200, { data: listings, pagination: { hasMore: false, nextCursor: null, count: 3 } });
    }
    return json(404, { error: "not found" });
  }) as typeof fetch;
  return { impl, calls };
}

const query: EvidenceQuery = { identity: charizard, gradingCompany: "PSA", grade: "9", condition: null, asOf: "2026-09-28" };

describe("PokeTrace adapter", () => {
  it("is disabled without an API key", () => {
    expect(new PokeTraceAdapter(null).enabled()).toBe(false);
  });

  it("maps editions and variants to PokeTrace's vocabulary", () => {
    expect(expectedVariant({ edition: "1st", variant: "holo" })).toEqual(["1st_Edition_Holofoil"]);
    expect(expectedVariant({ edition: "unlimited", variant: "holo" })[0]).toBe("Unlimited_Holofoil");
    expect(expectedVariant({ edition: null, variant: "reverse_holo" })).toEqual(["Reverse_Holofoil"]);
  });

  it("resolves the right printing and converts sold listings into evidence with reasons", async () => {
    const { impl, calls } = mockFetch();
    const obs = await new PokeTraceAdapter("pc_test", impl).fetchEvidence(query);
    expect(calls[0]).toBe("/v1/auth/info?");
    expect(calls[1]).toContain("search=Charizard");
    expect(calls[1]).toContain("card_number=4");
    expect(calls[2]).toContain("/v1/cards/pt-unl/listings");
    expect(calls[2]).toContain("grader=PSA");

    const sales = obs.filter((o) => o.kind === "completed_sale");
    expect(sales.map((o) => [o.sourceReference, o.verificationStatus])).toEqual([
      ["ebay:305000000001", "verified"],
      ["ebay:305000000002", "unverified"], // best offer
      ["ebay:305000000003", "failed"], // PokeTrace anomaly flag
    ]);
    expect(sales[0]).toMatchObject({ amountMinor: 104000, currency: "USD", observedAt: "2026-09-25", gradingCompany: "PSA", grade: "9" });
    expect(sales[2]!.verificationNotes).toContain("price_outlier");

    const guides = obs.filter((o) => o.kind === "price_guide");
    expect(guides).toHaveLength(1);
    expect(guides[0]).toMatchObject({ amountMinor: 105050, venue: "PokeTrace ebay average (PSA_9)" });
  });

  it("falls back to averages only when the plan does not include sold listings", async () => {
    const { impl } = mockFetch({ listingsStatus: 403 });
    const obs = await new PokeTraceAdapter("pc_test", impl).fetchEvidence(query);
    expect(obs.every((o) => o.kind === "price_guide")).toBe(true);
    expect(obs).toHaveLength(1);
  });

  it("reports plan and quota, and skips the paid-only listings call on a Free key", async () => {
    const { impl, calls } = mockFetch({ plan: "Free" });
    const adapter = new PokeTraceAdapter("pc_test", impl);
    expect(await adapter.planInfo()).toEqual({ plan: "Free", active: true, dailyLimit: 10000, dailyRemaining: 9990, resetsAt: "2026-09-29T00:00:00Z" });
    const obs = await adapter.fetchEvidence(query);
    expect(calls.some((c) => c.includes("/listings"))).toBe(false);
    expect(obs.every((o) => o.kind === "price_guide")).toBe(true);
  });

  it("uses a stored PokeTrace card id when the catalogue entry has one", async () => {
    const calls: string[] = [];
    const impl = (async (input: string | URL) => {
      const path = new URL(String(input)).pathname;
      if (path === "/v1/auth/info") return new Response(JSON.stringify({ data: { active: true, user: { plan: "Pro" } } }), { status: 200 });
      calls.push(path);
      const body = calls.length === 1 ? { data: cards[1] } : { data: [], pagination: { hasMore: false, nextCursor: null } };
      return new Response(JSON.stringify(body), { status: 200 });
    }) as typeof fetch;
    await new PokeTraceAdapter("pc_test", impl).fetchEvidence({ ...query, identity: { ...charizard, external_refs: { poketrace: "pt-unl" } } });
    expect(calls[0]).toBe("/v1/cards/pt-unl");
  });
});
