import type { FxLookup } from "@cardcore/engine";
import type { Queryable } from "../db.js";
import { many, one } from "../db.js";
import { notFound } from "../errors.js";
import { convertAt } from "./fx.js";

export interface AssetRow {
  id: string;
  asset_ref: string;
  collection_id: string;
  card_identity_id: string;
  acquisition_date: string;
  acquisition_price_minor: number;
  acquisition_currency: string;
  acquisition_source: string | null;
  notes: string | null;
  created_at: string;
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
}

export interface GradingRow {
  id: string;
  asset_id: string;
  grading_company: string | null;
  cert_number: string | null;
  grade: string | null;
  condition: string | null;
  effective_date: string;
  reason: string;
  recorded_at: string;
}

export interface OwnershipRow {
  id: string;
  asset_id: string;
  event_type: "acquisition" | "disposal" | "loss" | "damage";
  effective_date: string;
  quantity: number;
  amount_minor: number | null;
  currency: string | null;
  counterparty: string | null;
  reason: string | null;
  recorded_at: string;
}

export interface EffectiveValuationRow {
  id: string;
  asset_id: string;
  purpose: string;
  valuation_date: string;
  status: string;
  quantity: number;
  unit_value_minor: number | null;
  effective_unit_value_minor: number | null;
  override_id: string | null;
  confidence: string;
  lower_confidence: boolean;
  dispersion_pct: number | null;
  method_used: string;
  methodology_version_id: string;
  performed_at: string;
}

export interface InsuranceLineRow {
  asset_id: string;
  schedule_id: string;
  change: string;
  new_value_minor: number;
  effective_date: string;
  seq: number;
}

const ASSET_SELECT = `
  SELECT a.*, ci.game, ci.product_type, ci.category, ci.set_code, ci.set_name, ci.card_number, ci.card_name,
         ci.language, ci.edition, ci.variant, ci.rarity, ci.external_refs
  FROM assets a JOIN card_identities ci ON ci.id = a.card_identity_id`;

export async function getAsset(db: Queryable, assetId: string): Promise<AssetRow & { owner_user_id: string; base_currency: string }> {
  const row = await one<AssetRow & { owner_user_id: string; base_currency: string }>(
    db,
    `SELECT x.*, c.owner_user_id, c.base_currency FROM (${ASSET_SELECT} WHERE a.id = $1) x JOIN collections c ON c.id = x.collection_id`,
    [assetId],
  );
  if (!row) throw notFound("Asset");
  return row;
}

export function heldQuantity(events: OwnershipRow[], date: string, knownAt?: string): number {
  return events
    .filter((e) => e.effective_date <= date && (!knownAt || e.recorded_at <= knownAt))
    .reduce((q, e) => (e.event_type === "acquisition" ? q + e.quantity : e.event_type === "damage" ? q : q - e.quantity), 0);
}

export function gradingAt(records: GradingRow[], date: string, knownAt?: string): GradingRow | null {
  const eligible = records
    .filter((g) => g.effective_date <= date && (!knownAt || g.recorded_at <= knownAt))
    .sort((a, b) => b.effective_date.localeCompare(a.effective_date) || b.recorded_at.localeCompare(a.recorded_at));
  return eligible[0] ?? records.slice().sort((a, b) => a.recorded_at.localeCompare(b.recorded_at))[0] ?? null;
}

export interface CollectionData {
  assets: AssetRow[];
  gradings: Map<string, GradingRow[]>;
  ownership: Map<string, OwnershipRow[]>;
  valuations: Map<string, EffectiveValuationRow[]>;
  insuranceLines: Map<string, InsuranceLineRow[]>;
}

function group<T extends { asset_id: string }>(rows: T[]): Map<string, T[]> {
  const map = new Map<string, T[]>();
  for (const row of rows) {
    const list = map.get(row.asset_id) ?? [];
    list.push(row);
    map.set(row.asset_id, list);
  }
  return map;
}

export async function loadCollectionData(db: Queryable, collectionId: string): Promise<CollectionData> {
  const assets = await many<AssetRow>(db, `${ASSET_SELECT} WHERE a.collection_id = $1 ORDER BY a.created_at`, [collectionId]);
  const ids = assets.map((a) => a.id);
  const [gradings, ownership, valuations, insuranceLines] = await Promise.all([
    many<GradingRow>(db, `SELECT * FROM grading_records WHERE asset_id = ANY($1)`, [ids]),
    many<OwnershipRow>(db, `SELECT * FROM ownership_events WHERE asset_id = ANY($1) ORDER BY effective_date, recorded_at`, [ids]),
    many<EffectiveValuationRow>(
      db,
      `SELECT id, asset_id, purpose, valuation_date, status, quantity, unit_value_minor, effective_unit_value_minor, override_id,
              confidence, lower_confidence, dispersion_pct, method_used, methodology_version_id, performed_at
       FROM valuations_effective WHERE asset_id = ANY($1) ORDER BY valuation_date DESC, performed_at DESC`,
      [ids],
    ),
    many<InsuranceLineRow>(
      db,
      `SELECT l.asset_id, e.schedule_id, l.change, l.new_value_minor, e.effective_date, e.seq
       FROM insurance_event_lines l JOIN insurance_events e ON e.id = l.event_id
       WHERE l.asset_id = ANY($1) ORDER BY e.effective_date DESC, e.seq DESC`,
      [ids],
    ),
  ]);
  return {
    assets,
    gradings: group(gradings),
    ownership: group(ownership),
    valuations: group(valuations),
    insuranceLines: group(insuranceLines),
  };
}

export interface AssetPosition {
  assetId: string;
  assetRef: string;
  cardName: string;
  setName: string;
  cardNumber: string | null;
  game: string;
  category: string;
  productType: string;
  gradingCompany: string | null;
  grade: string | null;
  condition: string | null;
  heldQuantity: number;
  status: "held" | "disposed" | "lost" | "not_yet_acquired";
  costBasisMinor: number | null;
  marketValueMinor: number | null;
  marketValuationId: string | null;
  marketValuationDate: string | null;
  confidence: string | null;
  insuredValueMinor: number;
  insuranceStatus: "insured" | "not_scheduled" | "removed";
  unrealisedGainMinor: number | null;
  realisedGainMinor: number;
  proceedsMinor: number;
}

export interface PortfolioSnapshot {
  date: string;
  knownAt: string | null;
  baseCurrency: string;
  totals: {
    marketValueMinor: number;
    insuredValueMinor: number;
    costBasisMinor: number;
    unrealisedGainMinor: number;
    realisedGainMinor: number;
    heldAssets: number;
    unvaluedAssets: number;
  };
  bySet: Array<{ key: string; valueMinor: number; count: number }>;
  byGradingCompany: Array<{ key: string; valueMinor: number; count: number }>;
  byCategory: Array<{ key: string; valueMinor: number; count: number }>;
  largestAssets: AssetPosition[];
  positions: AssetPosition[];
  warnings: string[];
}

/**
 * Point-in-time portfolio. Uses only ledger events effective on/before `date` and the
 * valuation record in force at `date`. With `knownAt`, events recorded after that instant
 * are also ignored (bitemporal "as known at" view).
 */
export function computePortfolio(
  data: CollectionData,
  date: string,
  baseCurrency: string,
  fx: FxLookup,
  knownAt?: string,
): PortfolioSnapshot {
  const warnings = new Set<string>();
  const positions: AssetPosition[] = [];

  for (const asset of data.assets) {
    const events = (data.ownership.get(asset.id) ?? []).filter((e) => !knownAt || e.recorded_at <= knownAt);
    const effective = events.filter((e) => e.effective_date <= date);
    if (!effective.some((e) => e.event_type === "acquisition")) continue;

    const acquiredQty = effective.filter((e) => e.event_type === "acquisition").reduce((q, e) => q + e.quantity, 0);
    const acquisitionCost = effective
      .filter((e) => e.event_type === "acquisition")
      .reduce<number | null>((sum, e) => {
        if (sum == null || e.amount_minor == null || e.currency == null) return sum;
        const converted = convertAt(fx, e.amount_minor, e.currency, baseCurrency, e.effective_date);
        if (converted == null) {
          warnings.add(`No FX rate ${e.currency}→${baseCurrency} for acquisition cost of ${asset.asset_ref}`);
          return null;
        }
        return sum + converted;
      }, 0);
    const unitCost = acquisitionCost == null || acquiredQty === 0 ? null : acquisitionCost / acquiredQty;
    const held = heldQuantity(events, date);

    let proceeds = 0;
    let realised = 0;
    for (const e of effective.filter((x) => x.event_type === "disposal")) {
      const amount =
        e.amount_minor != null && e.currency ? convertAt(fx, e.amount_minor, e.currency, baseCurrency, e.effective_date) : 0;
      if (amount == null) {
        warnings.add(`No FX rate ${e.currency}→${baseCurrency} for disposal of ${asset.asset_ref}`);
        continue;
      }
      proceeds += amount;
      realised += amount - Math.round((unitCost ?? 0) * e.quantity);
    }
    for (const e of effective.filter((x) => x.event_type === "loss")) {
      realised -= Math.round((unitCost ?? 0) * e.quantity);
    }

    const valuation = (data.valuations.get(asset.id) ?? []).find(
      (v) =>
        (v.purpose === "market" || v.purpose === "historical") &&
        v.status === "concluded" &&
        v.valuation_date <= date &&
        (!knownAt || v.performed_at <= knownAt),
    );
    const marketValue = held > 0 && valuation?.effective_unit_value_minor != null ? valuation.effective_unit_value_minor * held : held > 0 ? null : 0;
    const costBasis = unitCost == null ? null : Math.round(unitCost * held);

    const insLine = (data.insuranceLines.get(asset.id) ?? []).find((l) => l.effective_date <= date);
    const insured = insLine && insLine.change !== "removed" ? insLine.new_value_minor : 0;

    const grading = gradingAt(data.gradings.get(asset.id) ?? [], date, knownAt);
    const lastExit = [...effective].reverse().find((e) => e.event_type === "disposal" || e.event_type === "loss");
    positions.push({
      assetId: asset.id,
      assetRef: asset.asset_ref,
      cardName: asset.card_name,
      setName: asset.set_name,
      cardNumber: asset.card_number,
      game: asset.game,
      category: asset.category,
      productType: asset.product_type,
      gradingCompany: grading?.grading_company ?? null,
      grade: grading?.grade ?? null,
      condition: grading?.condition ?? null,
      heldQuantity: held,
      status: held > 0 ? "held" : lastExit?.event_type === "loss" ? "lost" : "disposed",
      costBasisMinor: costBasis,
      marketValueMinor: marketValue,
      marketValuationId: held > 0 ? (valuation?.id ?? null) : null,
      marketValuationDate: held > 0 ? (valuation?.valuation_date ?? null) : null,
      confidence: held > 0 ? (valuation?.confidence ?? null) : null,
      insuredValueMinor: insured,
      insuranceStatus: !insLine ? "not_scheduled" : insLine.change === "removed" ? "removed" : "insured",
      unrealisedGainMinor: marketValue != null && costBasis != null && held > 0 ? marketValue - costBasis : null,
      realisedGainMinor: realised,
      proceedsMinor: proceeds,
    });
  }

  const held = positions.filter((p) => p.heldQuantity > 0);
  const breakdown = (keyOf: (p: AssetPosition) => string) => {
    const map = new Map<string, { valueMinor: number; count: number }>();
    for (const p of held) {
      const entry = map.get(keyOf(p)) ?? { valueMinor: 0, count: 0 };
      entry.valueMinor += p.marketValueMinor ?? 0;
      entry.count += p.heldQuantity;
      map.set(keyOf(p), entry);
    }
    return [...map.entries()].map(([key, v]) => ({ key, ...v })).sort((a, b) => b.valueMinor - a.valueMinor);
  };

  return {
    date,
    knownAt: knownAt ?? null,
    baseCurrency,
    totals: {
      marketValueMinor: held.reduce((s, p) => s + (p.marketValueMinor ?? 0), 0),
      insuredValueMinor: positions.reduce((s, p) => s + p.insuredValueMinor, 0),
      costBasisMinor: held.reduce((s, p) => s + (p.costBasisMinor ?? 0), 0),
      unrealisedGainMinor: held.reduce((s, p) => s + (p.unrealisedGainMinor ?? 0), 0),
      realisedGainMinor: positions.reduce((s, p) => s + p.realisedGainMinor, 0),
      heldAssets: held.length,
      unvaluedAssets: held.filter((p) => p.marketValueMinor == null).length,
    },
    bySet: breakdown((p) => p.setName),
    byGradingCompany: breakdown((p) => (p.productType === "sealed" ? "Sealed" : (p.gradingCompany ?? "Raw"))),
    byCategory: breakdown((p) => `${p.game} · ${p.productType === "sealed" ? p.category : "single"}`),
    largestAssets: [...held].sort((a, b) => (b.marketValueMinor ?? 0) - (a.marketValueMinor ?? 0)).slice(0, 10),
    positions,
    warnings: [...warnings],
  };
}
