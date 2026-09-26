import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { addDays } from "@cardcore/engine";
import { audit } from "../audit.js";
import { many, one, withTx } from "../db.js";
import { badRequest } from "../errors.js";
import { loadFxLookup } from "../services/fx.js";
import { computePortfolio, loadCollectionData } from "../services/ledger.js";
import { today } from "../services/valuation.js";
import { assertCollectionAccess, currency, isoDate, minor, parse, user, uuid, type AppContext } from "./context.js";

const assetSchema = z
  .object({
    cardIdentityId: uuid,
    quantity: z.number().int().min(1).default(1),
    acquisitionDate: isoDate,
    acquisitionPriceMinor: minor,
    acquisitionCurrency: currency,
    acquisitionSource: z.string().max(200).nullable().default(null),
    notes: z.string().max(2000).nullable().default(null),
    gradingCompany: z.string().max(40).nullable().default(null),
    certNumber: z.string().max(60).nullable().default(null),
    grade: z.string().max(20).nullable().default(null),
    condition: z.string().max(40).nullable().default(null),
  })
  .refine((b) => (b.gradingCompany == null) === (b.grade == null), { message: "gradingCompany and grade must be given together" });

export async function collectionRoutes(app: FastifyInstance, ctx: AppContext) {
  app.get("/api/collections", async (req) => {
    const u = user(req);
    return many(ctx.pool, `SELECT * FROM collections WHERE owner_user_id = $1 ORDER BY created_at`, [u.id]);
  });

  app.post("/api/collections", async (req, reply) => {
    const u = user(req);
    const body = parse(z.object({ name: z.string().min(1).max(120), baseCurrency: currency }), req.body);
    const row = await one<{ id: string }>(
      ctx.pool,
      `INSERT INTO collections (owner_user_id, name, base_currency) VALUES ($1,$2,$3) RETURNING *`,
      [u.id, body.name, body.baseCurrency],
    );
    await audit(ctx.pool, u.id, "collection.created", "collection", row!.id, body, req.id);
    return reply.code(201).send(row);
  });

  app.get("/api/collections/:id/assets", async (req) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    const c = await assertCollectionAccess(ctx.pool, u, id);
    const q = parse(z.object({ date: isoDate.optional() }), req.query);
    const data = await loadCollectionData(ctx.pool, id);
    const date = q.date ?? today();
    const snapshot = computePortfolio(data, date, c.base_currency, await loadFxLookup(ctx.pool, date));
    return snapshot.positions;
  });

  app.post("/api/collections/:id/assets", async (req, reply) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    await assertCollectionAccess(ctx.pool, u, id);
    const b = parse(assetSchema, req.body);
    if (b.acquisitionDate > today()) throw badRequest("Acquisition date cannot be in the future");
    const identity = await one<{ product_type: string }>(ctx.pool, `SELECT product_type FROM card_identities WHERE id = $1`, [b.cardIdentityId]);
    if (!identity) throw badRequest("Unknown card identity");
    const asset = await withTx(ctx.pool, async (tx) => {
      const a = await one<{ id: string; asset_ref: string }>(
        tx,
        `INSERT INTO assets (collection_id, card_identity_id, acquisition_date, acquisition_price_minor, acquisition_currency, acquisition_source, notes, created_by)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id, asset_ref`,
        [id, b.cardIdentityId, b.acquisitionDate, b.acquisitionPriceMinor, b.acquisitionCurrency, b.acquisitionSource, b.notes, u.id],
      );
      await tx.query(
        `INSERT INTO grading_records (asset_id, grading_company, cert_number, grade, condition, effective_date, reason, recorded_by)
         VALUES ($1,$2,$3,$4,$5,$6,'initial',$7)`,
        [a!.id, b.gradingCompany, b.certNumber, b.grade, identity.product_type === "sealed" ? "sealed" : b.condition, b.acquisitionDate, u.id],
      );
      await tx.query(
        `INSERT INTO ownership_events (asset_id, event_type, effective_date, quantity, amount_minor, currency, counterparty, recorded_by)
         VALUES ($1,'acquisition',$2,$3,$4,$5,$6,$7)`,
        [a!.id, b.acquisitionDate, b.quantity, b.acquisitionPriceMinor, b.acquisitionCurrency, b.acquisitionSource, u.id],
      );
      await audit(tx, u.id, "asset.created", "asset", a!.id, { ...b, assetRef: a!.asset_ref }, req.id);
      return a!;
    });
    return reply.code(201).send(asset);
  });

  app.get("/api/collections/:id/portfolio", async (req) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    const c = await assertCollectionAccess(ctx.pool, u, id);
    const q = parse(z.object({ date: isoDate.optional(), knownAt: z.string().datetime().optional() }), req.query);
    const date = q.date ?? today();
    const data = await loadCollectionData(ctx.pool, id);
    return computePortfolio(data, date, c.base_currency, await loadFxLookup(ctx.pool, date), q.knownAt ? new Date(q.knownAt).toISOString() : undefined);
  });

  app.get("/api/collections/:id/portfolio/history", async (req) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    const c = await assertCollectionAccess(ctx.pool, u, id);
    const q = parse(
      z.object({ from: isoDate.optional(), to: isoDate.optional(), points: z.coerce.number().int().min(2).max(120).default(30) }),
      req.query,
    );
    const data = await loadCollectionData(ctx.pool, id);
    const to = q.to ?? today();
    const firstAcq = data.assets.map((a) => a.acquisition_date).sort()[0];
    const from = q.from ?? firstAcq ?? addDays(to, -365);
    const fx = await loadFxLookup(ctx.pool, to);
    const span = Math.max(1, Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000));
    const step = Math.max(1, Math.ceil(span / (q.points - 1)));
    const series = [];
    for (let d = 0; ; d += step) {
      const date = d >= span ? to : addDays(from, d);
      const s = computePortfolio(data, date, c.base_currency, fx);
      series.push({
        date,
        marketValueMinor: s.totals.marketValueMinor,
        insuredValueMinor: s.totals.insuredValueMinor,
        costBasisMinor: s.totals.costBasisMinor,
        heldAssets: s.totals.heldAssets,
        unvaluedAssets: s.totals.unvaluedAssets,
      });
      if (date === to) break;
    }
    return { baseCurrency: c.base_currency, series };
  });
}
