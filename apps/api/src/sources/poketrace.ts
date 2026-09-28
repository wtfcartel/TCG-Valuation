import type { CardIdentityRow, EvidenceQuery, SourceAdapter, SourcedObservation } from "./types.js";
import { SourceNotConfiguredError } from "./types.js";

/**
 * PokeTrace (https://poketrace.com) — Pokémon prices from eBay and TCGplayer, graded PSA/BGS/CGC/SGC/TAG/ACE.
 *
 * Request/response shapes follow the MIT-licensed official SDK (github.com/PokeTrace/sdk, v1.0.0).
 * A small internal client is used instead of the SDK package so the fetch implementation can be
 * injected for tests and rate-limit errors map onto Cardcore's error handling.
 *
 * Evidence rules:
 *  - Individual eBay sold listings (`/v1/cards/:id/listings`, Pro plan) → `completed_sale`.
 *    Listings PokeTrace flags as anomalous are stored with verification `failed`, and
 *    best-offer listings as `unverified`, so the engine rejects both with their reason.
 *  - Rolling averages (`prices.<source>.<tier>`, free plan) → `price_guide` (context only, never comparables).
 *  - On a free key the listings call returns 403; the adapter then stores the averages only.
 */

type Fetch = typeof fetch;

interface PtCardSummary {
  id: string;
  name: string;
  cardNumber: string | null;
  set: { slug: string; name: string };
  variant: string;
  game: string;
  market: "US" | "EU";
  currency: string;
  prices: Record<string, Record<string, { avg: number | null; low: number | null; high: number | null; lastUpdated: string | null; saleCount?: number }>>;
  lastUpdated: string | null;
}

interface PtListing {
  id: number;
  sourceItemId: string;
  listingType: string;
  title: string;
  price: number;
  currency: string;
  listingUrl: string;
  condition: string | null;
  grader: string | null;
  grade: string | null;
  soldAt: string | null;
  anomalyFlag: string | null;
  anomalyReason: string | null;
}

export class PokeTraceError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const GRADERS = new Set(["PSA", "CGC", "BGS", "SGC", "TAG", "ACE"]);

/** Cardcore raw condition → PokeTrace condition tier names. */
const CONDITION_TIERS: Record<string, string> = {
  M: "NEAR_MINT",
  NM: "NEAR_MINT",
  LP: "LIGHTLY_PLAYED",
  MP: "MODERATELY_PLAYED",
  HP: "HEAVILY_PLAYED",
  DMG: "DAMAGED",
};

function normaliseConditionName(value: string | null): string | null {
  if (!value) return null;
  const v = value.toLowerCase();
  if (v.includes("near mint") || v === "nm" || v === "near_mint") return "NM";
  if (v.includes("lightly")) return "LP";
  if (v.includes("moderately")) return "MP";
  if (v.includes("heavily")) return "HP";
  if (v.includes("damaged")) return "DMG";
  return null;
}

/** Map a Cardcore identity to PokeTrace's variant vocabulary. */
export function expectedVariant(identity: Pick<CardIdentityRow, "edition" | "variant">): string[] {
  const first = /1st|first/i.test(identity.edition ?? "");
  const unlimited = /unlimited/i.test(identity.edition ?? "");
  const v = (identity.variant ?? "").toLowerCase();
  if (v.includes("reverse")) return ["Reverse_Holofoil"];
  if (v.includes("holo")) return first ? ["1st_Edition_Holofoil"] : unlimited ? ["Unlimited_Holofoil", "Holofoil"] : ["Holofoil", "Unlimited_Holofoil"];
  if (first) return ["1st_Edition"];
  if (unlimited) return ["Unlimited", "Normal"];
  return ["Normal", "Holofoil"];
}

function numberKey(n: string | null): string {
  return (n ?? "").split("/")[0]!.replace(/^0+(?=\d)/, "").toLowerCase();
}

export class PokeTraceAdapter implements SourceAdapter {
  readonly id = "poketrace";

  constructor(
    private readonly apiKey: string | null,
    private readonly fetchImpl: Fetch = fetch,
    private readonly baseUrl = "https://api.poketrace.com",
  ) {}

  enabled(): boolean {
    return Boolean(this.apiKey);
  }

  private async get<T>(path: string, params: Record<string, string | number | boolean | undefined> = {}): Promise<T> {
    if (!this.apiKey) throw new SourceNotConfiguredError(this.id, "POKETRACE_API_KEY is not set");
    const url = new URL(path, this.baseUrl);
    for (const [k, v] of Object.entries(params)) if (v !== undefined) url.searchParams.set(k, String(v));
    const res = await this.fetchImpl(url.toString(), { headers: { accept: "application/json", "X-API-Key": this.apiKey } });
    if (!res.ok) {
      let message = res.statusText;
      try {
        const body = (await res.json()) as { error?: string; message?: string };
        message = body.error ?? body.message ?? message;
      } catch {
        /* non-JSON error body */
      }
      throw new PokeTraceError(res.status, `PokeTrace ${res.status}: ${message}`);
    }
    return (await res.json()) as T;
  }

  /** Find the PokeTrace card matching the identity (name + number + variant + language). */
  async resolveCard(identity: CardIdentityRow): Promise<PtCardSummary> {
    if (identity.external_refs?.poketrace) {
      return (await this.get<{ data: PtCardSummary }>(`/v1/cards/${encodeURIComponent(identity.external_refs.poketrace)}`, { market: "US" })).data;
    }
    const game = identity.language === "ja" ? "pokemon-japanese" : "pokemon";
    const { data } = await this.get<{ data: PtCardSummary[] }>("/v1/cards", {
      search: identity.card_name,
      card_number: identity.card_number ? identity.card_number.split("/")[0] : undefined,
      game,
      market: "US",
      limit: 50,
    });
    const byNumber = data.filter((c) => !identity.card_number || numberKey(c.cardNumber) === numberKey(identity.card_number));
    const variants = expectedVariant(identity);
    for (const v of variants) {
      const hits = byNumber.filter((c) => c.variant === v);
      if (hits.length === 1) return hits[0]!;
      const inSet = hits.filter((c) => c.set.name.toLowerCase() === identity.set_name.toLowerCase());
      if (inSet.length === 1) return inSet[0]!;
    }
    if (byNumber.length === 1) return byNumber[0]!;
    throw new SourceNotConfiguredError(
      this.id,
      byNumber.length === 0
        ? `no PokeTrace card matches ${identity.card_name} ${identity.card_number ?? ""}`
        : `${byNumber.length} PokeTrace cards match ${identity.card_name} ${identity.card_number ?? ""}; ` +
            `set external_refs.poketrace on the catalogue entry to one of: ${byNumber.map((c) => `${c.id} (${c.set.name}, ${c.variant})`).join("; ")}`,
    );
  }

  async fetchEvidence(q: EvidenceQuery): Promise<SourcedObservation[]> {
    if (q.identity.game !== "pokemon") return [];
    const card = await this.resolveCard(q.identity);
    const out: SourcedObservation[] = [];
    const grader = q.gradingCompany && GRADERS.has(q.gradingCompany.toUpperCase()) ? q.gradingCompany.toUpperCase() : null;

    // 1. Individual sold listings (Pro plan). A free key gets 403 → averages only.
    try {
      let cursor: string | undefined;
      for (let page = 0; page < 3; page += 1) {
        const res = await this.get<{ data: PtListing[]; pagination: { hasMore: boolean; nextCursor: string | null } }>(
          `/v1/cards/${encodeURIComponent(card.id)}/listings`,
          { grader: grader ?? undefined, grade: grader ? (q.grade ?? undefined) : undefined, sort: "sold_at_desc", limit: 100, cursor },
        );
        for (const l of res.data) {
          if (!l.soldAt) continue;
          // Without a grader filter the API returns graded and raw listings; keep raw only for a raw subject.
          if (!grader && l.grader) continue;
          const bestOffer = /best.?offer/i.test(l.listingType);
          out.push({
            sourceReference: `ebay:${l.sourceItemId}`,
            sourceUrl: l.listingUrl,
            kind: "completed_sale",
            gradingCompany: l.grader ? l.grader.toUpperCase() : null,
            grade: l.grade,
            condition: l.grader ? null : normaliseConditionName(l.condition),
            observedAt: l.soldAt.slice(0, 10),
            venue: `eBay via PokeTrace (${l.listingType})`,
            amountMinor: Math.round(l.price * 100),
            currency: l.currency,
            buyersPremiumMinor: 0,
            armsLength: true,
            verificationStatus: l.anomalyFlag ? "failed" : bestOffer ? "unverified" : "verified",
            verificationNotes: l.anomalyFlag
              ? `Flagged anomalous by PokeTrace: ${l.anomalyFlag}${l.anomalyReason ? ` — ${l.anomalyReason}` : ""}`
              : bestOffer
                ? "Best-offer listing: accepted price may differ from the price shown"
                : "Completed eBay sale reported by PokeTrace",
            raw: { poketraceCardId: card.id, listing: l },
          });
        }
        if (!res.pagination?.hasMore || !res.pagination.nextCursor) break;
        cursor = res.pagination.nextCursor;
      }
    } catch (error) {
      if (!(error instanceof PokeTraceError && (error.status === 403 || error.status === 402))) throw error;
    }

    // 2. Rolling averages for the subject's tier — price guides (context only).
    const tiers = grader
      ? [`${grader}_${q.grade}`, `${grader}_${(q.grade ?? "").replace(".", "_")}`]
      : [CONDITION_TIERS[(q.condition ?? "NM").toUpperCase()] ?? "NEAR_MINT"];
    for (const [source, byTier] of Object.entries(card.prices ?? {})) {
      const tier = tiers.find((t) => byTier[t]);
      const p = tier ? byTier[tier] : undefined;
      if (!tier || !p || p.avg == null) continue;
      const date = (p.lastUpdated ?? card.lastUpdated ?? q.asOf).slice(0, 10);
      out.push({
        sourceReference: `poketrace:${card.id}:${source}:${tier}:${date}`,
        sourceUrl: null,
        kind: "price_guide",
        gradingCompany: grader,
        grade: grader ? q.grade : null,
        condition: grader ? null : q.condition,
        observedAt: date,
        venue: `PokeTrace ${source} average (${tier})`,
        amountMinor: Math.round(p.avg * 100),
        currency: card.currency,
        buyersPremiumMinor: 0,
        armsLength: null,
        verificationStatus: "unverified",
        verificationNotes: `Aggregate price guide${p.saleCount != null ? ` over ${p.saleCount} sale(s)` : ""} — not transaction evidence`,
        raw: { poketraceCardId: card.id, source, tier, price: p },
      });
    }
    return out;
  }
}
