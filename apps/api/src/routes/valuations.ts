import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { audit } from "../audit.js";
import { many, one } from "../db.js";
import { getValuation } from "../services/valuation.js";
import { assertAssetAccess, assertValuationAccess, currency, isoDate, minor, parse, user, uuid, type AppContext } from "./context.js";

export async function valuationRoutes(app: FastifyInstance, ctx: AppContext) {
  app.get("/api/assets/:id/valuations", async (req) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    await assertAssetAccess(ctx.pool, u, id);
    return many(ctx.pool, `SELECT * FROM valuations_effective WHERE asset_id = $1 ORDER BY performed_at DESC`, [id]);
  });

  app.get("/api/valuations/:id", async (req) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    await assertValuationAccess(ctx.pool, u, id);
    return getValuation(ctx.pool, id);
  });

  app.post("/api/valuations/:id/overrides", async (req, reply) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    await assertValuationAccess(ctx.pool, u, id);
    const b = parse(z.object({ overrideUnitValueMinor: minor, reason: z.string().trim().min(10).max(2000) }), req.body);
    const row = await one(
      ctx.pool,
      `INSERT INTO valuation_overrides (valuation_id, override_unit_value_minor, reason, overridden_by, overrider_role)
       VALUES ($1,$2,$3,$4,$5) RETURNING *`,
      [id, b.overrideUnitValueMinor, b.reason, u.id, u.role],
    );
    await audit(ctx.pool, u.id, "valuation.overridden", "valuation", id, b, req.id);
    return reply.code(201).send(row);
  });

  // ───────────── FX rates (documented, append-only) ─────────────

  app.get("/api/fx-rates", async (req) => {
    user(req);
    return many(ctx.pool, `SELECT * FROM fx_rates ORDER BY rate_date DESC, base_currency, quote_currency LIMIT 500`);
  });

  app.post("/api/fx-rates", async (req, reply) => {
    const u = user(req);
    const b = parse(
      z.object({
        baseCurrency: currency,
        quoteCurrency: currency,
        rate: z.number().positive(),
        rateDate: isoDate,
        source: z.string().min(2).max(200),
        sourceUrl: z.string().url().nullable().default(null),
      }),
      req.body,
    );
    const row = await one(
      ctx.pool,
      `INSERT INTO fx_rates (base_currency, quote_currency, rate, rate_date, source, source_url, recorded_by)
       VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (base_currency, quote_currency, rate_date, source) DO NOTHING RETURNING *`,
      [b.baseCurrency, b.quoteCurrency, b.rate, b.rateDate, b.source, b.sourceUrl, u.id],
    );
    if (row) await audit(ctx.pool, u.id, "fx_rate.recorded", "fx_rate", (row as { id: string }).id, b, req.id);
    return reply.code(row ? 201 : 200).send(row ?? { duplicate: true });
  });

  // ───────────── Reference data & audit ─────────────

  app.get("/api/methodology", async () => {
    const versions = await many(ctx.pool, `SELECT * FROM methodology_versions ORDER BY effective_from DESC`);
    const reviews = await many(
      ctx.pool,
      `SELECT mr.*, r.name AS reviewer_name, r.credentials, r.organisation FROM methodology_reviews mr JOIN reviewers r ON r.id = mr.reviewer_id`,
    );
    return { versions, reviews };
  });

  app.get("/api/sources", async () => ctx.sources.list());

  app.get("/api/audit", async (req) => {
    const u = user(req);
    const q = parse(z.object({ entityType: z.string().optional(), entityId: z.string().optional(), limit: z.coerce.number().int().max(500).default(100) }), req.query);
    return many(
      ctx.pool,
      `SELECT * FROM audit_events WHERE ($1::text IS NULL OR entity_type = $1) AND ($2::text IS NULL OR entity_id = $2)
         AND ($3::boolean OR actor_user_id = $4)
       ORDER BY id DESC LIMIT $5`,
      [q.entityType ?? null, q.entityId ?? null, u.role === "admin", u.id, q.limit],
    );
  });
}
