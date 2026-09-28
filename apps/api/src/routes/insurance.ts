import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { audit } from "../audit.js";
import { many, one, withTx } from "../db.js";
import { badRequest } from "../errors.js";
import { appendInsuranceEvent, reconcileSchedule, scheduledValues, verifyChain } from "../services/insurance.js";
import { today } from "../services/valuation.js";
import { assertCollectionAccess, assertScheduleAccess, isoDate, minor, parse, user, uuid, type AppContext } from "./context.js";

const rulesSchema = z
  .object({
    relative_change_pct: z.number().positive().optional(),
    absolute_change_minor: z.number().int().positive().optional(),
    reconciliation: z.enum(["monthly", "quarterly", "annual_renewal"]).optional(),
  })
  .default({ relative_change_pct: 10, absolute_change_minor: 250_000, reconciliation: "quarterly" });

export async function insuranceRoutes(app: FastifyInstance, ctx: AppContext) {
  app.get("/api/collections/:id/schedules", async (req) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    await assertCollectionAccess(ctx.pool, u, id);
    return many(
      ctx.pool,
      `SELECT s.*, (SELECT revised_declared_minor FROM insurance_events e WHERE e.schedule_id = s.id ORDER BY seq DESC LIMIT 1) AS declared_value_minor
       FROM insurance_schedules s WHERE s.collection_id = $1 ORDER BY created_at`,
      [id],
    );
  });

  app.post("/api/collections/:id/schedules", async (req, reply) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    const c = await assertCollectionAccess(ctx.pool, u, id);
    const b = parse(
      z.object({
        insurerName: z.string().max(200).nullable().default(null),
        policyReference: z.string().max(200).nullable().default(null),
        customerReference: z.string().max(200).nullable().default(null),
        notificationRules: rulesSchema,
      }),
      req.body,
    );
    const row = await one<{ id: string }>(
      ctx.pool,
      `INSERT INTO insurance_schedules (collection_id, insurer_name, policy_reference, customer_reference, base_currency, notification_rules, created_by)
       VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING *`,
      [id, b.insurerName, b.policyReference, b.customerReference, c.base_currency, JSON.stringify(b.notificationRules), u.id],
    );
    await audit(ctx.pool, u.id, "insurance_schedule.created", "insurance_schedule", row!.id, b, req.id);
    return reply.code(201).send(row);
  });

  app.get("/api/schedules/:id", async (req) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    await assertScheduleAccess(ctx.pool, u, id);
    const schedule = await one(ctx.pool, `SELECT * FROM insurance_schedules WHERE id = $1`, [id]);
    const events = await many(ctx.pool, `SELECT * FROM insurance_events WHERE schedule_id = $1 ORDER BY seq`, [id]);
    const lines = await many(
      ctx.pool,
      `SELECT l.*, e.seq, a.asset_ref, ci.card_name, ci.set_name FROM insurance_event_lines l
       JOIN insurance_events e ON e.id = l.event_id JOIN assets a ON a.id = l.asset_id JOIN card_identities ci ON ci.id = a.card_identity_id
       WHERE e.schedule_id = $1 ORDER BY e.seq`,
      [id],
    );
    const current = await scheduledValues(ctx.pool, id);
    const last = events[events.length - 1] as { revised_declared_minor: number } | undefined;
    return {
      schedule,
      declaredValueMinor: last?.revised_declared_minor ?? 0,
      scheduledAssets: [...current.entries()].map(([assetId, v]) => ({ assetId, valueMinor: v.value, quantity: v.quantity })),
      events: events.map((e) => ({ ...e, lines: lines.filter((l) => (l as { event_id: string }).event_id === (e as { id: string }).id) })),
      chain: await verifyChain(ctx.pool, id),
    };
  });

  app.post("/api/schedules/:id/reconcile", async (req, reply) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    await assertScheduleAccess(ctx.pool, u, id);
    return reply.code(201).send(await reconcileSchedule(ctx.pool, id, u.id, req.id));
  });

  // Insurer-agreed value for an asset (e.g. after insurer review). Recorded, never overwriting history.
  app.post("/api/schedules/:id/adjustments", async (req, reply) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    const s = await assertScheduleAccess(ctx.pool, u, id);
    const b = parse(
      z.object({ assetId: uuid, newValueMinor: minor, effectiveDate: isoDate.default(today()), reason: z.string().trim().min(10).max(2000) }),
      req.body,
    );
    const asset = await one<{ collection_id: string }>(ctx.pool, `SELECT collection_id FROM assets WHERE id = $1`, [b.assetId]);
    if (!asset || asset.collection_id !== s.collection_id) throw badRequest("Asset does not belong to this schedule's collection");
    const current = (await scheduledValues(ctx.pool, id)).get(b.assetId);
    if (!current) throw badRequest("Asset is not on this schedule; reconcile first");
    const event = await withTx(ctx.pool, (tx) =>
      appendInsuranceEvent(tx, id, {
        type: "insurer_adjustment",
        effectiveDate: b.effectiveDate,
        reason: b.reason,
        lines: [{ assetId: b.assetId, change: "adjusted", quantity: current.quantity, previousValueMinor: current.value, newValueMinor: b.newValueMinor, valuationId: null }],
        userId: u.id,
        requestId: req.id,
      }),
    );
    return reply.code(201).send(event);
  });
}
