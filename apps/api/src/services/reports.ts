import { canonicalJson, sha256Hex } from "@cardcore/engine";
import type { Db, Queryable } from "../db.js";
import { many, one, withTx } from "../db.js";
import { audit } from "../audit.js";
import { badRequest, notFound } from "../errors.js";
import { getSchedule, type InsuranceEventRow } from "./insurance.js";
import { loadCollectionData, computePortfolio } from "./ledger.js";
import { loadFxLookup } from "./fx.js";
import { today } from "./valuation.js";

export const VALUATION_REPORT_SCHEMA = "cardcore.valuation-report/1";
export const INSURANCE_REPORT_SCHEMA = "cardcore.insurance-adjustment/1";

export const LIMITATIONS = [
  "Values are estimates derived from historical completed-sale evidence available to Cardcore at the valuation date; they are not offers to buy or sell and do not guarantee any realisation.",
  "Card identity, grade and condition are as recorded by the owner. Raw-card condition has not been physically inspected. Graded items are valued on the recorded grading company, grade and certification number; authenticity of the slab has not been independently verified unless stated.",
  "Comparable-sale data is sourced from third parties and may contain errors or omissions. Evidence that failed verification, was not at arm's length, or was an asking price has been excluded.",
  "Thinly traded assets may have few or no adequate comparables; such valuations are flagged as lower-confidence and should be read with their confidence classification.",
  "Cardcore does not calculate insurance premiums or determine cover. Whether and when a change in declared value affects cover or premium is determined solely by the insurer.",
];

export function methodologyReviewStatement(
  reviews: Array<{ reviewer_name: string; credentials: string; organisation: string | null; review_date: string; scope_statement: string; conclusion: string }>,
  methodologyId: string,
): string {
  if (reviews.length === 0) {
    return `The Cardcore Comparable Sales Method (${methodologyId}) has not been independently reviewed.`;
  }
  const r = reviews[0]!;
  return (
    `The design of the Cardcore Comparable Sales Method (${methodologyId}) was reviewed by ${r.reviewer_name}, ${r.credentials}` +
    `${r.organisation ? ` of ${r.organisation}` : ""}, on ${r.review_date}. Scope: ${r.scope_statement} Conclusion: ${r.conclusion} ` +
    `That review addresses the methodology only. The reviewer has not reviewed, audited or certified the individual valuations ` +
    `in this report and accepts no responsibility for them, unless this report separately states that the reviewer reviewed this assignment.`
  );
}

async function methodologyBlock(db: Queryable, methodologyId: string) {
  const m = await one<{ id: string; name: string; summary: string; parameters: unknown; document_ref: string; effective_from: string }>(
    db,
    `SELECT id, name, summary, parameters, document_ref, effective_from FROM methodology_versions WHERE id = $1`,
    [methodologyId],
  );
  const reviews = await many<{ reviewer_name: string; credentials: string; organisation: string | null; review_date: string; scope_statement: string; conclusion: string }>(
    db,
    `SELECT r.name AS reviewer_name, r.credentials, r.organisation, mr.review_date, mr.scope_statement, mr.conclusion
     FROM methodology_reviews mr JOIN reviewers r ON r.id = mr.reviewer_id
     WHERE mr.methodology_version_id = $1 ORDER BY mr.review_date DESC`,
    [methodologyId],
  );
  return { ...m, reviews, reviewStatement: methodologyReviewStatement(reviews, methodologyId) };
}

async function storeReport(
  pool: Db,
  input: { type: "valuation" | "insurance_adjustment"; collectionId: string; scheduleId: string | null; schema: string; methodologyId: string | null; userId: string; build: (version: number) => Record<string, unknown>; requestId?: string },
) {
  return withTx(pool, async (tx) => {
    await tx.query(`SELECT id FROM collections WHERE id = $1 FOR UPDATE`, [input.collectionId]);
    const last = await one<{ version: number }>(
      tx,
      `SELECT max(version) AS version FROM reports WHERE collection_id = $1 AND report_type = $2`,
      [input.collectionId, input.type],
    );
    const version = (last?.version ?? 0) + 1;
    const payload = input.build(version);
    const sha = sha256Hex(canonicalJson(payload));
    const row = await one<{ id: string; generated_at: string }>(
      tx,
      `INSERT INTO reports (report_type, collection_id, schedule_id, version, schema_version, payload, payload_sha256, methodology_version_id, generated_by)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id, generated_at`,
      [input.type, input.collectionId, input.scheduleId, version, input.schema, JSON.stringify(payload), sha, input.methodologyId, input.userId],
    );
    await audit(tx, input.userId, "report.generated", "report", row!.id, { type: input.type, version, sha256: sha }, input.requestId);
    return { id: row!.id, version, sha256: sha, payload, generatedAt: row!.generated_at };
  });
}

export async function generateValuationReport(
  pool: Db,
  input: { collectionId: string; purpose: "market" | "insurance_replacement"; userId: string; requestId?: string },
) {
  const collection = await one<{ id: string; name: string; base_currency: string; owner_name: string; owner_email: string }>(
    pool,
    `SELECT c.id, c.name, c.base_currency, u.display_name AS owner_name, u.email AS owner_email
     FROM collections c JOIN users u ON u.id = c.owner_user_id WHERE c.id = $1`,
    [input.collectionId],
  );
  if (!collection) throw notFound("Collection");
  const requester = await one<{ display_name: string; role: string; email: string }>(pool, `SELECT display_name, role, email FROM users WHERE id = $1`, [input.userId]);
  const valuationDate = today();
  const data = await loadCollectionData(pool, input.collectionId);
  const fx = await loadFxLookup(pool, valuationDate);
  const portfolio = computePortfolio(data, valuationDate, collection.base_currency, fx);
  const held = portfolio.positions.filter((p) => p.heldQuantity > 0);

  const assets: Array<{ assetRef: string; description: string; game: string; grading: string; quantity: number; valuation: Record<string, unknown> | null }> = [];
  let total = 0;
  const methodologyIds = new Set<string>();
  for (const p of held) {
    const v = (data.valuations.get(p.assetId) ?? []).find(
      (x) => x.purpose === (input.purpose === "market" ? "market" : "insurance_replacement") && x.status === "concluded",
    );
    let valuation = null;
    if (v) {
      methodologyIds.add(v.methodology_version_id);
      const detail = await one<Record<string, unknown>>(
        pool,
        `SELECT v.*, u.display_name AS performed_by_name FROM valuations_effective v JOIN users u ON u.id = v.performed_by WHERE v.id = $1`,
        [v.id],
      );
      const comparables = await many<Record<string, unknown>>(
        pool,
        `SELECT vc.included, vc.match_tier, vc.differences, vc.age_days, vc.fx_rate, vc.fx_rate_date, vc.fx_source, vc.basis_amount_base_minor,
                vc.suspected_outlier, vc.deviation_from_median_pct, vc.rejection_code, vc.rejection_detail,
                po.source_id, po.source_reference, po.source_url, po.observation_kind, po.observed_at, po.venue, po.amount_minor,
                po.currency, po.buyers_premium_minor, po.verification_status
         FROM valuation_comparables vc JOIN price_observations po ON po.id = vc.observation_id
         WHERE vc.valuation_id = $1 ORDER BY vc.included DESC, po.observed_at DESC`,
        [v.id],
      );
      const overrides = await many<Record<string, unknown>>(
        pool,
        `SELECT o.override_unit_value_minor, o.reason, o.overrider_role, o.created_at, u.display_name AS overridden_by
         FROM valuation_overrides o JOIN users u ON u.id = o.overridden_by WHERE o.valuation_id = $1 ORDER BY o.created_at`,
        [v.id],
      );
      const unit = v.effective_unit_value_minor ?? 0;
      const lineTotal = unit * p.heldQuantity;
      total += lineTotal;
      valuation = {
        valuationId: v.id,
        valuationDate: v.valuation_date,
        methodologyVersion: v.methodology_version_id,
        performedBy: detail?.performed_by_name,
        computedUnitValueMinor: v.unit_value_minor,
        concludedUnitValueMinor: unit,
        totalValueMinor: lineTotal,
        method: v.method_used,
        confidence: v.confidence,
        confidenceReasons: detail?.confidence_reasons,
        confidenceFactors: detail?.confidence_factors,
        statistics: detail?.statistics,
        baseStatistics: detail?.base_statistics,
        flags: detail?.flags,
        assumptions: detail?.assumptions,
        inputsHash: detail?.inputs_hash,
        overrides,
        comparablesUsed: comparables.filter((c) => c.included),
        comparablesRejected: comparables.filter((c) => !c.included),
      };
    }
    assets.push({
      assetRef: p.assetRef,
      description: `${p.cardName} — ${p.setName}${p.cardNumber ? ` #${p.cardNumber}` : ""}`,
      game: p.game,
      grading: p.productType === "sealed" ? "Sealed" : p.gradingCompany ? `${p.gradingCompany} ${p.grade}` : `Raw (${p.condition ?? "condition not stated"})`,
      quantity: p.heldQuantity,
      valuation,
    });
  }
  const methodologyId = [...methodologyIds][0] ?? (await one<{ id: string }>(pool, `SELECT id FROM methodology_versions ORDER BY effective_from DESC LIMIT 1`))!.id;
  const methodology = await methodologyBlock(pool, methodologyId);

  return storeReport(pool, {
    type: "valuation",
    collectionId: input.collectionId,
    scheduleId: null,
    schema: VALUATION_REPORT_SCHEMA,
    methodologyId,
    userId: input.userId,
    requestId: input.requestId,
    build: (version) => ({
      schemaVersion: VALUATION_REPORT_SCHEMA,
      reportVersion: version,
      client: { name: collection.owner_name, email: collection.owner_email, collection: collection.name },
      purpose: input.purpose === "market" ? "Market Value" : "Insurance / Replacement Value",
      purposeDefinition:
        input.purpose === "market"
          ? "Expected arm's-length market realisation based primarily on recent comparable transactions."
          : "Reasonable cost to replace each asset with an equivalent item in the open market, including buyer's premium and a documented sourcing loading.",
      valuationDate,
      baseCurrency: collection.base_currency,
      methodology,
      additionalMethodologyVersions: [...methodologyIds].filter((id) => id !== methodologyId),
      assumptions: [
        "Each asset is as described in the ledger (identity, language, edition, variant, grading/condition).",
        "The asset is valued individually; no portfolio or bulk-sale discount or premium is applied.",
        "Values are expressed in the collection base currency using the documented FX rates shown with each comparable.",
      ],
      limitations: LIMITATIONS,
      assets,
      unvaluedAssets: assets.filter((a) => !a.valuation).map((a) => a.assetRef),
      collectionTotalMinor: total,
      valuer: {
        name: requester?.display_name,
        role: requester?.role,
        statement:
          "Individual valuations were computed by the Cardcore engine applying the stated methodology version to the evidence listed. " +
          "Manual overrides, where present, are identified with the person who made them and their reason. Responsibility for the " +
          "individual valuations rests with the valuer named here, not with any methodology reviewer.",
      },
      conclusion:
        `On the basis of the evidence, assumptions and limitations set out in this report, the ${input.purpose === "market" ? "market" : "insurance/replacement"} ` +
        `value of the ${assets.length - assets.filter((a) => !a.valuation).length} valued asset(s) as at ${valuationDate} is ` +
        `${collection.base_currency} ${(total / 100).toFixed(2)}.`,
    }),
  });
}

/**
 * Insurer-facing adjustment payload. By default it covers every event since the previous
 * adjustment report for the schedule, so consecutive reports chain without gaps.
 */
export async function generateInsuranceAdjustmentReport(
  pool: Db,
  input: { scheduleId: string; fromSeq?: number; userId: string; requestId?: string },
) {
  const schedule = await getSchedule(pool, input.scheduleId);
  const lastReport = await one<{ payload: { eventRange?: { toSeq: number } } }>(
    pool,
    `SELECT payload FROM reports WHERE schedule_id = $1 AND report_type = 'insurance_adjustment' ORDER BY version DESC LIMIT 1`,
    [input.scheduleId],
  );
  const fromSeq = input.fromSeq ?? (lastReport?.payload.eventRange?.toSeq ?? 0) + 1;
  const events = await many<InsuranceEventRow>(
    pool,
    `SELECT * FROM insurance_events WHERE schedule_id = $1 AND seq >= $2 ORDER BY seq`,
    [input.scheduleId, fromSeq],
  );
  if (events.length === 0) throw badRequest("No insurance adjustment events to report since the last report");
  const lines = await many<Record<string, unknown> & { event_id: string; change: string }>(
    pool,
    `SELECT l.event_id, l.change, l.quantity, l.previous_value_minor, l.new_value_minor, l.valuation_id,
            a.asset_ref, ci.card_name, ci.set_name, ci.card_number, ci.game,
            v.confidence, v.method_used, v.inputs_hash, v.methodology_version_id, v.valuation_date,
            (SELECT count(*) FROM valuation_comparables vc WHERE vc.valuation_id = v.id AND vc.included) AS comparables_used
     FROM insurance_event_lines l
     JOIN assets a ON a.id = l.asset_id
     JOIN card_identities ci ON ci.id = a.card_identity_id
     LEFT JOIN valuations v ON v.id = l.valuation_id
     WHERE l.event_id = ANY($1)`,
    [events.map((e) => e.id)],
  );
  const first = events[0]!;
  const last = events[events.length - 1]!;
  const methodologyId = last.methodology_version_id ?? first.methodology_version_id;
  const methodology = methodologyId ? await methodologyBlock(pool, methodologyId) : null;
  const describeLine = (l: Record<string, unknown>) => ({
    assetRef: l.asset_ref,
    description: `${l.card_name} — ${l.set_name}${l.card_number ? ` #${l.card_number}` : ""}`,
    quantity: l.quantity,
    previousValueMinor: l.previous_value_minor,
    newValueMinor: l.new_value_minor,
  });

  return storeReport(pool, {
    type: "insurance_adjustment",
    collectionId: schedule.collection_id,
    scheduleId: schedule.id,
    schema: INSURANCE_REPORT_SCHEMA,
    methodologyId: methodologyId ?? null,
    userId: input.userId,
    requestId: input.requestId,
    build: (version) => ({
      schemaVersion: INSURANCE_REPORT_SCHEMA,
      reportVersion: version,
      policy: {
        insurer: schedule.insurer_name,
        policyReference: schedule.policy_reference,
        customerReference: schedule.customer_reference,
        scheduleId: schedule.id,
      },
      currency: schedule.base_currency,
      previousDeclaredValueMinor: first.previous_declared_minor,
      revisedDeclaredValueMinor: last.revised_declared_minor,
      netChangeMinor: last.revised_declared_minor - first.previous_declared_minor,
      effectiveDate: last.effective_date,
      eventRange: { fromSeq: first.seq, toSeq: last.seq, firstEventHash: first.event_hash, lastEventHash: last.event_hash },
      adjustments: events.map((e) => ({
        seq: e.seq,
        type: e.event_type,
        effectiveDate: e.effective_date,
        reason: e.reason,
        previousDeclaredValueMinor: e.previous_declared_minor,
        revisedDeclaredValueMinor: e.revised_declared_minor,
        eventHash: e.event_hash,
        prevHash: e.prev_hash,
      })),
      assetsAdded: lines.filter((l) => l.change === "added").map(describeLine),
      assetsRemoved: lines.filter((l) => l.change === "removed").map(describeLine),
      assetsRevalued: lines.filter((l) => l.change === "revalued" || l.change === "adjusted").map(describeLine),
      evidence: lines
        .filter((l) => l.valuation_id)
        .map((l) => ({
          assetRef: l.asset_ref,
          valuationId: l.valuation_id,
          valuationDate: l.valuation_date,
          methodologyVersion: l.methodology_version_id,
          method: l.method_used,
          confidence: l.confidence,
          comparablesUsed: l.comparables_used,
          inputsHash: l.inputs_hash,
        })),
      methodology: methodology
        ? { id: methodology.id, name: methodology.name, documentRef: methodology.document_ref, reviewStatement: methodology.reviewStatement }
        : null,
      insurerRules: schedule.notification_rules,
      disclaimer:
        "Cardcore reports changes in declared value only. It does not calculate premiums or determine cover; the insurer decides whether " +
        "and when any change applies (immediately, at reconciliation or at renewal).",
    }),
  });
}

export async function getReport(db: Queryable, reportId: string) {
  const row = await one<{
    id: string;
    report_type: "valuation" | "insurance_adjustment";
    collection_id: string;
    version: number;
    schema_version: string;
    payload: Record<string, unknown>;
    payload_sha256: string;
    generated_at: string;
    owner_user_id: string;
  }>(
    db,
    `SELECT r.*, c.owner_user_id FROM reports r JOIN collections c ON c.id = r.collection_id WHERE r.id = $1`,
    [reportId],
  );
  if (!row) throw notFound("Report");
  const recomputed = sha256Hex(canonicalJson(row.payload));
  return { ...row, integrity: { algorithm: "sha256", stored: row.payload_sha256, verified: recomputed === row.payload_sha256 } };
}
