import {
  valuate,
  type AssetDescriptor,
  type Exclusion,
  type MethodologyParameters,
  type Observation,
  type ValuationPurpose,
  type ValuationResult,
} from "@cardcore/engine";
import type { Db, Queryable } from "../db.js";
import { many, one, withTx } from "../db.js";
import { audit } from "../audit.js";
import { badRequest, notFound } from "../errors.js";
import { loadFxLookup } from "./fx.js";
import { getAsset, gradingAt, heldQuantity, type GradingRow, type OwnershipRow } from "./ledger.js";

interface ObservationRow {
  id: string;
  source_id: string;
  source_reference: string;
  source_url: string | null;
  observation_kind: Observation["kind"];
  grading_company: string | null;
  grade: string | null;
  condition: string | null;
  observed_at: string;
  venue: string | null;
  amount_minor: number;
  currency: string;
  buyers_premium_minor: number;
  arms_length: boolean | null;
  verification_status: Observation["verificationStatus"];
  licence_status: string;
  reliability_tier: number;
  game: string;
  product_type: "single" | "sealed";
  set_code: string;
  card_number: string | null;
  language: string;
  edition: string | null;
  variant: string | null;
}

export async function currentMethodology(db: Queryable, onDate: string) {
  const row = await one<{ id: string; parameters: MethodologyParameters }>(
    db,
    `SELECT id, parameters FROM methodology_versions WHERE effective_from <= $1 ORDER BY effective_from DESC, created_at DESC LIMIT 1`,
    [onDate],
  );
  if (!row) {
    const earliest = await one<{ id: string; parameters: MethodologyParameters }>(
      db,
      `SELECT id, parameters FROM methodology_versions ORDER BY effective_from ASC LIMIT 1`,
    );
    if (!earliest) throw new Error("No methodology version registered");
    return earliest;
  }
  return row;
}

/**
 * Observations usable for an asset: shared market data from server-fetched sources, plus evidence the
 * asset's owner uploaded themselves (owner-scoped sources). Another user's uploads are never used.
 */
export async function loadObservations(db: Queryable, cardIdentityId: string, ownerUserId: string): Promise<ObservationRow[]> {
  return many<ObservationRow>(
    db,
    `SELECT po.*, ds.licence_status, ds.reliability_tier, ci.game, ci.product_type, ci.set_code, ci.card_number, ci.language, ci.edition, ci.variant
     FROM price_observations po
     JOIN card_identities ci ON ci.id = po.card_identity_id
     JOIN data_sources ds ON ds.id = po.source_id
     WHERE po.card_identity_id = $1
       AND (NOT ds.owner_scoped OR po.owner_scope = $2)
     ORDER BY po.observed_at DESC`,
    [cardIdentityId, ownerUserId],
  );
}

/** Preference when one transaction is evidenced by several sources: licensed/open first, scraped last. */
const LICENCE_RANK: Record<string, number> = { licensed: 0, open: 1, user_supplied: 2, synthetic: 3, unlicensed: 4, restricted: 5 };

function toObservation(r: ObservationRow): Observation {
  return {
    // Marketplace transaction IDs are shared across sources (e.g. "ebay:<item id>").
    transactionKey: /^ebay:\d+$/.test(r.source_reference) ? r.source_reference : null,
    sourcePriority: (LICENCE_RANK[r.licence_status] ?? 9) * 10 + r.reliability_tier,
    id: r.id,
    sourceId: r.source_id,
    sourceReference: r.source_reference,
    sourceUrl: r.source_url,
    kind: r.observation_kind,
    descriptor: {
      game: r.game,
      productType: r.product_type,
      setCode: r.set_code,
      cardNumber: r.card_number,
      language: r.language,
      edition: r.edition,
      variant: r.variant,
      gradingCompany: r.grading_company,
      grade: r.grade,
      condition: r.condition,
    },
    observedAt: r.observed_at,
    venue: r.venue,
    amountMinor: r.amount_minor,
    currency: r.currency,
    buyersPremiumMinor: r.buyers_premium_minor,
    armsLength: r.arms_length,
    verificationStatus: r.verification_status,
  };
}

export interface RunValuationOptions {
  assetId: string;
  purpose: Exclude<ValuationPurpose, "historical"> | "historical";
  valuationDate?: string;
  exclusions?: Array<{ observationId: string; reason: string }>;
  supersedesValuationId?: string | null;
  userId: string;
  requestId?: string;
}

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export async function runValuation(pool: Db, opts: RunValuationOptions): Promise<{ id: string; result: ValuationResult }> {
  const asset = await getAsset(pool, opts.assetId);
  const valuationDate = opts.valuationDate ?? today();
  if (valuationDate > today()) throw badRequest("Valuation date cannot be in the future");
  // A market valuation dated in the past is, by definition, a historical valuation.
  const purpose: ValuationPurpose = opts.purpose === "market" && valuationDate < today() ? "historical" : opts.purpose;

  const [gradings, ownership] = await Promise.all([
    many<GradingRow>(pool, `SELECT * FROM grading_records WHERE asset_id = $1`, [asset.id]),
    many<OwnershipRow>(pool, `SELECT * FROM ownership_events WHERE asset_id = $1`, [asset.id]),
  ]);
  const quantity = heldQuantity(ownership, valuationDate);
  if (quantity <= 0) throw badRequest(`Asset ${asset.asset_ref} was not held on ${valuationDate}`);
  const grading = gradingAt(gradings, valuationDate);

  const subject: AssetDescriptor & { certNumber: string | null } = {
    game: asset.game,
    productType: asset.product_type,
    setCode: asset.set_code,
    cardNumber: asset.card_number,
    language: asset.language,
    edition: asset.edition,
    variant: asset.variant,
    gradingCompany: grading?.grading_company ?? null,
    grade: grading?.grade ?? null,
    condition: asset.product_type === "sealed" ? "sealed" : (grading?.condition ?? null),
    certNumber: grading?.cert_number ?? null,
  };

  const methodology = await currentMethodology(pool, valuationDate);
  const observations = (await loadObservations(pool, asset.card_identity_id, asset.owner_user_id)).map(toObservation);
  const knownIds = new Set(observations.map((o) => o.id));
  const exclusions: Exclusion[] = (opts.exclusions ?? []).map((e) => {
    if (!knownIds.has(e.observationId)) throw badRequest(`Unknown observation ${e.observationId}`);
    return { ...e, excludedBy: opts.userId };
  });
  const fx = await loadFxLookup(pool, valuationDate);

  let result: ValuationResult;
  try {
    result = valuate({
      subject,
      purpose,
      valuationDate,
      baseCurrency: asset.base_currency,
      quantity,
      methodologyVersion: methodology.id,
      parameters: methodology.parameters,
      observations,
      exclusions,
      fx,
    });
  } catch (error) {
    if (error instanceof RangeError) throw badRequest(error.message);
    throw error;
  }

  const id = await withTx(pool, async (tx) => {
    const s = result.statistics;
    const row = await one<{ id: string }>(
      tx,
      `INSERT INTO valuations (asset_id, purpose, valuation_date, status, methodology_version_id, base_currency, subject_snapshot,
         quantity, unit_value_minor, total_value_minor, mean_minor, median_minor, min_minor, max_minor, range_minor, dispersion_pct,
         statistics, base_statistics, method_used, window_days, escalated, lower_confidence, confidence, confidence_factors,
         confidence_reasons, flags, assumptions, inputs_hash, supersedes_valuation_id, performed_by)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30)
       RETURNING id`,
      [
        asset.id,
        purpose,
        valuationDate,
        result.status,
        methodology.id,
        asset.base_currency,
        JSON.stringify({ ...subject, assetRef: asset.asset_ref, cardName: asset.card_name, setName: asset.set_name }),
        quantity,
        result.unitValueMinor,
        result.totalValueMinor,
        s?.meanMinor ?? null,
        s?.medianMinor ?? null,
        s?.minMinor ?? null,
        s?.maxMinor ?? null,
        s?.rangeMinor ?? null,
        s?.dispersionPct ?? null,
        s ? JSON.stringify(s) : null,
        result.baseStatistics ? JSON.stringify(result.baseStatistics) : null,
        result.methodUsed,
        result.windowDays,
        result.escalated,
        result.lowerConfidence,
        result.confidence.classification,
        JSON.stringify(result.confidence.factors),
        JSON.stringify(result.confidence.reasons),
        JSON.stringify(result.flags),
        JSON.stringify(result.assumptions),
        result.inputsHash,
        opts.supersedesValuationId ?? null,
        opts.userId,
      ],
    );
    for (const c of result.comparables) {
      await tx.query(
        `INSERT INTO valuation_comparables (valuation_id, observation_id, included, match_tier, differences, age_days, fx_rate,
           fx_rate_id, fx_rate_date, fx_source, basis_amount_base_minor, suspected_outlier, deviation_from_median_pct,
           rejection_code, rejection_detail, excluded_by)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)`,
        [
          row!.id,
          c.observationId,
          c.included,
          c.matchTier,
          JSON.stringify(c.differences),
          c.ageDays,
          c.fx?.rate ?? null,
          c.fx?.rateId ?? null,
          c.fx?.rateDate ?? null,
          c.fx?.source ?? null,
          c.basisAmountBaseMinor,
          c.suspectedOutlier,
          c.deviationFromMedianPct,
          c.rejection?.code ?? null,
          c.rejection?.detail ?? null,
          c.rejection?.excludedBy ?? null,
        ],
      );
    }
    await audit(tx, opts.userId, "valuation.created", "valuation", row!.id, {
      assetId: asset.id,
      purpose,
      valuationDate,
      status: result.status,
      unitValueMinor: result.unitValueMinor,
      exclusions: exclusions.length,
      supersedes: opts.supersedesValuationId ?? null,
    }, opts.requestId);
    return row!.id;
  });
  return { id, result };
}

export async function getValuation(db: Queryable, valuationId: string) {
  const valuation = await one<Record<string, unknown> & { asset_id: string }>(
    db,
    `SELECT v.*, u.display_name AS performed_by_name FROM valuations_effective v JOIN users u ON u.id = v.performed_by WHERE v.id = $1`,
    [valuationId],
  );
  if (!valuation) throw notFound("Valuation");
  const comparables = await many(
    db,
    `SELECT vc.*, po.source_id, po.source_reference, po.source_url, po.observation_kind, po.observed_at, po.venue, po.amount_minor,
            po.currency, po.buyers_premium_minor, po.grading_company, po.grade, po.condition, po.verification_status,
            po.arms_length, po.fetched_at, ds.licence_status
     FROM valuation_comparables vc JOIN price_observations po ON po.id = vc.observation_id
     JOIN data_sources ds ON ds.id = po.source_id
     WHERE vc.valuation_id = $1
     ORDER BY vc.included DESC, po.observed_at DESC`,
    [valuationId],
  );
  const overrides = await many(
    db,
    `SELECT o.*, u.display_name AS overridden_by_name FROM valuation_overrides o JOIN users u ON u.id = o.overridden_by
     WHERE o.valuation_id = $1 ORDER BY o.created_at`,
    [valuationId],
  );
  return { ...valuation, comparables, overrides };
}
