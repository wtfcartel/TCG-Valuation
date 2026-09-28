import type { AssetDescriptor, MatchTier } from "./types.js";

export type MatchOutcome =
  | { matched: true; tier: MatchTier; differences: string[] }
  | { matched: false; detail: string };

const CONDITION_LADDER = ["M", "NM", "LP", "MP", "HP", "DMG"] as const;

const CONDITION_ALIASES: Record<string, string> = {
  mint: "M",
  m: "M",
  "near-mint": "NM",
  "near mint": "NM",
  nm: "NM",
  excellent: "LP",
  "lightly-played": "LP",
  "lightly played": "LP",
  lp: "LP",
  good: "MP",
  "moderately-played": "MP",
  "moderately played": "MP",
  mp: "MP",
  played: "HP",
  "heavily-played": "HP",
  "heavily played": "HP",
  hp: "HP",
  poor: "DMG",
  damaged: "DMG",
  dmg: "DMG",
};

export function normaliseCondition(condition: string | null): string | null {
  if (condition == null) return null;
  const key = condition.trim().toLowerCase();
  if (key === "sealed") return "SEALED";
  return CONDITION_ALIASES[key] ?? condition.trim().toUpperCase();
}

function norm(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase().replace(/\s+/g, " ");
}

/** Card numbers compare without leading zeros ("004/102" ≡ "4/102"). */
function normCardNumber(value: string | null): string {
  return norm(value)
    .split("/")
    .map((part) => part.replace(/^0+(?=\d)/, ""))
    .join("/");
}

function numericGrade(grade: string | null): number | null {
  if (grade == null) return null;
  const match = /(\d+(?:\.\d+)?)/.exec(grade);
  return match ? Number(match[1]) : null;
}

/**
 * Decide whether an observation describes the same asset as the subject.
 *
 * Exact: identical card identity (game, product type, set, number, language, edition,
 * variant) and identical grading basis (same grading company and grade, or both raw in
 * the same condition).
 *
 * Secondary: identical card identity, but the grading basis differs in exactly one
 * bounded way — grade within `maxGradeSteps` at the same company, the same grade at a
 * different company, or a raw condition one step away. Secondary comparables are used
 * unadjusted and always lower the confidence classification.
 *
 * Anything else (different language, edition, variant, set …) is not comparable.
 */
export function matchComparable(
  subject: AssetDescriptor,
  candidate: AssetDescriptor,
  maxGradeSteps: number,
): MatchOutcome {
  const identityChecks: Array<[string, string, string]> = [
    ["game", norm(subject.game), norm(candidate.game)],
    ["product type", subject.productType, candidate.productType],
    ["set", norm(subject.setCode), norm(candidate.setCode)],
    ["card number", normCardNumber(subject.cardNumber), normCardNumber(candidate.cardNumber)],
    ["language", norm(subject.language), norm(candidate.language)],
    ["edition", norm(subject.edition), norm(candidate.edition)],
    ["variant", norm(subject.variant), norm(candidate.variant)],
  ];
  const mismatched = identityChecks.filter(([, a, b]) => a !== b).map(([name]) => name);
  if (mismatched.length > 0) {
    return { matched: false, detail: `Different ${mismatched.join(", ")}` };
  }

  if (subject.productType === "sealed") {
    return { matched: true, tier: "exact", differences: [] };
  }

  const subjectGraded = subject.gradingCompany != null;
  const candidateGraded = candidate.gradingCompany != null;
  if (subjectGraded !== candidateGraded) {
    return {
      matched: false,
      detail: subjectGraded ? "Candidate is raw; subject is graded" : "Candidate is graded; subject is raw",
    };
  }

  if (subjectGraded) {
    const sameCompany = norm(subject.gradingCompany) === norm(candidate.gradingCompany);
    const sameGrade = norm(subject.grade) === norm(candidate.grade);
    if (sameCompany && sameGrade) return { matched: true, tier: "exact", differences: [] };
    if (!sameCompany && sameGrade) {
      return { matched: true, tier: "secondary", differences: ["grading company"] };
    }
    if (sameCompany) {
      const a = numericGrade(subject.grade);
      const b = numericGrade(candidate.grade);
      if (a != null && b != null && Math.abs(a - b) <= maxGradeSteps) {
        return { matched: true, tier: "secondary", differences: ["grade"] };
      }
    }
    return { matched: false, detail: "Grading company and/or grade not comparable" };
  }

  const subjectCondition = normaliseCondition(subject.condition);
  const candidateCondition = normaliseCondition(candidate.condition);
  if (subjectCondition === candidateCondition) return { matched: true, tier: "exact", differences: [] };
  if (subjectCondition == null || candidateCondition == null) {
    return { matched: true, tier: "secondary", differences: ["condition"] };
  }
  const ia = CONDITION_LADDER.indexOf(subjectCondition as (typeof CONDITION_LADDER)[number]);
  const ib = CONDITION_LADDER.indexOf(candidateCondition as (typeof CONDITION_LADDER)[number]);
  if (ia >= 0 && ib >= 0 && Math.abs(ia - ib) <= 1) {
    return { matched: true, tier: "secondary", differences: ["condition"] };
  }
  return { matched: false, detail: "Raw condition not comparable" };
}
