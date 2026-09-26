export interface CardIdentityRow {
  id: string;
  game: string;
  product_type: "single" | "sealed";
  category: string;
  set_code: string;
  set_name: string;
  card_number: string | null;
  card_name: string;
  language: string;
  edition: string | null;
  variant: string | null;
  rarity: string | null;
  external_refs: Record<string, string>;
}

export interface EvidenceQuery {
  identity: CardIdentityRow;
  gradingCompany: string | null;
  grade: string | null;
  condition: string | null;
  asOf: string;
}

/** Evidence exactly as returned by a source, before it is written to price_observations. */
export interface SourcedObservation {
  sourceReference: string;
  sourceUrl: string | null;
  kind: "completed_sale" | "asking_price" | "price_guide";
  gradingCompany: string | null;
  grade: string | null;
  condition: string | null;
  observedAt: string;
  venue: string | null;
  amountMinor: number;
  currency: string;
  buyersPremiumMinor: number;
  armsLength: boolean | null;
  verificationStatus: "verified" | "unverified" | "failed";
  verificationNotes: string | null;
  raw: unknown;
}

export interface CatalogCandidate {
  source: string;
  externalId: string;
  game: string;
  productType: "single" | "sealed";
  category: string;
  setCode: string;
  setName: string;
  cardNumber: string | null;
  cardName: string;
  language: string;
  rarity: string | null;
  variants: string[];
  imageUrl: string | null;
}

/** Every pricing/catalogue integration implements this. Nothing else in Cardcore depends on a vendor. */
export interface SourceAdapter {
  readonly id: string;
  enabled(): boolean;
  fetchEvidence?(query: EvidenceQuery): Promise<SourcedObservation[]>;
  searchCatalog?(query: string, language: string): Promise<CatalogCandidate[]>;
  getCatalogItem?(externalId: string, language: string): Promise<{ candidate: CatalogCandidate; priceGuide: SourcedObservation[] }>;
}

export class SourceNotConfiguredError extends Error {
  constructor(sourceId: string, reason: string) {
    super(`Source '${sourceId}' is not available: ${reason}`);
  }
}
