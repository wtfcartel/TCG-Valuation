import type { CardIdentityRow, EvidenceQuery, SourceAdapter, SourcedObservation } from "./types.js";
import { SourceNotConfiguredError } from "./types.js";

/**
 * PokeTrace (https://poketrace.com) — Pokémon prices from eBay and TCGplayer (US) and Cardmarket (EU).
 *
 * Implemented against PokeTrace's published API reference (base https://api.poketrace.com/v1,
 * X-API-Key auth) and the MIT-licensed official SDK (github.com/PokeTrace/sdk).
 *
 * Plans (daily limits, reset at midnight UTC):
 *   Free   250/day, burst 1 req/2 s  — US market, raw conditions only
 *   Pro    10k/day, burst 30/10 s    — adds graded tiers and EU Cardmarket
 *   Growth 30k/day, burst 45/10 s    — as Pro
 *   Scale  100k/day, burst 60/10 s   — adds individual eBay sold listings (and WebSocket)
 *
 * Evidence rules:
 *  - Individual eBay sold listings (`/cards/:id/listings`, Scale only) → `completed_sale`, keyed by eBay item ID.
 *    Anomaly-flagged listings → verification `failed`; best-offer listings → `unverified` (engine rejects both).
 *  - Tier averages (`prices.<source>.<tier>`) → `price_guide`: context only, never comparables.
 *  - The plan is read from the `X-Plan` response header, so no quota is spent on a separate plan lookup and the
 *    listings endpoint is only called on plans that include it (a 403 still falls back to averages).
 */

type Fetch = typeof fetch;
type Sleep = (ms: number) => Promise<void>;

interface PtTierPrice {
  avg: number | null;
  low?: number | null;
  high?: number | null;
  saleCount?: number;
  lastUpdated?: string | null;
}

interface PtCardSummary {
  id: string;
  name: string;
  cardNumber: string | null;
  set: { slug: string; name: string };
  variant?: string | null;
  game: string;
  market: "US" | "EU";
  currency: string;
  prices: Record<string, Record<string, PtTierPrice>>;
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
  anomalyFlag?: string | null;
  anomalyReason?: string | null;
}

interface PtPage<T> {
  data: T[];
  pagination?: { hasMore: boolean; nextCursor: string | null; count: number };
}

export class PokeTraceError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly code?: string,
  ) {
    super(message);
  }
}

export interface PokeTracePlanInfo {
  plan: string;
  active: boolean;
  dailyLimit: number | null;
  dailyRemaining: number | null;
  resetsAt: string | null;
}

/** Grading companies PokeTrace prices, as tier prefixes ({COMPANY}_{GRADE}). */
const GRADERS = new Set(["PSA", "CGC", "BGS", "SGC", "ACE", "TAG", "PCA", "SFG", "CGS"]);

/** Cardcore raw condition → PokeTrace raw tier. */
const CONDITION_TIERS: Record<string, string> = {
  M: "MINT",
  NM: "NEAR_MINT",
  LP: "LIGHTLY_PLAYED",
  MP: "MODERATELY_PLAYED",
  HP: "HEAVILY_PLAYED",
  DMG: "DAMAGED",
};

/** Plans that include individual sold listings. */
const LISTINGS_PLANS = new Set(["scale"]);

/** Minimum spacing between requests, by plan burst limit (with a small safety margin). */
function minIntervalMs(plan: string | null): number {
  switch ((plan ?? "free").toLowerCase()) {
    case "scale":
      return 180; // 60 / 10 s
    case "growth":
      return 240; // 45 / 10 s
    case "pro":
      return 360; // 30 / 10 s
    default:
      return 2100; // Free: 1 / 2 s
  }
}

function normaliseConditionName(value: string | null): string | null {
  if (!value) return null;
  const v = value.toLowerCase().replace(/_/g, " ");
  if (v.includes("near mint") || v === "nm") return "NM";
  if (v === "mint") return "M";
  if (v.includes("lightly")) return "LP";
  if (v.includes("moderately")) return "MP";
  if (v.includes("heavily")) return "HP";
  if (v.includes("damaged")) return "DMG";
  return null;
}

/** PokeTrace tier name for a graded subject: half grades use an underscore (9.5 → 9_5). */
export function gradedTier(grader: string, grade: string): string {
  return `${grader.toUpperCase()}_${grade.replace(".", "_")}`;
}

/** Map a Cardcore identity to PokeTrace's variant vocabulary, most likely first. */
export function expectedVariant(identity: Pick<CardIdentityRow, "edition" | "variant">): string[] {
  const first = /1st|first/i.test(identity.edition ?? "");
  const unlimited = /unlimited/i.test(identity.edition ?? "");
  const v = (identity.variant ?? "").toLowerCase();
  if (v.includes("reverse")) return ["Reverse_Holofoil"];
  if (v.includes("holo")) return first ? ["1st_Edition_Holofoil"] : unlimited ? ["Holofoil", "Unlimited"] : ["Holofoil"];
  if (first) return ["1st_Edition"];
  if (unlimited) return ["Unlimited", "Normal"];
  return ["Normal"];
}

function numberKey(n: string | null): string {
  return (n ?? "").split("/")[0]!.replace(/^0+(?=\d)/, "").toLowerCase();
}

export class PokeTraceAdapter implements SourceAdapter {
  readonly id = "poketrace";
  private readonly baseUrl: string;
  private readonly sleep: Sleep;
  private lastPlan: string | null = null;
  private lastRemaining: number | null = null;
  private lastRequestAt = 0;

  constructor(
    private readonly apiKey: string | null,
    private readonly fetchImpl: Fetch = fetch,
    opts: { baseUrl?: string; sleep?: Sleep } = {},
  ) {
    this.baseUrl = (opts.baseUrl ?? "https://api.poketrace.com/v1").replace(/\/$/, "");
    this.sleep = opts.sleep ?? ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
  }

  enabled(): boolean {
    return Boolean(this.apiKey);
  }

  /** Plan and quota most recently reported by response headers (no request made). */
  lastSeen(): { plan: string | null; remaining: number | null } {
    return { plan: this.lastPlan, remaining: this.lastRemaining };
  }

  private async get<T>(path: string, params: Record<string, string | number | boolean | undefined> = {}, attempt = 0): Promise<T> {
    if (!this.apiKey) throw new SourceNotConfiguredError(this.id, "POKETRACE_API_KEY is not set");
    const url = new URL(`${this.baseUrl}${path}`);
    for (const [k, v] of Object.entries(params)) if (v !== undefined) url.searchParams.set(k, String(v));

    const wait = this.lastRequestAt + minIntervalMs(this.lastPlan) - Date.now();
    if (this.lastRequestAt && wait > 0) await this.sleep(wait);
    this.lastRequestAt = Date.now();

    const res = await this.fetchImpl(url.toString(), { headers: { accept: "application/json", "X-API-Key": this.apiKey } });
    const plan = res.headers.get("X-Plan");
    if (plan) this.lastPlan = plan;
    const remaining = res.headers.get("X-RateLimit-Remaining");
    if (remaining != null && remaining !== "") this.lastRemaining = Number(remaining);

    if (!res.ok) {
      let body: { error?: string; message?: string; code?: string; retryAfter?: number } = {};
      try {
        body = (await res.json()) as typeof body;
      } catch {
        /* non-JSON error body */
      }
      if (res.status === 429 && attempt === 0) {
        const retryAfter = Number(body.retryAfter ?? res.headers.get("Retry-After") ?? 2);
        // Burst limit: wait once and retry. A daily-quota 429 (long retryAfter) is surfaced instead.
        if (retryAfter <= 30) {
          await this.sleep(retryAfter * 1000);
          return this.get<T>(path, params, attempt + 1);
        }
      }
      throw new PokeTraceError(res.status, `PokeTrace ${res.status}: ${body.error ?? body.message ?? res.statusText}`, body.code);
    }
    return (await res.json()) as T;
  }

  /** Plan and quota for the configured key (GET /auth/info). The key itself is never returned. */
  async planInfo(): Promise<PokeTracePlanInfo> {
    const { data } = await this.get<{
      data: {
        active: boolean;
        user: { plan: string; remaining?: number; limit?: number; resetsAt?: string; daily?: { remaining: number; limit: number; resetsAt: string } };
      };
    }>("/auth/info");
    const u = data.user;
    return {
      plan: u.plan,
      active: data.active,
      dailyLimit: u.limit ?? u.daily?.limit ?? null,
      dailyRemaining: u.remaining ?? u.daily?.remaining ?? null,
      resetsAt: u.resetsAt ?? u.daily?.resetsAt ?? null,
    };
  }

  /** Find the PokeTrace card matching the identity (name + number + variant + set, US market). */
  async resolveCard(identity: CardIdentityRow): Promise<PtCardSummary> {
    if (identity.external_refs?.poketrace) {
      const linked = (await this.get<{ data: PtCardSummary }>(`/cards/${encodeURIComponent(identity.external_refs.poketrace)}`, { market: "US" })).data;
      // Defence in depth: a stored link must still describe this card before its market data is imported.
      const sameName = linked.name.toLowerCase().includes(identity.card_name.toLowerCase().split(/\s+/)[0] ?? "");
      const sameNumber = !identity.card_number || numberKey(linked.cardNumber) === numberKey(identity.card_number);
      if (!sameName || !sameNumber) {
        throw new SourceNotConfiguredError(
          this.id,
          `linked PokeTrace card ${linked.id} (${linked.name} ${linked.cardNumber ?? ""}) does not match ${identity.card_name} ${identity.card_number ?? ""}`,
        );
      }
      return linked;
    }
    const game = identity.language === "ja" ? "pokemon-japanese" : identity.language === "zh" ? "pokemon-chinese" : "pokemon";
    const found: PtCardSummary[] = [];
    let cursor: string | undefined;
    for (let page = 0; page < 3; page += 1) {
      const res = await this.get<PtPage<PtCardSummary>>("/cards", {
        search: identity.card_name,
        card_number: identity.card_number ? identity.card_number.split("/")[0] : undefined,
        game,
        market: "US",
        limit: 20,
        cursor,
      });
      found.push(...res.data);
      if (!res.pagination?.hasMore || !res.pagination.nextCursor) break;
      cursor = res.pagination.nextCursor;
    }
    const byNumber = found.filter((c) => !identity.card_number || numberKey(c.cardNumber) === numberKey(identity.card_number));
    for (const v of expectedVariant(identity)) {
      const hits = byNumber.filter((c) => (c.variant ?? "Normal") === v);
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
            `set external_refs.poketrace on the catalogue entry to one of: ${byNumber
              .map((c) => `${c.id} (${c.set.name}, ${c.variant ?? "Normal"})`)
              .join("; ")}`,
    );
  }

  async fetchEvidence(q: EvidenceQuery): Promise<SourcedObservation[]> {
    if (q.identity.game !== "pokemon" || q.identity.product_type !== "single") return [];
    const card = await this.resolveCard(q.identity); // also learns the plan from X-Plan
    const out: SourcedObservation[] = [];
    const grader = q.gradingCompany && GRADERS.has(q.gradingCompany.toUpperCase()) ? q.gradingCompany.toUpperCase() : null;
    const plan = this.lastPlan?.toLowerCase() ?? null;

    // 1. Individual sold listings — Scale plan only.
    if (plan === null || LISTINGS_PLANS.has(plan)) {
      try {
        let cursor: string | undefined;
        for (let page = 0; page < 5; page += 1) {
          const res = await this.get<PtPage<PtListing>>(`/cards/${encodeURIComponent(card.id)}/listings`, {
            grader: grader ?? undefined,
            grade: grader ? (q.grade ?? undefined) : undefined,
            sort: "sold_at_desc",
            limit: 20,
            cursor,
          });
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
        if (!(error instanceof PokeTraceError && error.status === 403)) throw error;
      }
    }

    // 2. Tier averages for the subject — price guides (context only). Graded tiers need Pro or above.
    const tier = grader ? gradedTier(grader, q.grade ?? "") : (CONDITION_TIERS[(q.condition ?? "NM").toUpperCase()] ?? "NEAR_MINT");
    for (const [source, byTier] of Object.entries(card.prices ?? {})) {
      const p = byTier[tier];
      if (!p || p.avg == null) continue;
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
        raw: { poketraceCardId: card.id, source, tier, price: p, plan: this.lastPlan },
      });
    }
    return out;
  }
}
