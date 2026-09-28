import { canonicalJson, sha256Hex } from "@cardcore/engine";
import type { Db, Queryable, Tx } from "../db.js";
import { many, one, withTx } from "../db.js";
import { audit } from "../audit.js";
import { notFound } from "../errors.js";
import { heldQuantity, type OwnershipRow } from "./ledger.js";
import { currentMethodology, runValuation, today } from "./valuation.js";

export type InsuranceEventType =
  | "initial_declaration"
  | "acquisition"
  | "disposal"
  | "revaluation"
  | "grading_change"
  | "loss_damage"
  | "insurer_adjustment";

export interface EventLineInput {
  assetId: string;
  change: "added" | "removed" | "revalued" | "adjusted";
  quantity: number;
  previousValueMinor: number;
  newValueMinor: number;
  valuationId: string | null;
}

export interface ScheduleRow {
  id: string;
  collection_id: string;
  insurer_name: string | null;
  policy_reference: string | null;
  customer_reference: string | null;
  base_currency: string;
  notification_rules: Record<string, unknown>;
  created_at: string;
}

export interface InsuranceEventRow {
  id: string;
  schedule_id: string;
  seq: number;
  event_type: InsuranceEventType;
  effective_date: string;
  previous_declared_minor: number;
  revised_declared_minor: number;
  reason: string;
  methodology_version_id: string | null;
  prev_hash: string | null;
  event_hash: string;
  created_by: string;
  created_at: string;
}

function sortLines(lines: EventLineInput[]): EventLineInput[] {
  return [...lines].sort((a, b) => (a.assetId < b.assetId ? -1 : a.assetId > b.assetId ? 1 : 0));
}

export async function getSchedule(db: Queryable, scheduleId: string) {
  const row = await one<ScheduleRow & { owner_user_id: string }>(
    db,
    `SELECT s.*, c.owner_user_id FROM insurance_schedules s JOIN collections c ON c.id = s.collection_id WHERE s.id = $1`,
    [scheduleId],
  );
  if (!row) throw notFound("Insurance schedule");
  return row;
}

/** Current scheduled (declared) value per asset: the latest line for each asset. */
export async function scheduledValues(db: Queryable, scheduleId: string): Promise<Map<string, { value: number; quantity: number }>> {
  const rows = await many<{ asset_id: string; change: string; new_value_minor: number; quantity: number }>(
    db,
    `SELECT DISTINCT ON (l.asset_id) l.asset_id, l.change, l.new_value_minor, l.quantity
     FROM insurance_event_lines l JOIN insurance_events e ON e.id = l.event_id
     WHERE e.schedule_id = $1
     ORDER BY l.asset_id, e.seq DESC`,
    [scheduleId],
  );
  return new Map(
    rows.filter((r) => r.change !== "removed").map((r) => [r.asset_id, { value: r.new_value_minor, quantity: r.quantity }]),
  );
}

/**
 * Append an Insurance Adjustment Event. The previous declared value is read from the last
 * event, never recomputed or overwritten, and each event is hash-chained to its predecessor.
 */
export async function appendInsuranceEvent(
  tx: Tx,
  scheduleId: string,
  input: { type: InsuranceEventType; effectiveDate: string; reason: string; lines: EventLineInput[]; userId: string; requestId?: string },
): Promise<InsuranceEventRow> {
  await tx.query(`SELECT id FROM insurance_schedules WHERE id = $1 FOR UPDATE`, [scheduleId]);
  const last = await one<InsuranceEventRow>(
    tx,
    `SELECT * FROM insurance_events WHERE schedule_id = $1 ORDER BY seq DESC LIMIT 1`,
    [scheduleId],
  );
  const seq = (last?.seq ?? 0) + 1;
  const previous = last?.revised_declared_minor ?? 0;
  const lines = sortLines(input.lines);
  const delta = lines.reduce((s, l) => s + (l.newValueMinor - l.previousValueMinor), 0);
  const revised = previous + delta;
  const methodology = await currentMethodology(tx, input.effectiveDate);
  const prevHash = last?.event_hash ?? null;
  const eventHash = sha256Hex(
    canonicalJson({
      scheduleId,
      seq,
      type: input.type,
      effectiveDate: input.effectiveDate,
      previousDeclaredMinor: previous,
      revisedDeclaredMinor: revised,
      reason: input.reason,
      lines,
      methodologyVersion: methodology.id,
      prevHash,
    }),
  );
  const event = await one<InsuranceEventRow>(
    tx,
    `INSERT INTO insurance_events (schedule_id, seq, event_type, effective_date, previous_declared_minor, revised_declared_minor,
       reason, methodology_version_id, prev_hash, event_hash, created_by)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING *`,
    [scheduleId, seq, input.type, input.effectiveDate, previous, revised, input.reason, methodology.id, prevHash, eventHash, input.userId],
  );
  for (const l of lines) {
    await tx.query(
      `INSERT INTO insurance_event_lines (event_id, asset_id, change, quantity, previous_value_minor, new_value_minor, valuation_id)
       VALUES ($1,$2,$3,$4,$5,$6,$7)`,
      [event!.id, l.assetId, l.change, l.quantity, l.previousValueMinor, l.newValueMinor, l.valuationId],
    );
  }
  await audit(tx, input.userId, "insurance_event.appended", "insurance_event", event!.id, {
    scheduleId,
    seq,
    type: input.type,
    previous,
    revised,
    lines: lines.length,
  }, input.requestId);
  return event!;
}

/**
 * Called inside the disposal/loss transaction: removes (or pro-rates) the asset on every
 * schedule on which it is insured, producing a Disposal or Loss/Damage adjustment event.
 */
export async function onAssetExit(
  tx: Tx,
  input: {
    assetId: string;
    assetRef: string;
    collectionId: string;
    heldBefore: number;
    quantityOut: number;
    effectiveDate: string;
    type: "disposal" | "loss_damage";
    userId: string;
    requestId?: string;
  },
): Promise<InsuranceEventRow[]> {
  const schedules = await many<{ id: string }>(tx, `SELECT id FROM insurance_schedules WHERE collection_id = $1`, [input.collectionId]);
  const events: InsuranceEventRow[] = [];
  for (const s of schedules) {
    const current = (await scheduledValues(tx, s.id)).get(input.assetId);
    if (!current || current.value === 0) continue;
    const heldAfter = input.heldBefore - input.quantityOut;
    const newValue = heldAfter <= 0 ? 0 : Math.round((current.value * heldAfter) / input.heldBefore);
    events.push(
      await appendInsuranceEvent(tx, s.id, {
        type: input.type,
        effectiveDate: input.effectiveDate,
        reason:
          input.type === "disposal"
            ? `Disposal of ${input.quantityOut} × ${input.assetRef}`
            : `Loss/damage of ${input.quantityOut} × ${input.assetRef}`,
        lines: [
          {
            assetId: input.assetId,
            change: heldAfter <= 0 ? "removed" : "adjusted",
            quantity: Math.max(heldAfter, 0),
            previousValueMinor: current.value,
            newValueMinor: newValue,
            valuationId: null,
          },
        ],
        userId: input.userId,
        requestId: input.requestId,
      }),
    );
  }
  return events;
}

/**
 * Reconcile a schedule against the live collection: every held asset gets a fresh insurance /
 * replacement valuation; new assets are added, changed values revalued. Nothing is overwritten —
 * each change is a line on an appended event.
 */
export async function reconcileSchedule(
  pool: Db,
  scheduleId: string,
  userId: string,
  requestId?: string,
): Promise<{ events: InsuranceEventRow[]; unvalued: string[] }> {
  const schedule = await getSchedule(pool, scheduleId);
  const effectiveDate = today();
  const assets = await many<{ id: string; asset_ref: string }>(
    pool,
    `SELECT id, asset_ref FROM assets WHERE collection_id = $1 ORDER BY created_at`,
    [schedule.collection_id],
  );
  const current = await scheduledValues(pool, scheduleId);
  const hasEvents = Boolean(await one(pool, `SELECT 1 FROM insurance_events WHERE schedule_id = $1 LIMIT 1`, [scheduleId]));

  const added: EventLineInput[] = [];
  const revalued: EventLineInput[] = [];
  const unvalued: string[] = [];
  for (const asset of assets) {
    const ownership = await many<OwnershipRow>(pool, `SELECT * FROM ownership_events WHERE asset_id = $1`, [asset.id]);
    const held = heldQuantity(ownership, effectiveDate);
    if (held <= 0) continue;
    const { id: valuationId, result } = await runValuation(pool, {
      assetId: asset.id,
      purpose: "insurance_replacement",
      valuationDate: effectiveDate,
      userId,
      requestId,
    });
    const existing = current.get(asset.id);
    if (result.totalValueMinor == null) {
      unvalued.push(asset.asset_ref);
      continue;
    }
    if (!existing) {
      added.push({ assetId: asset.id, change: "added", quantity: held, previousValueMinor: 0, newValueMinor: result.totalValueMinor, valuationId });
    } else if (existing.value !== result.totalValueMinor) {
      revalued.push({
        assetId: asset.id,
        change: "revalued",
        quantity: held,
        previousValueMinor: existing.value,
        newValueMinor: result.totalValueMinor,
        valuationId,
      });
    }
  }

  const events = await withTx(pool, async (tx) => {
    const out: InsuranceEventRow[] = [];
    if (added.length) {
      out.push(
        await appendInsuranceEvent(tx, scheduleId, {
          type: hasEvents ? "acquisition" : "initial_declaration",
          effectiveDate,
          reason: hasEvents ? `${added.length} asset(s) added to schedule` : `Initial declaration of ${added.length} asset(s)`,
          lines: added,
          userId,
          requestId,
        }),
      );
    }
    if (revalued.length) {
      out.push(
        await appendInsuranceEvent(tx, scheduleId, {
          type: "revaluation",
          effectiveDate,
          reason: `Revaluation of ${revalued.length} asset(s) under the current methodology`,
          lines: revalued,
          userId,
          requestId,
        }),
      );
    }
    return out;
  });
  return { events, unvalued };
}

/** Verify that the hash chain of a schedule's events is intact. */
export async function verifyChain(db: Queryable, scheduleId: string): Promise<{ valid: boolean; brokenAtSeq: number | null }> {
  const events = await many<InsuranceEventRow>(db, `SELECT * FROM insurance_events WHERE schedule_id = $1 ORDER BY seq`, [scheduleId]);
  let prev: string | null = null;
  for (const e of events) {
    const lines = await many<{ asset_id: string; change: EventLineInput["change"]; quantity: number; previous_value_minor: number; new_value_minor: number; valuation_id: string | null }>(
      db,
      `SELECT asset_id, change, quantity, previous_value_minor, new_value_minor, valuation_id FROM insurance_event_lines WHERE event_id = $1`,
      [e.id],
    );
    const expected = sha256Hex(
      canonicalJson({
        scheduleId,
        seq: e.seq,
        type: e.event_type,
        effectiveDate: e.effective_date,
        previousDeclaredMinor: e.previous_declared_minor,
        revisedDeclaredMinor: e.revised_declared_minor,
        reason: e.reason,
        lines: sortLines(lines.map((l) => ({
          assetId: l.asset_id,
          change: l.change,
          quantity: l.quantity,
          previousValueMinor: l.previous_value_minor,
          newValueMinor: l.new_value_minor,
          valuationId: l.valuation_id,
        }))),
        methodologyVersion: e.methodology_version_id,
        prevHash: prev,
      }),
    );
    if (e.prev_hash !== prev || e.event_hash !== expected) return { valid: false, brokenAtSeq: e.seq };
    prev = e.event_hash;
  }
  return { valid: true, brokenAtSeq: null };
}
