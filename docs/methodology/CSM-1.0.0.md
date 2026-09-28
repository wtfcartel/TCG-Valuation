# Cardcore Comparable Sales Method — version CSM-1.0.0

Effective 2026-09-26. Implemented in `packages/engine` (`CSM_1_0_0_PARAMETERS`). Any change to the rules or parameters below requires a new version, so that every stored valuation can be reproduced under the version it cites.

## 1. Purposes of value

| Purpose | Definition | Basis per comparable |
|---|---|---|
| **Market Value** | Expected arm's-length market realisation, based primarily on recent comparable completed transactions | Sale price **excluding** buyer's premium |
| **Insurance / Replacement Value** | Reasonable cost to replace the asset with an equivalent item in the open market | Sale price **plus** buyer's premium; the concluded mean is then increased by a **5% sourcing/transaction loading** |
| **Historical Value** | Market value at a past date, using only evidence dated on or before that date | As Market Value; later sales are rejected as `AFTER_VALUATION_DATE` |

These values are calculated and stored separately and are never substituted for one another.

## 2. Subject identification (closest equivalent asset)

The subject is described by game, product type, set, card number, language, edition, variant, grading company, grade (graded) or condition (raw), and certification number.

- **Exact comparable:** identical game, product type, set, card number (leading zeros ignored), language, edition and variant, **and** an identical grading basis (same company and grade, or both raw in the same condition). Sealed products match on identity alone.
- **Secondary comparable:** identical card identity with **one bounded difference** in grading basis: grade within ±1 at the same company; the same grade at a different company; or raw condition one step away on the M–NM–LP–MP–HP–DMG ladder. Secondary comparables are **not price-adjusted** in this version, and their use always makes the confidence *Limited*.
- Any other difference (language, edition, variant, set, graded vs raw) is not comparable: `IDENTITY_MISMATCH`.

## 3. Evidence screening

Every observation for the identity is screened. Each rejection is **stored with the valuation**, together with its code:

| Code | Rule |
|---|---|
| `NOT_COMPLETED_SALE` | Asking prices and price guides are never treated as evidence |
| `AFTER_VALUATION_DATE` | Sale completed after the valuation date |
| `IDENTITY_MISMATCH` | See §2 |
| `VERIFICATION_FAILED` / `UNVERIFIED` | Only transactions verified as completed are used |
| `NOT_ARMS_LENGTH` / `ARMS_LENGTH_UNKNOWN` | Only confirmed arm's-length transactions are used |
| `MANUAL_EXCLUSION` | Excluded by a user, with a documented reason (≥ 5 characters) and the user's identity |
| `NO_FX_RATE` | No documented FX rate within 7 days before the FX date |
| `OUTSIDE_WINDOW` / `NOT_SELECTED_OLDER` | Eligible, but not selected (§4) |

**FX:** foreign-currency amounts are converted at the documented rate available on the **valuation date** (the most recent rate not after that date, at most 7 days old). Direct, inverse and EUR/USD cross rates are allowed. The rate, rate date and source are stored per comparable.

## 4. Selection and calculation

1. **Base set:** the **3 most recent** eligible exact comparables within **90 days** of the valuation date.
2. **Thin market:** if fewer than 3 exist, widen the window progressively to **180, 365, then 730 days** (`widened_window`). If there are still fewer than 3, add the most recent secondary comparables within 730 days (`secondary_comparables`). If only 1–2 adequate comparables exist, a value is still concluded but flagged `FEWER_THAN_BASE_SAMPLE` and *Limited*. If none exist, no value is concluded (`insufficient_evidence`).
3. **Statistics** on the basis amounts: arithmetic mean, median, minimum, maximum, range, and **dispersion = (max − min) ÷ mean × 100**. The coefficient of variation is reported for information only.
4. **Conclusion:** the concluded value is the **arithmetic mean** of the selected comparables (rounded half away from zero to the minor unit). For insurance, mean × 1.05.

## 5. Escalation rule (dispersion)

If the base set has dispersion **> 22.5%** (the threshold sits inside the brief's 20–25% band and is set as a parameter):

1. Flag `DISPERSION_EXCEEDED` and keep the base-set statistics on the valuation record.
2. Expand to the most recent **5–10** eligible comparables of the same tier, widening the window if needed to reach 5.
3. **Flag suspected outliers**: any comparable deviating from the median by more than **35%**. Outliers are **not removed automatically**. Exclusion requires a documented reason (§3, `MANUAL_EXCLUSION`) and produces a **new** valuation that references the one it supersedes.
4. Recalculate the mean on the expanded set. If dispersion is still above the threshold, flag `DISPERSION_PERSISTS_AFTER_ESCALATION`.

## 6. Confidence classification (no numeric score)

The stored factors are: comparable count, exact vs secondary count, median and newest evidence age, dispersion, liquidity (exact-match eligible sales in the last 90 days), window used, and grading certainty (graded + cert / graded without cert / raw with stated condition / raw condition unknown / sealed).

- **Limited evidence** if any of the following: fewer than 3 comparables; any secondary comparable; median age > 365 days; dispersion > 2 × threshold (45%); or no value concluded.
- **High evidence** only if all of the following: not Limited; dispersion ≤ 22.5%; median age ≤ 90 days; ≥ 3 exact sales in the last 90 days; and the asset is graded with a certification number, or is sealed.
- **Moderate evidence** otherwise. For example, raw cards are capped at Moderate because their condition is owner-assessed.

The rules that produced the classification are stored as `confidence_reasons` and printed in the report.

## 7. Overrides and auditability

A valuation row is never updated. Manual overrides are separate rows recording the overriding value, reason (≥ 10 characters), user and role. The effective value is the latest override, or the computed value if there is none. Each valuation stores: valuation date, methodology version and parameters, subject snapshot, all comparables considered (used and rejected, with reasons, FX and basis amounts), statistics, flags, assumptions, confidence factors and reasons, performer, and an `inputs_hash` (SHA-256 of the canonicalised inputs), so the result can be reproduced.

## 8. Limitations

Values depend on the completeness and accuracy of third-party sale data. Raw-card condition is not inspected. Slab authenticity is not verified unless a cert-verification source is integrated. Unadjusted secondary comparables can bias results for thinly traded assets; this is why they force *Limited* confidence.

## 9. Methodology validation vs valuation responsibility

An independent reviewer (e.g. a CA/CPA) may review **this methodology** and be recorded in `methodology_reviews`. Reports then state the reviewer, date, scope and conclusion, and state expressly that the review covers the methodology only: the reviewer has **not** reviewed or certified any individual valuation unless they were separately engaged to review that assignment. Responsibility for individual valuations rests with the valuer named in the report.
