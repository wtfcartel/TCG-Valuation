import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { audit } from "../audit.js";
import { many, one } from "../db.js";
import { badRequest, HttpError } from "../errors.js";
import { parse, user, type AppContext } from "./context.js";

const identitySchema = z.object({
  game: z.enum(["pokemon", "one_piece", "mtg", "yugioh", "lorcana", "other"]),
  productType: z.enum(["single", "sealed"]).default("single"),
  category: z.string().min(1).max(40).default("card"),
  setCode: z.string().min(1).max(40),
  setName: z.string().min(1).max(200),
  cardNumber: z.string().max(40).nullable().default(null),
  cardName: z.string().min(1).max(200),
  language: z.string().min(2).max(10).default("en"),
  edition: z.string().max(60).nullable().default(null),
  variant: z.string().max(60).nullable().default(null),
  rarity: z.string().max(60).nullable().default(null),
  externalRefs: z.record(z.string()).default({}),
});

export async function upsertIdentity(db: import("../db.js").Queryable, b: z.infer<typeof identitySchema>, userId: string) {
  const existing = await one<{ id: string }>(
    db,
    `SELECT id FROM card_identities WHERE game = $1 AND product_type = $2 AND set_code = $3 AND coalesce(card_number,'') = coalesce($4,'')
       AND language = $5 AND coalesce(edition,'') = coalesce($6,'') AND coalesce(variant,'') = coalesce($7,'') AND card_name = $8`,
    [b.game, b.productType, b.setCode, b.cardNumber, b.language, b.edition, b.variant, b.cardName],
  );
  if (existing) return { id: existing.id, created: false };
  const row = await one<{ id: string }>(
    db,
    `INSERT INTO card_identities (game, product_type, category, set_code, set_name, card_number, card_name, language, edition, variant, rarity, external_refs, created_by)
     VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) RETURNING id`,
    [b.game, b.productType, b.category, b.setCode, b.setName, b.cardNumber, b.cardName, b.language, b.edition, b.variant, b.rarity, JSON.stringify(b.externalRefs), userId],
  );
  await audit(db, userId, "card_identity.created", "card_identity", row!.id, b);
  return { id: row!.id, created: true };
}

export async function catalogRoutes(app: FastifyInstance, ctx: AppContext) {
  app.get("/api/catalog/search", async (req) => {
    user(req);
    const q = parse(
      z.object({ q: z.string().max(200).default(""), game: z.string().optional(), limit: z.coerce.number().int().min(1).max(100).default(30) }),
      req.query,
    );
    const terms = q.q.trim();
    return many(
      ctx.pool,
      `SELECT * FROM card_identities
       WHERE ($1 = '' OR card_name ILIKE '%' || $1 || '%' OR set_name ILIKE '%' || $1 || '%' OR set_code ILIKE $1 || '%'
              OR card_number ILIKE $1 || '%')
         AND ($2::text IS NULL OR game = $2)
       ORDER BY card_name, set_name LIMIT $3`,
      [terms, q.game ?? null, q.limit],
    );
  });

  app.post("/api/catalog/cards", async (req, reply) => {
    const u = user(req);
    const body = parse(identitySchema, req.body);
    const result = await upsertIdentity(ctx.pool, body, u.id);
    const row = await one(ctx.pool, `SELECT * FROM card_identities WHERE id = $1`, [result.id]);
    return reply.code(result.created ? 201 : 200).send(row);
  });

  // Link a catalogue entry to an external source's ID (e.g. {"poketrace": "<card uuid>"}). Audited; merges keys.
  app.patch("/api/catalog/cards/:id/external-refs", async (req) => {
    const u = user(req);
    const { id } = parse(z.object({ id: z.string().uuid() }), req.params);
    const refs = parse(z.record(z.string().min(1).max(200)), req.body);
    const row = await one<{ external_refs: Record<string, string> }>(ctx.pool, `SELECT external_refs FROM card_identities WHERE id = $1`, [id]);
    if (!row) throw badRequest("Unknown card identity");
    const updated = await one(
      ctx.pool,
      `UPDATE card_identities SET external_refs = external_refs || $2::jsonb WHERE id = $1 RETURNING *`,
      [id, JSON.stringify(refs)],
    );
    await audit(ctx.pool, u.id, "card_identity.external_refs_set", "card_identity", id, { previous: row.external_refs, set: refs }, req.id);
    return updated;
  });

  app.get("/api/catalog/remote", async (req) => {
    user(req);
    const q = parse(z.object({ source: z.string().default("tcgdex"), q: z.string().min(2), language: z.string().default("en") }), req.query);
    const adapter = ctx.sources.get(q.source);
    if (!adapter?.searchCatalog || !adapter.enabled()) throw badRequest(`Source ${q.source} does not offer an enabled catalogue`);
    try {
      return await adapter.searchCatalog(q.q, q.language);
    } catch (error) {
      throw new HttpError(502, `Catalogue source error: ${(error as Error).message}`, "upstream_error");
    }
  });

  app.post("/api/catalog/import", async (req, reply) => {
    const u = user(req);
    const body = parse(
      z.object({
        source: z.string().default("tcgdex"),
        externalId: z.string().min(1),
        language: z.string().default("en"),
        edition: z.string().nullable().default(null),
        variant: z.string().nullable().default(null),
      }),
      req.body,
    );
    const adapter = ctx.sources.get(body.source);
    if (!adapter?.getCatalogItem || !adapter.enabled()) throw badRequest(`Source ${body.source} does not offer an enabled catalogue`);
    let item;
    try {
      item = await adapter.getCatalogItem(body.externalId, body.language);
    } catch (error) {
      throw new HttpError(502, `Catalogue source error: ${(error as Error).message}`, "upstream_error");
    }
    const c = item.candidate;
    const identity = await upsertIdentity(
      ctx.pool,
      {
        game: c.game as "pokemon",
        productType: c.productType,
        category: c.category,
        setCode: c.setCode,
        setName: c.setName,
        cardNumber: c.cardNumber,
        cardName: c.cardName,
        language: c.language,
        edition: body.edition,
        variant: body.variant ?? (c.variants[0] ?? null),
        rarity: c.rarity,
        externalRefs: { [c.source]: c.externalId },
      },
      u.id,
    );
    for (const o of item.priceGuide) {
      await ctx.pool.query(
        `INSERT INTO price_observations (source_id, source_reference, source_url, card_identity_id, observation_kind, grading_company, grade,
           condition, observed_at, venue, amount_minor, currency, buyers_premium_minor, arms_length, verification_status, verification_notes,
           fetched_at, raw_payload, ingested_by)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,now(),$17,$18)
         ON CONFLICT (source_id, source_reference) DO NOTHING`,
        [adapter.id, o.sourceReference, o.sourceUrl, identity.id, o.kind, o.gradingCompany, o.grade, o.condition, o.observedAt, o.venue,
          o.amountMinor, o.currency, o.buyersPremiumMinor, o.armsLength, o.verificationStatus, o.verificationNotes, JSON.stringify(o.raw), u.id],
      );
    }
    const row = await one(ctx.pool, `SELECT * FROM card_identities WHERE id = $1`, [identity.id]);
    return reply.code(identity.created ? 201 : 200).send({ identity: row, imageUrl: c.imageUrl, availableVariants: c.variants });
  });
}
