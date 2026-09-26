import { classifyConfidence } from "./confidence.js";
import { canonicalJson, sha256Hex } from "./hash.js";
import { matchComparable } from "./matching.js";
import { applyPercentage, convertMinor, daysBetween } from "./money.js";
import { describe, deviationPct, median } from "./stats.js";
import type {
  ComparableRecord,
  ConfidenceFactors,
  Flag,
  FxQuote,
  MethodUsed,
  Observation,
  RejectionCode,
  Statistics,
  ValuationInput,
  ValuationResult,
} from "./types.js";

interface Candidate {
  record: ComparableRecord;
  observation: Observation;
}

function reject(record: ComparableRecord, code: RejectionCode, detail: string, excludedBy?: string): ComparableRecord {
  return { ...record, included: false, rejection: { code, detail, ...(excludedBy ? { excludedBy } : {}) } };
}

function resolveFx(input: ValuationInput, obs: Observation): FxQuote | null {
  if (obs.currency === input.baseCurrency) {
    return { rate: 1, rateId: null, rateDate: input.valuationDate, source: "identity" };
  }
  const onDate = input.parameters.fxRateBasis === "sale_date" ? obs.observedAt : input.valuationDate;
  const quote = input.fx(obs.currency, input.baseCurrency, onDate);
  if (!quote) return null;
  const staleness = daysBetween(quote.rateDate, onDate);
  if (staleness < 0 || staleness > input.parameters.fxMaxStalenessDays) return null;
  return quote;
}

/** Step 1 — screen every observation and record why each one is, or is not, usable evidence. */
function screen(input: ValuationInput): { eligible: Candidate[]; rejected: ComparableRecord[]; liquidity90d: number } {
  const { parameters: p } = input;
  const exclusions = new Map(input.exclusions.map((e) => [e.observationId, e]));
  const eligible: Candidate[] = [];
  const rejected: ComparableRecord[] = [];
  let liquidity90d = 0;

  const sorted = [...input.observations].sort(
    (a, b) => b.observedAt.localeCompare(a.observedAt) || a.id.localeCompare(b.id),
  );

  for (const obs of sorted) {
    const ageDays = daysBetween(obs.observedAt, input.valuationDate);
    let record: ComparableRecord = {
      observationId: obs.id,
      sourceId: obs.sourceId,
      sourceReference: obs.sourceReference,
      sourceUrl: obs.sourceUrl,
      venue: obs.venue,
      observedAt: obs.observedAt,
      ageDays,
      amountMinor: obs.amountMinor,
      currency: obs.currency,
      buyersPremiumMinor: obs.buyersPremiumMinor,
      matchTier: null,
      differences: [],
      fx: null,
      basisAmountBaseMinor: null,
      included: false,
      suspectedOutlier: false,
      deviationFromMedianPct: null,
      rejection: null,
    };

    if (obs.kind !== "completed_sale") {
      rejected.push(reject(record, "NOT_COMPLETED_SALE", `Observation is a ${obs.kind.replace("_", " ")}, not a completed sale`));
      continue;
    }
    if (ageDays < 0) {
      rejected.push(reject(record, "AFTER_VALUATION_DATE", "Sale completed after the valuation date; evidence did not exist at that date"));
      continue;
    }
    const match = matchComparable(input.subject, obs.descriptor, p.secondaryMaxGradeSteps);
    if (!match.matched) {
      rejected.push(reject(record, "IDENTITY_MISMATCH", match.detail));
      continue;
    }
    record = { ...record, matchTier: match.tier, differences: match.differences };
    if (obs.verificationStatus === "failed") {
      rejected.push(reject(record, "VERIFICATION_FAILED", "Transaction failed source verification"));
      continue;
    }
    if (obs.verificationStatus === "unverified") {
      rejected.push(reject(record, "UNVERIFIED", "Transaction has not been verified as completed"));
      continue;
    }
    if (obs.armsLength === false) {
      rejected.push(reject(record, "NOT_ARMS_LENGTH", "Transaction is not at arm's length"));
      continue;
    }
    if (obs.armsLength == null) {
      rejected.push(reject(record, "ARMS_LENGTH_UNKNOWN", "Arm's-length status of the transaction is unknown"));
      continue;
    }
    if (match.tier === "exact" && ageDays <= 90) liquidity90d += 1;

    const exclusion = exclusions.get(obs.id);
    if (exclusion) {
      rejected.push(reject(record, "MANUAL_EXCLUSION", exclusion.reason, exclusion.excludedBy));
      continue;
    }
    const fx = resolveFx(input, obs);
    if (!fx) {
      rejected.push(reject(record, "NO_FX_RATE", `No documented ${obs.currency}→${input.baseCurrency} rate within ${p.fxMaxStalenessDays} days`));
      continue;
    }
    const basis =
      input.purpose === "insurance_replacement" ? obs.amountMinor + obs.buyersPremiumMinor : obs.amountMinor;
    record = { ...record, fx, basisAmountBaseMinor: convertMinor(basis, fx.rate) };
    eligible.push({ record, observation: obs });
  }
  return { eligible, rejected, liquidity90d };
}

interface Selection {
  selected: Candidate[];
  windowDays: number;
  method: MethodUsed;
}

/** Step 2 — pick the base comparable set, widening the window and then the match tier as required. */
function selectBase(eligible: Candidate[], input: ValuationInput): Selection | null {
  const p = input.parameters;
  const windows = [p.initialWindowDays, ...p.widenedWindowDays];
  const exact = eligible.filter((c) => c.record.matchTier === "exact");

  for (const windowDays of windows) {
    const inWindow = exact.filter((c) => c.record.ageDays <= windowDays);
    if (inWindow.length >= p.baseSampleSize) {
      return {
        selected: inWindow.slice(0, p.baseSampleSize),
        windowDays,
        method: windowDays === p.initialWindowDays ? "exact_recent" : "widened_window",
      };
    }
  }

  const widest = windows[windows.length - 1]!;
  const exactInWidest = exact.filter((c) => c.record.ageDays <= widest);
  const secondaryInWidest = eligible.filter((c) => c.record.matchTier === "secondary" && c.record.ageDays <= widest);
  const selected = [...exactInWidest, ...secondaryInWidest].slice(0, p.baseSampleSize);
  if (selected.length === 0) return null;
  return {
    selected,
    windowDays: widest,
    method: selected.some((c) => c.record.matchTier === "secondary") ? "secondary_comparables" : "widened_window",
  };
}

/** Step 3 — escalation: expand to 5–10 transactions of the same match tier, widening the window if needed. */
function expand(eligible: Candidate[], base: Selection, input: ValuationInput): Selection {
  const p = input.parameters;
  const allowSecondary = base.selected.some((c) => c.record.matchTier === "secondary");
  const pool = eligible.filter((c) => allowSecondary || c.record.matchTier === "exact");
  const windows = [p.initialWindowDays, ...p.widenedWindowDays].filter((w) => w >= base.windowDays);
  let windowDays = base.windowDays;
  let chosen = pool.filter((c) => c.record.ageDays <= windowDays);
  for (const w of windows) {
    windowDays = w;
    chosen = pool.filter((c) => c.record.ageDays <= w);
    if (chosen.length >= p.expandedSampleMin) break;
  }
  if (chosen.length <= base.selected.length) return base;
  const selected = chosen.slice(0, p.expandedSampleMax);
  const method: MethodUsed = selected.some((c) => c.record.matchTier === "secondary")
    ? "secondary_comparables"
    : windowDays === p.initialWindowDays
      ? "exact_expanded"
      : "widened_window";
  return { selected, windowDays, method };
}

function gradingCertainty(input: ValuationInput): ConfidenceFactors["gradingCertainty"] {
  const s = input.subject;
  if (s.productType === "sealed") return "sealed";
  if (s.gradingCompany) return s.certNumber ? "graded_certified" : "graded_uncertified";
  return s.condition ? "raw_condition_stated" : "raw_condition_unknown";
}

/**
 * Run the Cardcore Comparable Sales Method.
 *
 * The function is pure and deterministic: the same inputs always produce the same
 * result and inputs hash, which is what makes a stored valuation reproducible.
 */
export function valuate(input: ValuationInput): ValuationResult {
  const p = input.parameters;
  if (!Number.isInteger(input.quantity) || input.quantity < 1) throw new RangeError("quantity must be a positive integer");
  for (const e of input.exclusions) {
    if (!e.reason || e.reason.trim().length < 5) {
      throw new RangeError(`Exclusion of ${e.observationId} requires a documented reason`);
    }
  }

  const { eligible, rejected, liquidity90d } = screen(input);
  const flags: Flag[] = [];
  const assumptions: string[] = [
    "Only verified, arm's-length completed sales are treated as evidence; asking prices and price guides are recorded but never used.",
    input.purpose === "insurance_replacement"
      ? `Replacement value = mean gross buyer cost (sale price + buyer's premium) plus a ${p.replacementLoadingPct}% sourcing/transaction loading.`
      : "Market value = mean of the comparable sale prices, excluding buyer's premium (expected arm's-length realisation).",
    p.fxRateBasis === "valuation_date"
      ? "Foreign-currency evidence is translated at the documented FX rate available on the valuation date."
      : "Foreign-currency evidence is translated at the documented FX rate available on each sale date.",
    "Secondary comparables, where used, are not price-adjusted; their use lowers the confidence classification.",
  ];
  if (input.purpose === "historical") {
    assumptions.push(`Historical valuation: only evidence dated on or before ${input.valuationDate} is considered.`);
  }
  if (input.exclusions.length > 0) {
    flags.push({
      code: "MANUAL_EXCLUSIONS_APPLIED",
      message: `${input.exclusions.length} comparable(s) excluded with documented reasons`,
    });
  }

  const base = selectBase(eligible, input);
  let final = base;
  let baseStatistics: Statistics | null = null;
  let escalated = false;

  if (base) {
    const baseStats = describe(base.selected.map((c) => c.record.basisAmountBaseMinor!));
    if (base.selected.length >= p.baseSampleSize && baseStats.dispersionPct > p.dispersionThresholdPct) {
      escalated = true;
      baseStatistics = baseStats;
      flags.push({
        code: "DISPERSION_EXCEEDED",
        message: `Dispersion of base set ${baseStats.dispersionPct}% exceeds ${p.dispersionThresholdPct}% threshold; comparable set expanded`,
      });
      final = expand(eligible, base, input);
    }
  }

  let statistics: Statistics | null = null;
  let unitValueMinor: number | null = null;
  const selectedIds = new Set(final?.selected.map((c) => c.record.observationId));
  const comparables: ComparableRecord[] = [];

  if (final) {
    statistics = describe(final.selected.map((c) => c.record.basisAmountBaseMinor!));
    const med = median(final.selected.map((c) => c.record.basisAmountBaseMinor!));
    let outliers = 0;
    for (const c of eligible) {
      if (selectedIds.has(c.record.observationId)) {
        const dev = deviationPct(c.record.basisAmountBaseMinor!, med);
        const suspected = final.selected.length >= p.baseSampleSize && dev > p.outlierDeviationPct;
        if (suspected) outliers += 1;
        comparables.push({ ...c.record, included: true, deviationFromMedianPct: dev, suspectedOutlier: suspected });
      } else {
        const outside = c.record.ageDays > final.windowDays;
        comparables.push(
          reject(
            c.record,
            outside ? "OUTSIDE_WINDOW" : "NOT_SELECTED_OLDER",
            outside
              ? `Older than the ${final.windowDays}-day evidence window`
              : "Eligible, but more recent comparables were selected",
          ),
        );
      }
    }
    if (outliers > 0) {
      flags.push({
        code: "SUSPECTED_OUTLIERS",
        message: `${outliers} comparable(s) deviate from the median by more than ${p.outlierDeviationPct}%. They remain included unless excluded with a documented reason.`,
      });
    }
    if (escalated && statistics.dispersionPct > p.dispersionThresholdPct) {
      flags.push({
        code: "DISPERSION_PERSISTS_AFTER_ESCALATION",
        message: `Dispersion remains ${statistics.dispersionPct}% after expanding to ${statistics.count} comparables`,
      });
    }
    unitValueMinor =
      input.purpose === "insurance_replacement"
        ? applyPercentage(statistics.meanMinor, p.replacementLoadingPct)
        : statistics.meanMinor;
  } else {
    comparables.push(...eligible.map((c) => reject(c.record, "OUTSIDE_WINDOW", "Outside every permitted evidence window")));
  }
  comparables.push(...rejected);

  const used = final?.selected ?? [];
  const exactCount = used.filter((c) => c.record.matchTier === "exact").length;
  const ages = used.map((c) => c.record.ageDays);
  const factors: ConfidenceFactors = {
    comparableCount: used.length,
    exactMatchCount: exactCount,
    secondaryMatchCount: used.length - exactCount,
    medianAgeDays: ages.length ? median(ages) : null,
    newestAgeDays: ages.length ? Math.min(...ages) : null,
    dispersionPct: statistics?.dispersionPct ?? null,
    liquiditySales90d: liquidity90d,
    windowDays: final?.windowDays ?? null,
    gradingCertainty: gradingCertainty(input),
  };
  const confidence = classifyConfidence(factors, p, final != null);

  const methodUsed: MethodUsed = final?.method ?? "insufficient_evidence";
  const lowerConfidence = methodUsed === "widened_window" || methodUsed === "secondary_comparables" || used.length < p.baseSampleSize;
  if (methodUsed === "widened_window") {
    flags.push({ code: "WIDENED_WINDOW", message: `Evidence window widened to ${final!.windowDays} days` });
  }
  if (methodUsed === "secondary_comparables") {
    flags.push({ code: "SECONDARY_COMPARABLES_USED", message: "Secondary (non-exact) comparables were required" });
  }
  if (final && used.length < p.baseSampleSize) {
    flags.push({ code: "FEWER_THAN_BASE_SAMPLE", message: `Only ${used.length} adequate comparable(s) found` });
  }
  if (!final) {
    flags.push({ code: "INSUFFICIENT_EVIDENCE", message: "No adequate comparable sales; no value concluded" });
  } else if (lowerConfidence) {
    flags.push({ code: "LOWER_CONFIDENCE", message: "Valuation is flagged as lower-confidence" });
  }

  const inputsHash = sha256Hex(
    canonicalJson({
      subject: input.subject,
      purpose: input.purpose,
      valuationDate: input.valuationDate,
      baseCurrency: input.baseCurrency,
      quantity: input.quantity,
      methodologyVersion: input.methodologyVersion,
      parameters: p,
      observations: [...input.observations].sort((a, b) => a.id.localeCompare(b.id)),
      exclusions: [...input.exclusions].sort((a, b) => a.observationId.localeCompare(b.observationId)),
      fx: comparables.filter((c) => c.fx).map((c) => ({ id: c.observationId, fx: c.fx })),
    }),
  );

  return {
    status: final ? "concluded" : "insufficient_evidence",
    purpose: input.purpose,
    valuationDate: input.valuationDate,
    baseCurrency: input.baseCurrency,
    methodologyVersion: input.methodologyVersion,
    methodUsed,
    escalated,
    lowerConfidence: lowerConfidence || !final,
    windowDays: final?.windowDays ?? null,
    unitValueMinor,
    quantity: input.quantity,
    totalValueMinor: unitValueMinor == null ? null : unitValueMinor * input.quantity,
    statistics,
    baseStatistics,
    comparables,
    confidence,
    flags,
    assumptions,
    inputsHash,
  };
}
