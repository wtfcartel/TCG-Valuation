import { createHash } from "node:crypto";
import { addDays } from "@cardcore/engine";
import type { EvidenceQuery, SourceAdapter, SourcedObservation } from "./types.js";

/** Deterministic PRNG seeded from the identity so demo evidence is stable across imports. */
function prng(seed: string): () => number {
  let state = createHash("sha256").update(seed).digest().readUInt32LE(0) || 1;
  return () => {
    state ^= state << 13;
    state ^= state >>> 17;
    state ^= state << 5;
    return ((state >>> 0) % 1_000_000) / 1_000_000;
  };
}

/**
 * Synthetic evidence for development only. It deliberately includes noise the engine must
 * handle: an asking price, an unverified sale, a non-arm's-length sale, a EUR-denominated
 * sale, and one outlier.
 */
export class DemoAdapter implements SourceAdapter {
  readonly id = "demo";
  constructor(private readonly isEnabled: boolean) {}

  enabled(): boolean {
    return this.isEnabled;
  }

  async fetchEvidence(q: EvidenceQuery): Promise<SourcedObservation[]> {
    const key = [q.identity.id, q.gradingCompany ?? "raw", q.grade ?? q.condition ?? ""].join("|");
    const rand = prng(key);
    const tag = createHash("sha256").update(key).digest("hex").slice(0, 10);
    const gradeFactor = q.grade ? Math.max(0.3, Number.parseFloat(q.grade) / 9) ** 3 : 1;
    const base = Math.round((10_000 + rand() * 190_000) * gradeFactor);
    const out: SourcedObservation[] = [];
    const venues = ["eBay", "Goldin", "Heritage Auctions", "Cardmarket", "Fanatics Collect"];
    for (let i = 0; i < 9; i += 1) {
      const daysAgo = 4 + i * 17 + Math.floor(rand() * 10);
      let amount = Math.round(base * (0.9 + rand() * 0.2));
      if (i === 5) amount = Math.round(base * 1.6); // outlier
      const isEur = i === 2;
      out.push({
        sourceReference: `demo-${tag}-${i}`,
        sourceUrl: `https://example.invalid/demo-sale/${tag}/${i}`,
        kind: "completed_sale",
        gradingCompany: q.gradingCompany,
        grade: q.grade,
        condition: q.condition,
        observedAt: addDays(q.asOf, -daysAgo),
        venue: venues[i % venues.length]!,
        amountMinor: isEur ? Math.round(amount / 1.1) : amount,
        currency: isEur ? "EUR" : "USD",
        buyersPremiumMinor: i % 2 === 1 ? Math.round(amount * 0.2) : 0,
        armsLength: i === 7 ? false : true,
        verificationStatus: i === 8 ? "unverified" : "verified",
        verificationNotes: "Synthetic demo record",
        raw: { synthetic: true, index: i },
      });
    }
    out.push({
      sourceReference: `demo-${tag}-ask`,
      sourceUrl: `https://example.invalid/demo-listing/${tag}`,
      kind: "asking_price",
      gradingCompany: q.gradingCompany,
      grade: q.grade,
      condition: q.condition,
      observedAt: addDays(q.asOf, -1),
      venue: "eBay (Buy It Now listing)",
      amountMinor: Math.round(base * 1.45),
      currency: "USD",
      buyersPremiumMinor: 0,
      armsLength: null,
      verificationStatus: "unverified",
      verificationNotes: "Asking price — not a completed sale",
      raw: { synthetic: true, listing: true },
    });
    return out;
  }
}
