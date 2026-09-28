import type { MethodologyParameters } from "./types.js";

export const CSM_VERSION = "CSM-1.1.0";

/**
 * Cardcore Comparable Sales Method v1.0.0 — default parameters.
 * The narrative methodology lives in docs/methodology/CSM-1.0.0.md; any change to these
 * values requires a new methodology version so historical valuations remain reproducible.
 */
export const CSM_1_0_0_PARAMETERS: MethodologyParameters = {
  baseSampleSize: 3,
  dispersionThresholdPct: 22.5,
  expandedSampleMin: 5,
  expandedSampleMax: 10,
  initialWindowDays: 90,
  widenedWindowDays: [180, 365, 730],
  outlierDeviationPct: 35,
  replacementLoadingPct: 5,
  fxRateBasis: "valuation_date",
  fxMaxStalenessDays: 7,
  secondaryMaxGradeSteps: 1,
  confidence: {
    highMaxMedianAgeDays: 90,
    highMinLiquidity90d: 3,
    moderateMaxMedianAgeDays: 365,
  },
};

/**
 * CSM-1.1.0 (effective 2026-09-28): identical to 1.0.0 except that a transaction evidenced by
 * several sources (e.g. the same eBay sale via a data vendor and a saved page) is used once.
 */
export const CSM_1_1_0_PARAMETERS: MethodologyParameters = {
  ...CSM_1_0_0_PARAMETERS,
  deduplicateTransactions: true,
};

export const METHODOLOGY_VERSIONS = [
  { id: "CSM-1.0.0", effectiveFrom: "2026-09-26", parameters: CSM_1_0_0_PARAMETERS, documentRef: "docs/methodology/CSM-1.0.0.md" },
  { id: "CSM-1.1.0", effectiveFrom: "2026-09-28", parameters: CSM_1_1_0_PARAMETERS, documentRef: "docs/methodology/CSM-1.1.0.md" },
] as const;

export function validateParameters(p: MethodologyParameters): string[] {
  const errors: string[] = [];
  if (!Number.isInteger(p.baseSampleSize) || p.baseSampleSize < 1) errors.push("baseSampleSize must be a positive integer");
  if (!(p.dispersionThresholdPct > 0)) errors.push("dispersionThresholdPct must be positive");
  if (p.expandedSampleMin < p.baseSampleSize) errors.push("expandedSampleMin must be ≥ baseSampleSize");
  if (p.expandedSampleMax < p.expandedSampleMin) errors.push("expandedSampleMax must be ≥ expandedSampleMin");
  const windows = [p.initialWindowDays, ...p.widenedWindowDays];
  if (windows.some((w, i) => i > 0 && w <= windows[i - 1]!)) errors.push("evidence windows must be strictly increasing");
  if (p.replacementLoadingPct < 0) errors.push("replacementLoadingPct must be ≥ 0");
  return errors;
}
