/**
 * Core types for the Cardcore valuation engine.
 *
 * All money is represented as integer minor units (e.g. cents) together with an
 * ISO-4217 currency code. The engine never uses floating point for stored money;
 * floats appear only transiently in FX conversion and are rounded half-away-from-zero.
 */

export type ISODate = string; // YYYY-MM-DD

export type ValuationPurpose = "market" | "insurance_replacement" | "historical";

export type ObservationKind = "completed_sale" | "asking_price" | "price_guide";

export type VerificationStatus = "verified" | "unverified" | "failed";

/** The attributes that define "the same asset" for comparable matching. */
export interface AssetDescriptor {
  game: string;
  productType: "single" | "sealed";
  setCode: string;
  cardNumber: string | null;
  language: string;
  edition: string | null;
  variant: string | null;
  /** null = raw / ungraded */
  gradingCompany: string | null;
  grade: string | null;
  /** Raw-card condition (e.g. NM, LP) or "sealed". Ignored for graded items. */
  condition: string | null;
}

/** A single piece of externally sourced market data, as stored in the market-data layer. */
export interface Observation {
  id: string;
  sourceId: string;
  sourceReference: string;
  sourceUrl: string | null;
  kind: ObservationKind;
  descriptor: AssetDescriptor;
  /** Date the transaction completed (or the quote was observed). */
  observedAt: ISODate;
  venue: string | null;
  amountMinor: number;
  currency: string;
  buyersPremiumMinor: number;
  armsLength: boolean | null;
  verificationStatus: VerificationStatus;
}

export interface FxQuote {
  rate: number;
  rateId: string | null;
  rateDate: ISODate;
  source: string;
}

/** Returns the rate to convert 1 unit of `from` into `to`, as available on `onDate` (no look-ahead). */
export type FxLookup = (from: string, to: string, onDate: ISODate) => FxQuote | null;

export interface Exclusion {
  observationId: string;
  reason: string;
  excludedBy: string;
}

export interface MethodologyParameters {
  /** Default comparable sample size. */
  baseSampleSize: number;
  /** Dispersion (range / mean, %) above which the comparable set is escalated. */
  dispersionThresholdPct: number;
  expandedSampleMin: number;
  expandedSampleMax: number;
  /** Initial evidence window (days before valuation date). */
  initialWindowDays: number;
  /** Progressive widening steps (days) when fewer than baseSampleSize comparables exist. */
  widenedWindowDays: number[];
  /** A comparable deviating from the median by more than this % is flagged as a suspected outlier. */
  outlierDeviationPct: number;
  /** Replacement-cost loading applied on top of gross buyer cost, for insurance/replacement purpose. */
  replacementLoadingPct: number;
  /** Which date's FX rate is used to translate evidence into the base currency. */
  fxRateBasis: "valuation_date" | "sale_date";
  /** Max days an FX rate may pre-date the lookup date. */
  fxMaxStalenessDays: number;
  /** Maximum grade steps between subject and a secondary comparable. */
  secondaryMaxGradeSteps: number;
  confidence: {
    highMaxMedianAgeDays: number;
    highMinLiquidity90d: number;
    moderateMaxMedianAgeDays: number;
  };
}

export type MatchTier = "exact" | "secondary";

export type RejectionCode =
  | "NOT_COMPLETED_SALE"
  | "AFTER_VALUATION_DATE"
  | "VERIFICATION_FAILED"
  | "UNVERIFIED"
  | "NOT_ARMS_LENGTH"
  | "ARMS_LENGTH_UNKNOWN"
  | "IDENTITY_MISMATCH"
  | "NO_FX_RATE"
  | "OUTSIDE_WINDOW"
  | "NOT_SELECTED_OLDER"
  | "MANUAL_EXCLUSION";

export interface ComparableRecord {
  observationId: string;
  sourceId: string;
  sourceReference: string;
  sourceUrl: string | null;
  venue: string | null;
  observedAt: ISODate;
  ageDays: number;
  amountMinor: number;
  currency: string;
  buyersPremiumMinor: number;
  matchTier: MatchTier | null;
  /** Attributes on which the comparable differs from the subject (secondary comparables). */
  differences: string[];
  fx: FxQuote | null;
  /** Evidence amount in base currency on the purpose's basis (net for market, gross for replacement). */
  basisAmountBaseMinor: number | null;
  included: boolean;
  suspectedOutlier: boolean;
  deviationFromMedianPct: number | null;
  rejection: { code: RejectionCode; detail: string; excludedBy?: string } | null;
}

export interface Statistics {
  count: number;
  meanMinor: number;
  medianMinor: number;
  minMinor: number;
  maxMinor: number;
  rangeMinor: number;
  /** range / mean × 100 */
  dispersionPct: number;
  /** population standard deviation / mean × 100 — reported for information only */
  coefficientOfVariationPct: number;
}

export type MethodUsed =
  | "exact_recent"
  | "exact_expanded"
  | "widened_window"
  | "secondary_comparables"
  | "insufficient_evidence";

export type ConfidenceClass = "high" | "moderate" | "limited";

export interface ConfidenceFactors {
  comparableCount: number;
  exactMatchCount: number;
  secondaryMatchCount: number;
  medianAgeDays: number | null;
  newestAgeDays: number | null;
  dispersionPct: number | null;
  /** Count of eligible exact-match completed sales in the 90 days before the valuation date. */
  liquiditySales90d: number;
  windowDays: number | null;
  gradingCertainty: "graded_certified" | "graded_uncertified" | "raw_condition_stated" | "raw_condition_unknown" | "sealed";
}

export interface ConfidenceAssessment {
  classification: ConfidenceClass;
  factors: ConfidenceFactors;
  /** Human-readable rules that determined the classification — no opaque score. */
  reasons: string[];
}

export type FlagCode =
  | "DISPERSION_EXCEEDED"
  | "DISPERSION_PERSISTS_AFTER_ESCALATION"
  | "SUSPECTED_OUTLIERS"
  | "FEWER_THAN_BASE_SAMPLE"
  | "WIDENED_WINDOW"
  | "SECONDARY_COMPARABLES_USED"
  | "LOWER_CONFIDENCE"
  | "MANUAL_EXCLUSIONS_APPLIED"
  | "INSUFFICIENT_EVIDENCE";

export interface Flag {
  code: FlagCode;
  message: string;
}

export interface ValuationInput {
  subject: AssetDescriptor & { certNumber?: string | null };
  purpose: ValuationPurpose;
  /** Evidence cut-off. Only evidence dated on/before this date is eligible. */
  valuationDate: ISODate;
  baseCurrency: string;
  quantity: number;
  methodologyVersion: string;
  parameters: MethodologyParameters;
  observations: Observation[];
  exclusions: Exclusion[];
  fx: FxLookup;
}

export interface ValuationResult {
  status: "concluded" | "insufficient_evidence";
  purpose: ValuationPurpose;
  valuationDate: ISODate;
  baseCurrency: string;
  methodologyVersion: string;
  methodUsed: MethodUsed;
  escalated: boolean;
  lowerConfidence: boolean;
  windowDays: number | null;
  /** Concluded per-unit value in base currency minor units. */
  unitValueMinor: number | null;
  quantity: number;
  totalValueMinor: number | null;
  statistics: Statistics | null;
  /** Statistics on the base three-sale set before escalation, where escalation happened. */
  baseStatistics: Statistics | null;
  comparables: ComparableRecord[];
  confidence: ConfidenceAssessment;
  flags: Flag[];
  assumptions: string[];
  inputsHash: string;
}
