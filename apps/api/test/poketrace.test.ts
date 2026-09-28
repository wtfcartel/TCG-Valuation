import { describe, expect, it } from "vitest";
import { expectedVariant, gradedTier, PokeTraceAdapter, PokeTraceError } from "../src/sources/poketrace.js";
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
    variant: "Holofoil",
    game: "pokemon",
    market: "US",
    currency: "USD",
    lastUpdated: "2026-09-27T00:00:00Z",
    prices: {
      ebay: {
        PSA_9: { avg: 1050.5, low: 900, high: 1200, lastUpdated: "2026-09-27T00:00:00Z", saleCount: 14 },
        CGC_9_5: { avg: 1400, low: 1300, high: 1500, lastUpdated: "2026-09-27T00:00:00Z", saleCount: 3 },
        NEAR_MINT: { avg: 410, low: 380, high: 450, lastUpdated: "2026-09-27T00:00:00Z", saleCount: 40 },
      },
      tcgplayer: { NEAR_MINT: { avg: 400, low: 350, high: 450, lastUpdated: "2026-09-27T00:00:00Z" } },
    },
  },
];

const listings = [
  { id: 1, sourceItemId: "305000000001", listingType: "Auction", title: "Charizard PSA 9", price: 1040, currency: "USD", listingUrl: "https://www.ebay.com/itm/305000000001", condition: null, grader: "PSA", grade: "9", soldAt: "2026-09-25T10:00:00Z", anomalyFlag: null, anomalyReason: null },
  { id: 2, sourceItemId: "305000000002", listingType: "BestOffer", title: "Charizard PSA 9", price: 1300, currency: "USD", listingUrl: "https://www.ebay.com/itm/305000000002", condition: null, grader: "PSA", grade: "9", soldAt: "2026-09-24T10:00:00Z", anomalyFlag: null, anomalyReason: null },
  { id: 3, sourceItemId: "305000000003", listingType: "FixedPrice", title: "Charizard PSA 9 lot", price: 99, currency: "USD", listingUrl: "https://www.ebay.com/itm/305000000003", condition: null, grader: "PSA", grade: "9", soldAt: "2026-09-23T10:00:00Z", anomalyFlag: "price_outlier", anomalyReason: "90% below median" },
];

const noSleep = async () => undefined;

function mockApi(opts: { plan?: string; listingsStatus?: number; rateLimitOnce?: boolean } = {}) {
  const calls: string[] = [];
  let limited = false;
  const impl = (async (input: string | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    calls.push(`${url.pathname}?${url.searchParams.toString()}`);
    expect((init?.headers as Record<string, string>)["X-API-Key"]).toBe("pc_test");
    const headers = { "content-type": "application/json", "X-Plan": opts.plan ?? "Scale", "X-RateLimit-Remaining": "99" };
    const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers });
    if (opts.rateLimitOnce && !limited) {
      limited = true;
      return json(429, { error: "Rate limit exceeded", retryAfter: 2 });
    }
    if (url.pathname === "/v1/auth/info") {
      return json(200, { data: { key: "pc_xxx", name: null, active: true, createdAt: "2026-09-28T00:00:00Z", user: { plan: opts.plan ?? "Scale", remaining: 240, limit: 250, periodStart: "2026-09-28T00:00:00Z", resetsAt: "2026-09-29T00:00:00Z" } } });
    }
    if (url.pathname === "/v1/cards") return json(200, { data: cards, pagination: { hasMore: false, nextCursor: null, count: 2 } });
    if (url.pathname === "/v1/cards/pt-unl") return json(200, { data: cards[1] });
    if (url.pathname.endsWith("/listings")) {
      if (opts.listingsStatus) return json(opts.listingsStatus, { error: "Upgrade required", code: "UPGRADE_REQUIRED" });
      return json(200, { data: listings, pagination: { hasMore: false, nextCursor: null, count: 3 } });
    }
    return json(404, { error: "Not found" });
  }) as typeof fetch;
  return { impl, calls };
}

const graded: EvidenceQuery = { identity: charizard, gradingCompany: "PSA", grade: "9", condition: null, asOf: "2026-09-28" };
const raw: EvidenceQuery = { identity: charizard, gradingCompany: null, grade: null, condition: "NM", asOf: "2026-09-28" };

describe("PokeTrace adapter", () => {
  it("is disabled without an API key", () => {
    expect(new PokeTraceAdapter(null).enabled()).toBe(false);
  });

  it("maps editions, variants and half grades to PokeTrace's vocabulary", () => {
    expect(expectedVariant({ edition: "1st", variant: "holo" })).toEqual(["1st_Edition_Holofoil"]);
    expect(expectedVariant({ edition: "unlimited", variant: "holo" })[0]).toBe("Holofoil");
    expect(expectedVariant({ edition: null, variant: "reverse_holo" })).toEqual(["Reverse_Holofoil"]);
    expect(gradedTier("cgc", "9.5")).toBe("CGC_9_5");
  });

  it("reads plan and quota from /auth/info", async () => {
    const { impl } = mockApi({ plan: "Free" });
    expect(await new PokeTraceAdapter("pc_test", impl, { sleep: noSleep }).planInfo()).toEqual({
      plan: "Free",
      active: true,
      dailyLimit: 250,
      dailyRemaining: 240,
      resetsAt: "2026-09-29T00:00:00Z",
    });
  });

  it("on Scale: resolves the printing, pages at 20, and turns sold listings into evidence with reasons", async () => {
    const { impl, calls } = mockApi({ plan: "Scale" });
    const obs = await new PokeTraceAdapter("pc_test", impl, { sleep: noSleep }).fetchEvidence(graded);
    expect(calls[0]).toMatch(/^\/v1\/cards\?.*search=Charizard/);
    expect(calls[0]).toContain("card_number=4");
    expect(calls[0]).toContain("limit=20");
    expect(calls[1]).toContain("/v1/cards/pt-unl/listings");
    expect(calls[1]).toContain("grader=PSA");
    expect(calls[1]).toContain("limit=20");
    expect(calls).toHaveLength(2); // no separate plan lookup: X-Plan header is used

    const sales = obs.filter((o) => o.kind === "completed_sale");
    expect(sales.map((o) => [o.sourceReference, o.verificationStatus])).toEqual([
      ["ebay:305000000001", "verified"],
      ["ebay:305000000002", "unverified"],
      ["ebay:305000000003", "failed"],
    ]);
    expect(sales[0]).toMatchObject({ amountMinor: 104000, currency: "USD", observedAt: "2026-09-25", gradingCompany: "PSA", grade: "9" });
    expect(sales[2]!.verificationNotes).toContain("price_outlier");
    const guides = obs.filter((o) => o.kind === "price_guide");
    expect(guides.map((g) => g.venue)).toEqual(["PokeTrace ebay average (PSA_9)"]);
  });

  it("on Pro/Growth/Free: never calls the Scale-only listings endpoint", async () => {
    for (const plan of ["Free", "Pro", "Growth"]) {
      const { impl, calls } = mockApi({ plan });
      const obs = await new PokeTraceAdapter("pc_test", impl, { sleep: noSleep }).fetchEvidence(raw);
      expect(calls.some((c) => c.includes("/listings"))).toBe(false);
      expect(obs.every((o) => o.kind === "price_guide")).toBe(true);
      expect(obs.map((o) => o.venue).sort()).toEqual(["PokeTrace ebay average (NEAR_MINT)", "PokeTrace tcgplayer average (NEAR_MINT)"]);
    }
  });

  it("uses underscore half-grade tiers for price guides", async () => {
    const { impl } = mockApi({ plan: "Pro" });
    const obs = await new PokeTraceAdapter("pc_test", impl, { sleep: noSleep }).fetchEvidence({ ...graded, gradingCompany: "CGC", grade: "9.5" });
    expect(obs.map((o) => o.venue)).toEqual(["PokeTrace ebay average (CGC_9_5)"]);
  });

  it("falls back to averages if listings return 403 despite the plan header", async () => {
    const { impl } = mockApi({ plan: "Scale", listingsStatus: 403 });
    const obs = await new PokeTraceAdapter("pc_test", impl, { sleep: noSleep }).fetchEvidence(graded);
    expect(obs.every((o) => o.kind === "price_guide")).toBe(true);
  });

  it("waits and retries once on a burst 429, spacing requests on the Free plan", async () => {
    const waits: number[] = [];
    const { impl, calls } = mockApi({ plan: "Free", rateLimitOnce: true });
    const adapter = new PokeTraceAdapter("pc_test", impl, { sleep: async (ms) => void waits.push(ms) });
    await adapter.fetchEvidence(raw);
    expect(calls).toHaveLength(2); // 429, then the retried search
    expect(waits).toContain(2000);
  });

  it("surfaces an invalid key as an error", async () => {
    const impl = (async () => new Response(JSON.stringify({ error: "Invalid API key" }), { status: 401 })) as typeof fetch;
    await expect(new PokeTraceAdapter("pc_test", impl, { sleep: noSleep }).fetchEvidence(raw)).rejects.toBeInstanceOf(PokeTraceError);
  });

  it("uses a stored PokeTrace card id when the catalogue entry has one", async () => {
    const { impl, calls } = mockApi({ plan: "Pro" });
    await new PokeTraceAdapter("pc_test", impl, { sleep: noSleep }).fetchEvidence({ ...raw, identity: { ...charizard, external_refs: { poketrace: "pt-unl" } } });
    expect(calls[0]).toBe("/v1/cards/pt-unl?market=US");
  });
});
