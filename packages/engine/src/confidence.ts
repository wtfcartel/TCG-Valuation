import type {
  ConfidenceAssessment,
  ConfidenceClass,
  ConfidenceFactors,
  MethodologyParameters,
} from "./types.js";

/**
 * Transparent, rule-based confidence classification. No numeric score is produced:
 * the stored factors plus the rules below fully explain the outcome.
 */
export function classifyConfidence(
  factors: ConfidenceFactors,
  params: MethodologyParameters,
  concluded: boolean,
): ConfidenceAssessment {
  const limited: string[] = [];
  const notHigh: string[] = [];
  const threshold = params.dispersionThresholdPct;

  if (!concluded) limited.push("No adequate comparable sales were available");
  if (factors.comparableCount < params.baseSampleSize) {
    limited.push(`Fewer than ${params.baseSampleSize} comparable sales (${factors.comparableCount})`);
  }
  if (factors.secondaryMatchCount > 0) {
    limited.push(`${factors.secondaryMatchCount} secondary (non-exact) comparable(s) used without adjustment`);
  }
  if (factors.medianAgeDays != null && factors.medianAgeDays > params.confidence.moderateMaxMedianAgeDays) {
    limited.push(`Median evidence age ${factors.medianAgeDays} days exceeds ${params.confidence.moderateMaxMedianAgeDays}`);
  }
  if (factors.dispersionPct != null && factors.dispersionPct > threshold * 2) {
    limited.push(`Dispersion ${factors.dispersionPct}% exceeds twice the ${threshold}% threshold`);
  }

  if (factors.dispersionPct != null && factors.dispersionPct > threshold) {
    notHigh.push(`Dispersion ${factors.dispersionPct}% exceeds the ${threshold}% threshold`);
  }
  if (factors.medianAgeDays != null && factors.medianAgeDays > params.confidence.highMaxMedianAgeDays) {
    notHigh.push(`Median evidence age ${factors.medianAgeDays} days exceeds ${params.confidence.highMaxMedianAgeDays}`);
  }
  if (factors.liquiditySales90d < params.confidence.highMinLiquidity90d) {
    notHigh.push(
      `Thin market: ${factors.liquiditySales90d} exact-match sale(s) in the last 90 days (< ${params.confidence.highMinLiquidity90d})`,
    );
  }
  if (factors.gradingCertainty === "raw_condition_stated" || factors.gradingCertainty === "raw_condition_unknown") {
    notHigh.push("Raw-card condition is owner-assessed and not independently verified");
  }
  if (factors.gradingCertainty === "graded_uncertified") {
    notHigh.push("Graded asset has no certification number recorded");
  }

  let classification: ConfidenceClass;
  let reasons: string[];
  if (limited.length > 0) {
    classification = "limited";
    reasons = [...limited, ...notHigh];
  } else if (notHigh.length > 0) {
    classification = "moderate";
    reasons = notHigh;
  } else {
    classification = "high";
    reasons = [
      `${factors.comparableCount} exact-match comparable sales`,
      `Median evidence age ${factors.medianAgeDays} days`,
      `Dispersion ${factors.dispersionPct}% within ${threshold}% threshold`,
      `${factors.liquiditySales90d} exact-match sales in the last 90 days`,
    ];
  }
  return { classification, factors, reasons };
}
