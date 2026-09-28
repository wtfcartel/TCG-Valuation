import { describe as suite, expect, it } from "vitest";
import {
  CSM_1_0_0_PARAMETERS,
  CSM_1_1_0_PARAMETERS,
  CSM_VERSION,
  describe,
  valuate,
  type AssetDescriptor,
  type FxLookup,
  type Observation,
  type ValuationInput,
} from "../src/index.js";

const subject: AssetDescriptor & { certNumber: string } = {
  game: "pokemon",
  productType: "single",
  setCode: "base1",
  cardNumber: "4/102",
  language: "en",
  edition: "unlimited",
  variant: "holo",
  gradingCompany: "PSA",
  grade: "9",
  condition: null,
  certNumber: "12345678",
};

let seq = 0;
function sale(amount: number, observedAt: string, overrides: Partial<Observation> = {}): Observation {
  seq += 1;
  return {
    id: `obs-${String(seq).padStart(3, "0")}`,
    sourceId: "test",
    sourceReference: `ref-${seq}`,
    sourceUrl: `https://example.test/${seq}`,
    kind: "completed_sale",
    descriptor: { ...subject },
    observedAt,
    venue: "Test Auctions",
    amountMinor: amount,
    currency: "USD",
    buyersPremiumMinor: 0,
    armsLength: true,
    verificationStatus: "verified",
    ...overrides,
  };
}

const noFx: FxLookup = () => null;

function input(observations: Observation[], overrides: Partial<ValuationInput> = {}): ValuationInput {
  return {
    subject,
    purpose: "market",
    valuationDate: "2026-09-01",
    baseCurrency: "USD",
    quantity: 1,
    methodologyVersion: CSM_VERSION,
    parameters: CSM_1_0_0_PARAMETERS,
    observations,
    exclusions: [],
    fx: noFx,
    ...overrides,
  };
}

suite("statistics", () => {
  it("computes mean, median, range and dispersion", () => {
    const s = describe([100_00, 110_00, 120_00]);
    expect(s.meanMinor).toBe(110_00);
    expect(s.medianMinor).toBe(110_00);
    expect(s.rangeMinor).toBe(20_00);
    expect(s.dispersionPct).toBe(18.18);
  });
});

suite("comparable sales method", () => {
  it("uses the three most recent verified arm's-length exact sales", () => {
    const r = valuate(
      input([
        sale(100_00, "2026-08-20"),
        sale(105_00, "2026-08-10"),
        sale(110_00, "2026-08-01"),
        sale(500_00, "2026-07-01"),
      ]),
    );
    expect(r.status).toBe("concluded");
    expect(r.methodUsed).toBe("exact_recent");
    expect(r.unitValueMinor).toBe(105_00);
    expect(r.statistics?.medianMinor).toBe(105_00);
    expect(r.comparables.filter((c) => c.included)).toHaveLength(3);
    const older = r.comparables.find((c) => c.amountMinor === 500_00);
    expect(older?.rejection?.code).toBe("NOT_SELECTED_OLDER");
  });

  it("never treats asking prices or price guides as evidence", () => {
    const r = valuate(
      input([
        sale(100_00, "2026-08-20"),
        sale(999_00, "2026-08-25", { kind: "asking_price" }),
        sale(999_00, "2026-08-26", { kind: "price_guide" }),
      ]),
    );
    expect(r.statistics?.count).toBe(1);
    expect(r.comparables.filter((c) => c.rejection?.code === "NOT_COMPLETED_SALE")).toHaveLength(2);
    expect(r.confidence.classification).toBe("limited");
  });

  it("rejects unverified, non-arm's-length and mismatched evidence with reasons", () => {
    const r = valuate(
      input([
        sale(100_00, "2026-08-20", { verificationStatus: "unverified" }),
        sale(100_00, "2026-08-20", { armsLength: false }),
        sale(100_00, "2026-08-20", { descriptor: { ...subject, language: "ja" } }),
        sale(100_00, "2026-08-20", { descriptor: { ...subject, edition: "1st" } }),
      ]),
    );
    expect(r.status).toBe("insufficient_evidence");
    expect(r.unitValueMinor).toBeNull();
    expect(r.comparables.map((c) => c.rejection?.code).sort()).toEqual([
      "IDENTITY_MISMATCH",
      "IDENTITY_MISMATCH",
      "NOT_ARMS_LENGTH",
      "UNVERIFIED",
    ]);
  });

  it("escalates to an expanded set when dispersion exceeds the threshold and flags outliers", () => {
    const r = valuate(
      input([
        sale(100_00, "2026-08-25"),
        sale(160_00, "2026-08-20"),
        sale(105_00, "2026-08-15"),
        sale(98_00, "2026-08-10"),
        sale(102_00, "2026-08-05"),
        sale(101_00, "2026-07-30"),
      ]),
    );
    expect(r.escalated).toBe(true);
    expect(r.baseStatistics?.count).toBe(3);
    expect(r.statistics?.count).toBe(6);
    expect(r.methodUsed).toBe("exact_expanded");
    expect(r.flags.map((f) => f.code)).toContain("DISPERSION_EXCEEDED");
    expect(r.flags.map((f) => f.code)).toContain("SUSPECTED_OUTLIERS");
    const outlier = r.comparables.find((c) => c.amountMinor === 160_00)!;
    expect(outlier.suspectedOutlier).toBe(true);
    expect(outlier.included).toBe(true); // flagged, not silently removed
  });

  it("requires a documented reason to exclude a sale and then recalculates", () => {
    const obs = [
      sale(100_00, "2026-08-25"),
      sale(160_00, "2026-08-20"),
      sale(105_00, "2026-08-15"),
      sale(98_00, "2026-08-10"),
    ];
    expect(() => valuate(input(obs, { exclusions: [{ observationId: obs[1]!.id, reason: "", excludedBy: "u1" }] }))).toThrow(
      /documented reason/,
    );
    const r = valuate(
      input(obs, {
        exclusions: [{ observationId: obs[1]!.id, reason: "Listing shows card was damaged in photos", excludedBy: "u1" }],
      }),
    );
    expect(r.escalated).toBe(false);
    expect(r.unitValueMinor).toBe(Math.round((100_00 + 105_00 + 98_00) / 3));
    const excluded = r.comparables.find((c) => c.observationId === obs[1]!.id)!;
    expect(excluded.rejection).toMatchObject({ code: "MANUAL_EXCLUSION", excludedBy: "u1" });
  });

  it("widens the window, then uses secondary comparables, and flags lower confidence", () => {
    const widened = valuate(
      input([sale(100_00, "2026-08-20"), sale(100_00, "2026-03-01"), sale(100_00, "2026-02-01")]),
    );
    expect(widened.methodUsed).toBe("widened_window");
    expect(widened.windowDays).toBe(365);
    expect(widened.lowerConfidence).toBe(true);

    const secondary = valuate(
      input([
        sale(100_00, "2026-08-20"),
        sale(80_00, "2026-08-18", { descriptor: { ...subject, grade: "8" } }),
        sale(120_00, "2026-08-18", { descriptor: { ...subject, gradingCompany: "CGC" } }),
      ]),
    );
    expect(secondary.methodUsed).toBe("secondary_comparables");
    expect(secondary.confidence.classification).toBe("limited");
    expect(secondary.flags.map((f) => f.code)).toContain("SECONDARY_COMPARABLES_USED");
  });

  it("converts foreign-currency evidence with the documented FX rate and rejects when none exists", () => {
    const fx: FxLookup = (from, to, onDate) =>
      from === "EUR" && to === "USD" ? { rate: 1.1, rateId: "fx-1", rateDate: onDate, source: "ECB" } : null;
    const r = valuate(
      input([sale(100_00, "2026-08-20", { currency: "EUR" }), sale(100_00, "2026-08-19", { currency: "JPY" })], { fx }),
    );
    const eur = r.comparables.find((c) => c.currency === "EUR")!;
    expect(eur.basisAmountBaseMinor).toBe(110_00);
    expect(eur.fx?.source).toBe("ECB");
    expect(r.comparables.find((c) => c.currency === "JPY")?.rejection?.code).toBe("NO_FX_RATE");
  });

  it("calculates insurance replacement value separately from market value", () => {
    const obs = [
      sale(100_00, "2026-08-20", { buyersPremiumMinor: 20_00 }),
      sale(100_00, "2026-08-10", { buyersPremiumMinor: 20_00 }),
      sale(100_00, "2026-08-01", { buyersPremiumMinor: 20_00 }),
    ];
    const market = valuate(input(obs));
    const replacement = valuate(input(obs, { purpose: "insurance_replacement" }));
    expect(market.unitValueMinor).toBe(100_00);
    expect(replacement.unitValueMinor).toBe(126_00); // (100 + 20) × 1.05
  });

  it("historical valuation ignores evidence that did not exist at the valuation date", () => {
    const obs = [sale(200_00, "2026-08-20"), sale(100_00, "2026-01-20"), sale(100_00, "2026-01-10"), sale(100_00, "2026-01-05")];
    const r = valuate(input(obs, { purpose: "historical", valuationDate: "2026-02-01" }));
    expect(r.unitValueMinor).toBe(100_00);
    expect(r.comparables.find((c) => c.amountMinor === 200_00)?.rejection?.code).toBe("AFTER_VALUATION_DATE");
  });

  it("classifies high evidence only for recent, liquid, tight, exact, certified evidence", () => {
    const r = valuate(input([sale(100_00, "2026-08-25"), sale(102_00, "2026-08-20"), sale(104_00, "2026-08-15")]));
    expect(r.confidence.classification).toBe("high");
    const raw = valuate(
      input([sale(100_00, "2026-08-25"), sale(102_00, "2026-08-20"), sale(104_00, "2026-08-15")].map((o) => ({
        ...o,
        descriptor: { ...o.descriptor, gradingCompany: null, grade: null, condition: "NM" },
      })), { subject: { ...subject, gradingCompany: null, grade: null, condition: "NM", certNumber: null } }),
    );
    expect(raw.confidence.classification).toBe("moderate");
    expect(raw.confidence.reasons.join(" ")).toMatch(/owner-assessed/);
  });

  it("uses one copy of a transaction reported by several sources, preferring the better source", () => {
    const a = sale(100_00, "2026-08-25", { transactionKey: "ebay:1", sourceId: "scrape", sourcePriority: 3 });
    const b = sale(100_00, "2026-08-25", { transactionKey: "ebay:1", sourceId: "licensed", sourcePriority: 0 });
    const obs = [a, b, sale(102_00, "2026-08-20"), sale(104_00, "2026-08-15")];
    // CSM-1.0.0 had no de-duplication: reproducing an old valuation must not change it.
    expect(valuate(input(obs)).statistics?.count).toBe(3);
    expect(valuate(input(obs)).comparables.some((c) => c.rejection?.code === "DUPLICATE_TRANSACTION")).toBe(false);
    const r = valuate(input(obs, { parameters: CSM_1_1_0_PARAMETERS }));
    expect(r.statistics?.count).toBe(3);
    const dup = r.comparables.find((c) => c.observationId === a.id)!;
    expect(dup.rejection?.code).toBe("DUPLICATE_TRANSACTION");
    expect(r.comparables.find((c) => c.observationId === b.id)?.included).toBe(true);
  });

  it("is deterministic (same inputs → same hash)", () => {
    const obs = [sale(100_00, "2026-08-25"), sale(102_00, "2026-08-20"), sale(104_00, "2026-08-15")];
    expect(valuate(input(obs)).inputsHash).toBe(valuate(input([...obs].reverse())).inputsHash);
  });
});
