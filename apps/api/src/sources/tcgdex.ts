import type { CatalogCandidate, SourceAdapter, SourcedObservation } from "./types.js";
import { SourceNotConfiguredError } from "./types.js";

type Fetch = typeof fetch;

interface TcgdexCardBrief {
  id: string;
  localId: string;
  name: string;
  image?: string;
}

interface TcgdexCard extends TcgdexCardBrief {
  rarity?: string;
  set: { id: string; name: string; cardCount?: { official?: number } };
  variants?: Record<string, boolean>;
  updated?: string;
  pricing?: {
    cardmarket?: { updated?: string; unit?: string; avg?: number; trend?: number; low?: number } | null;
    tcgplayer?: { updated?: string; unit?: string; [variant: string]: unknown } | null;
  };
}

/**
 * TCGdex — open, multilingual Pokémon catalogue (https://tcgdex.dev). The card database is
 * MIT-licensed; artwork and trademarks are not. Pricing embedded in TCGdex responses is an
 * aggregate price guide and is stored as `price_guide`, which the engine never uses as evidence.
 */
export class TcgdexAdapter implements SourceAdapter {
  readonly id = "tcgdex";
  constructor(
    private readonly isEnabled: boolean,
    private readonly fetchImpl: Fetch = fetch,
    private readonly baseUrl = "https://api.tcgdex.net/v2",
  ) {}

  enabled(): boolean {
    return this.isEnabled;
  }

  private async get<T>(path: string): Promise<T> {
    if (!this.isEnabled) throw new SourceNotConfiguredError(this.id, "disabled by configuration");
    const res = await this.fetchImpl(`${this.baseUrl}${path}`, { headers: { accept: "application/json" } });
    if (!res.ok) throw new Error(`TCGdex responded ${res.status} for ${path}`);
    return (await res.json()) as T;
  }

  async searchCatalog(query: string, language: string): Promise<CatalogCandidate[]> {
    const lang = encodeURIComponent(language || "en");
    const briefs = await this.get<TcgdexCardBrief[]>(`/${lang}/cards?name=${encodeURIComponent(query)}&pagination:itemsPerPage=25`);
    return briefs.slice(0, 25).map((b) => {
      const setCode = b.id.includes("-") ? b.id.slice(0, b.id.lastIndexOf("-")) : b.id;
      return {
        source: this.id,
        externalId: b.id,
        game: "pokemon",
        productType: "single",
        category: "card",
        setCode,
        setName: setCode,
        cardNumber: b.localId,
        cardName: b.name,
        language: language || "en",
        rarity: null,
        variants: [],
        imageUrl: b.image ? `${b.image}/low.webp` : null,
      };
    });
  }

  async getCatalogItem(externalId: string, language: string) {
    const lang = encodeURIComponent(language || "en");
    const card = await this.get<TcgdexCard>(`/${lang}/cards/${encodeURIComponent(externalId)}`);
    const official = card.set.cardCount?.official;
    const candidate: CatalogCandidate = {
      source: this.id,
      externalId: card.id,
      game: "pokemon",
      productType: "single",
      category: "card",
      setCode: card.set.id,
      setName: card.set.name,
      cardNumber: official ? `${card.localId}/${official}` : card.localId,
      cardName: card.name,
      language: language || "en",
      rarity: card.rarity ?? null,
      variants: Object.entries(card.variants ?? {})
        .filter(([, has]) => has)
        .map(([name]) => name),
      imageUrl: card.image ? `${card.image}/high.webp` : null,
    };
    const priceGuide: SourcedObservation[] = [];
    const cm = card.pricing?.cardmarket;
    const today = new Date().toISOString().slice(0, 10);
    if (cm && typeof cm.trend === "number") {
      priceGuide.push({
        sourceReference: `tcgdex:${card.id}:cardmarket-trend:${(cm.updated ?? today).slice(0, 10)}`,
        sourceUrl: `https://api.tcgdex.net/v2/${lang}/cards/${card.id}`,
        kind: "price_guide",
        gradingCompany: null,
        grade: null,
        condition: null,
        observedAt: (cm.updated ?? today).slice(0, 10),
        venue: "Cardmarket trend (via TCGdex)",
        amountMinor: Math.round(cm.trend * 100),
        currency: cm.unit ?? "EUR",
        buyersPremiumMinor: 0,
        armsLength: null,
        verificationStatus: "unverified",
        verificationNotes: "Aggregate price guide — not transaction evidence",
        raw: cm,
      });
    }
    return { candidate, priceGuide };
  }
}
