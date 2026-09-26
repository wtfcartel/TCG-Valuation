import { createHash, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { audit } from "../audit.js";
import { many, one, withTx } from "../db.js";
import { badRequest, HttpError, notFound } from "../errors.js";
import { parseCsv, storeObservations } from "../services/evidence.js";
import { appendInsuranceEvent, onAssetExit, scheduledValues } from "../services/insurance.js";
import { getAsset, gradingAt, heldQuantity, type GradingRow, type OwnershipRow } from "../services/ledger.js";
import { getValuation, loadObservations, runValuation, today } from "../services/valuation.js";
import type { SourcedObservation } from "../sources/types.js";
import { SourceNotConfiguredError, type CardIdentityRow } from "../sources/types.js";
import { ebayPageToObservations } from "../sources/ebay-sold.js";
import { assertAssetAccess, currency, isoDate, minor, parse, user, uuid, type AppContext } from "./context.js";

const idParams = z.object({ id: uuid });

const exitSchema = z.object({
  effectiveDate: isoDate,
  quantity: z.number().int().min(1).default(1),
  proceedsMinor: minor.nullable().default(null),
  currency: currency.nullable().default(null),
  counterparty: z.string().max(200).nullable().default(null),
  reason: z.string().max(1000).nullable().default(null),
});

const manualEvidenceSchema = z.object({
  kind: z.enum(["completed_sale", "asking_price"]).default("completed_sale"),
  observedAt: isoDate,
  venue: z.string().min(1).max(200),
  amountMinor: minor,
  currency,
  buyersPremiumMinor: minor.default(0),
  sourceReference: z.string().min(1).max(300),
  sourceUrl: z.string().url().max(2000).nullable().default(null),
  gradingCompany: z.string().max(40).nullable().default(null),
  grade: z.string().max(20).nullable().default(null),
  condition: z.string().max(40).nullable().default(null),
  armsLength: z.boolean().nullable().default(true),
  verified: z.boolean().default(false),
  verificationNotes: z.string().max(1000).nullable().default(null),
});

/** Ensure a new exit event never drives the held quantity negative on any later date. */
function assertQuantityAvailable(events: OwnershipRow[], effectiveDate: string, quantity: number): number {
  const heldBefore = heldQuantity(events, effectiveDate);
  const checkpoints = [effectiveDate, ...events.map((e) => e.effective_date).filter((d) => d > effectiveDate)];
  for (const d of checkpoints) {
    if (heldQuantity(events, d) - quantity < 0) {
      throw badRequest(`Only ${heldQuantity(events, d)} unit(s) held on ${d}; cannot remove ${quantity}`);
    }
  }
  return heldBefore;
}

export async function assetRoutes(app: FastifyInstance, ctx: AppContext) {
  app.get("/api/assets/:id", async (req) => {
    const u = user(req);
    const { id } = parse(idParams, req.params);
    await assertAssetAccess(ctx.pool, u, id);
    const asset = await getAsset(ctx.pool, id);
    const [gradings, ownership, valuations, photos, insurance] = await Promise.all([
      many<GradingRow>(ctx.pool, `SELECT * FROM grading_records WHERE asset_id = $1 ORDER BY effective_date, recorded_at`, [id]),
      many<OwnershipRow>(ctx.pool, `SELECT * FROM ownership_events WHERE asset_id = $1 ORDER BY effective_date, recorded_at`, [id]),
      many(
        ctx.pool,
        `SELECT id, purpose, valuation_date, status, unit_value_minor, effective_unit_value_minor, override_id, total_value_minor,
                effective_total_value_minor, quantity, confidence, method_used, escalated, lower_confidence, dispersion_pct,
                methodology_version_id, performed_at, flags
         FROM valuations_effective WHERE asset_id = $1 ORDER BY performed_at DESC`,
        [id],
      ),
      many(ctx.pool, `SELECT id, content_type, byte_size, sha256, caption, uploaded_at FROM asset_photos WHERE asset_id = $1 ORDER BY uploaded_at`, [id]),
      many(
        ctx.pool,
        `SELECT e.schedule_id, e.seq, e.event_type, e.effective_date, l.change, l.quantity, l.previous_value_minor, l.new_value_minor, l.valuation_id
         FROM insurance_event_lines l JOIN insurance_events e ON e.id = l.event_id WHERE l.asset_id = $1 ORDER BY e.seq`,
        [id],
      ),
    ]);
    const now = today();
    const grading = gradingAt(gradings, now);
    const held = heldQuantity(ownership, now);
    const lastInsurance = insurance[insurance.length - 1] as { change: string; new_value_minor: number } | undefined;
    const disposals = ownership.filter((e) => e.event_type === "disposal");
    return {
      ...asset,
      current: {
        heldQuantity: held,
        status: held > 0 ? "held" : ownership.some((e) => e.event_type === "loss") ? "lost" : "disposed",
        grading,
        insuranceStatus: !lastInsurance ? "not_scheduled" : lastInsurance.change === "removed" ? "removed" : "insured",
        insuredValueMinor: lastInsurance && lastInsurance.change !== "removed" ? lastInsurance.new_value_minor : 0,
        disposalDate: held === 0 ? (disposals[disposals.length - 1]?.effective_date ?? null) : null,
        disposalPriceMinor: held === 0 ? (disposals[disposals.length - 1]?.amount_minor ?? null) : null,
      },
      gradingHistory: gradings,
      ownershipEvents: ownership,
      valuations,
      photos,
      insuranceHistory: insurance,
    };
  });

  app.post("/api/assets/:id/grading", async (req, reply) => {
    const u = user(req);
    const { id } = parse(idParams, req.params);
    await assertAssetAccess(ctx.pool, u, id);
    const b = parse(
      z
        .object({
          effectiveDate: isoDate,
          gradingCompany: z.string().max(40).nullable(),
          certNumber: z.string().max(60).nullable().default(null),
          grade: z.string().max(20).nullable(),
          condition: z.string().max(40).nullable().default(null),
          reason: z.enum(["graded", "regraded", "cracked", "correction", "condition_change"]),
        })
        .refine((x) => (x.gradingCompany == null) === (x.grade == null), { message: "gradingCompany and grade must be given together" }),
      req.body,
    );
    if (b.effectiveDate > today()) throw badRequest("Effective date cannot be in the future");
    const asset = await getAsset(ctx.pool, id);
    const record = await one(
      ctx.pool,
      `INSERT INTO grading_records (asset_id, grading_company, cert_number, grade, condition, effective_date, reason, recorded_by)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *`,
      [id, b.gradingCompany, b.certNumber, b.grade, b.condition, b.effectiveDate, b.reason, u.id],
    );
    await audit(ctx.pool, u.id, "asset.grading_changed", "asset", id, b, req.id);

    // A grading change alters what the asset is; re-value for insurance and record a Grading Change event.
    const schedules = await many<{ id: string }>(ctx.pool, `SELECT id FROM insurance_schedules WHERE collection_id = $1`, [asset.collection_id]);
    const insuranceEvents = [];
    for (const s of schedules) {
      const existing = (await scheduledValues(ctx.pool, s.id)).get(id);
      if (!existing) continue;
      const { id: valuationId, result } = await runValuation(ctx.pool, { assetId: id, purpose: "insurance_replacement", userId: u.id, requestId: req.id });
      const newValue = result.totalValueMinor ?? existing.value;
      insuranceEvents.push(
        await withTx(ctx.pool, (tx) =>
          appendInsuranceEvent(tx, s.id, {
            type: "grading_change",
            effectiveDate: b.effectiveDate,
            reason:
              `Grading change on ${asset.asset_ref}: ${b.gradingCompany ? `${b.gradingCompany} ${b.grade}` : "raw"} (${b.reason})` +
              (result.totalValueMinor == null ? "; insufficient evidence to revalue, previous value retained" : ""),
            lines: [{ assetId: id, change: "revalued", quantity: existing.quantity, previousValueMinor: existing.value, newValueMinor: newValue, valuationId }],
            userId: u.id,
            requestId: req.id,
          }),
        ),
      );
    }
    return reply.code(201).send({ record, insuranceEvents });
  });

  for (const kind of ["disposals", "losses"] as const) {
    app.post(`/api/assets/:id/${kind}`, async (req, reply) => {
      const u = user(req);
      const { id } = parse(idParams, req.params);
      await assertAssetAccess(ctx.pool, u, id);
      const b = parse(exitSchema, req.body);
      if (b.effectiveDate > today()) throw badRequest("Effective date cannot be in the future");
      if ((b.proceedsMinor == null) !== (b.currency == null)) throw badRequest("proceedsMinor and currency must be given together");
      if (kind === "disposals" && b.proceedsMinor == null) throw badRequest("A disposal requires proceedsMinor and currency");
      const asset = await getAsset(ctx.pool, id);
      const result = await withTx(ctx.pool, async (tx) => {
        await tx.query(`SELECT id FROM collections WHERE id = $1 FOR UPDATE`, [asset.collection_id]);
        const events = await many<OwnershipRow>(tx, `SELECT * FROM ownership_events WHERE asset_id = $1`, [id]);
        const heldBefore = assertQuantityAvailable(events, b.effectiveDate, b.quantity);
        const event = await one(
          tx,
          `INSERT INTO ownership_events (asset_id, event_type, effective_date, quantity, amount_minor, currency, counterparty, reason, recorded_by)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *`,
          [id, kind === "disposals" ? "disposal" : "loss", b.effectiveDate, b.quantity, b.proceedsMinor, b.currency, b.counterparty, b.reason, u.id],
        );
        await audit(tx, u.id, kind === "disposals" ? "asset.disposed" : "asset.lost", "asset", id, b, req.id);
        const insuranceEvents = await onAssetExit(tx, {
          assetId: id,
          assetRef: asset.asset_ref,
          collectionId: asset.collection_id,
          heldBefore,
          quantityOut: b.quantity,
          effectiveDate: b.effectiveDate,
          type: kind === "disposals" ? "disposal" : "loss_damage",
          userId: u.id,
          requestId: req.id,
        });
        return { event, insuranceEvents };
      });
      return reply.code(201).send(result);
    });
  }

  app.post("/api/assets/:id/photos", async (req, reply) => {
    const u = user(req);
    const { id } = parse(idParams, req.params);
    await assertAssetAccess(ctx.pool, u, id);
    const file = await req.file();
    if (!file) throw badRequest("Expected a multipart file field");
    if (!["image/jpeg", "image/png", "image/webp", "image/heic"].includes(file.mimetype)) throw badRequest("Unsupported image type");
    const buffer = await file.toBuffer();
    const storageKey = `${id}/${randomUUID()}`;
    await mkdir(join(ctx.config.photoStorageDir, id), { recursive: true });
    await writeFile(join(ctx.config.photoStorageDir, storageKey), buffer);
    const sha256 = createHash("sha256").update(buffer).digest("hex");
    const caption = (file.fields.caption as { value?: string } | undefined)?.value ?? null;
    const row = await one(
      ctx.pool,
      `INSERT INTO asset_photos (asset_id, storage_key, content_type, byte_size, sha256, caption, uploaded_by)
       VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id, content_type, byte_size, sha256, caption, uploaded_at`,
      [id, storageKey, file.mimetype, buffer.length, sha256, caption, u.id],
    );
    await audit(ctx.pool, u.id, "asset.photo_added", "asset", id, { sha256, bytes: buffer.length }, req.id);
    return reply.code(201).send(row);
  });

  app.get("/api/photos/:id", async (req, reply) => {
    const u = user(req);
    const { id } = parse(idParams, req.params);
    const photo = await one<{ asset_id: string; storage_key: string; content_type: string }>(
      ctx.pool,
      `SELECT asset_id, storage_key, content_type FROM asset_photos WHERE id = $1`,
      [id],
    );
    if (!photo) throw notFound("Photo");
    await assertAssetAccess(ctx.pool, u, photo.asset_id);
    return reply.type(photo.content_type).send(createReadStream(join(ctx.config.photoStorageDir, photo.storage_key)));
  });

  // ───────────── Evidence (market-data layer) ─────────────

  app.get("/api/assets/:id/evidence", async (req) => {
    const u = user(req);
    const { id } = parse(idParams, req.params);
    await assertAssetAccess(ctx.pool, u, id);
    const asset = await getAsset(ctx.pool, id);
    return loadObservations(ctx.pool, asset.card_identity_id, asset.owner_user_id);
  });

  app.post("/api/assets/:id/evidence/import", async (req, reply) => {
    const u = user(req);
    const { id } = parse(idParams, req.params);
    await assertAssetAccess(ctx.pool, u, id);
    const b = parse(z.object({ sourceId: z.string().min(1) }), req.body);
    const adapter = ctx.sources.get(b.sourceId);
    if (!adapter?.fetchEvidence) throw badRequest(`Source ${b.sourceId} cannot supply evidence automatically`);
    if (!adapter.enabled()) throw new HttpError(422, `Source ${b.sourceId} is not enabled (licence/configuration required)`, "source_disabled");
    const asset = await getAsset(ctx.pool, id);
    const grading = gradingAt(await many<GradingRow>(ctx.pool, `SELECT * FROM grading_records WHERE asset_id = $1`, [id]), today());
    const identity = await one<import("../sources/types.js").CardIdentityRow>(ctx.pool, `SELECT * FROM card_identities WHERE id = $1`, [asset.card_identity_id]);
    let observations: SourcedObservation[];
    try {
      observations = await adapter.fetchEvidence({
        identity: identity!,
        gradingCompany: grading?.grading_company ?? null,
        grade: grading?.grade ?? null,
        condition: grading?.condition ?? null,
        asOf: today(),
      });
    } catch (error) {
      if (error instanceof SourceNotConfiguredError) throw new HttpError(422, error.message, "source_disabled");
      throw new HttpError(502, `Evidence source error: ${(error as Error).message}`, "upstream_error");
    }
    const stored = await storeObservations(ctx.pool, adapter.id, asset.card_identity_id, observations, u.id);
    await audit(ctx.pool, u.id, "evidence.imported", "asset", id, { sourceId: adapter.id, ...stored }, req.id);
    return reply.code(201).send({ sourceId: adapter.id, fetched: observations.length, ...stored });
  });

  app.post("/api/assets/:id/evidence", async (req, reply) => {
    const u = user(req);
    const { id } = parse(idParams, req.params);
    await assertAssetAccess(ctx.pool, u, id);
    const b = parse(manualEvidenceSchema, req.body);
    if (b.verified && !b.sourceUrl) throw badRequest("A verified sale requires a source URL");
    if (b.kind === "asking_price" && b.verified) throw badRequest("An asking price cannot be marked as a verified sale");
    const asset = await getAsset(ctx.pool, id);
    const obs: SourcedObservation = {
      sourceReference: b.sourceReference,
      sourceUrl: b.sourceUrl,
      kind: b.kind,
      gradingCompany: b.gradingCompany,
      grade: b.grade,
      condition: b.condition,
      observedAt: b.observedAt,
      venue: b.venue,
      amountMinor: b.amountMinor,
      currency: b.currency,
      buyersPremiumMinor: b.buyersPremiumMinor,
      armsLength: b.kind === "asking_price" ? null : b.armsLength,
      verificationStatus: b.verified ? "verified" : "unverified",
      verificationNotes: b.verificationNotes ?? (b.verified ? `Verified by ${u.email} against source URL` : null),
      raw: { enteredBy: u.id, entry: "manual" },
    };
    const stored = await storeObservations(ctx.pool, "manual", asset.card_identity_id, [obs], u.id);
    if (stored.inserted === 0) throw new HttpError(409, "Evidence with this source reference already exists", "conflict");
    await audit(ctx.pool, u.id, "evidence.recorded", "asset", id, b, req.id);
    return reply.code(201).send(stored);
  });

  app.post("/api/assets/:id/evidence/csv", async (req, reply) => {
    const u = user(req);
    const { id } = parse(idParams, req.params);
    await assertAssetAccess(ctx.pool, u, id);
    const b = parse(z.object({ csv: z.string().min(1).max(2_000_000) }), req.body);
    const asset = await getAsset(ctx.pool, id);
    const rows = parseCsv(b.csv);
    const required = ["sale_date", "venue", "amount", "currency", "source_reference"];
    const errors: string[] = [];
    const observations: SourcedObservation[] = [];
    rows.forEach((r, i) => {
      const missing = required.filter((k) => !r[k]);
      const amount = Number(r.amount);
      const premium = r.buyers_premium ? Number(r.buyers_premium) : 0;
      if (missing.length || !/^\d{4}-\d{2}-\d{2}$/.test(r.sale_date ?? "") || !Number.isFinite(amount) || !Number.isFinite(premium)) {
        errors.push(`row ${i + 2}: ${missing.length ? `missing ${missing.join(", ")}` : "invalid date or amount"}`);
        return;
      }
      observations.push({
        sourceReference: r.source_reference!,
        sourceUrl: r.source_url || null,
        kind: "completed_sale",
        gradingCompany: r.grading_company || null,
        grade: r.grade || null,
        condition: r.condition || null,
        observedAt: r.sale_date!,
        venue: r.venue!,
        amountMinor: Math.round(amount * 100),
        currency: r.currency!.toUpperCase(),
        buyersPremiumMinor: Math.round(premium * 100),
        armsLength: r.arms_length ? ["1", "true", "yes", "y"].includes(r.arms_length.toLowerCase()) : null,
        verificationStatus: ["1", "true", "yes", "y"].includes((r.verified ?? "").toLowerCase()) ? "verified" : "unverified",
        verificationNotes: r.notes || null,
        raw: r,
      });
    });
    if (errors.length) throw badRequest(`CSV rejected: ${errors.slice(0, 10).join("; ")}`);
    const stored = await storeObservations(ctx.pool, "csv_import", asset.card_identity_id, observations, u.id);
    await audit(ctx.pool, u.id, "evidence.csv_imported", "asset", id, { rows: rows.length, ...stored }, req.id);
    return reply.code(201).send({ rows: rows.length, ...stored });
  });

  // Saved eBay "Sold items" result page (HTML) → UNLICENSED/SCRAPED completed-sale evidence.
  app.post("/api/assets/:id/evidence/ebay-page", async (req, reply) => {
    const u = user(req);
    const { id } = parse(idParams, req.params);
    await assertAssetAccess(ctx.pool, u, id);
    const b = parse(
      z.object({
        html: z.string().min(100).max(8_000_000),
        site: z.enum(["ebay.com", "ebay.com.au", "ebay.co.uk", "ebay.ca", "ebay.de"]).default("ebay.com"),
      }),
      req.body,
    );
    const fallbackCurrency = { "ebay.com": "USD", "ebay.com.au": "AUD", "ebay.co.uk": "GBP", "ebay.ca": "CAD", "ebay.de": "EUR" }[b.site];
    const asset = await getAsset(ctx.pool, id);
    const identity = await one<CardIdentityRow>(ctx.pool, `SELECT * FROM card_identities WHERE id = $1`, [asset.card_identity_id]);
    const parsed = ebayPageToObservations(b.html, identity!, { site: b.site, fallbackCurrency });
    if (parsed.listingsFound === 0) throw badRequest("No eBay result listings found in this page. Save the full 'Sold items' search results page.");
    const stored = await storeObservations(ctx.pool, "ebay_sold_scrape", asset.card_identity_id, parsed.observations, u.id);
    const bestOffer = parsed.observations.filter((o) => o.verificationStatus === "unverified").length;
    await audit(ctx.pool, u.id, "evidence.ebay_page_imported", "asset", id, { site: b.site, listingsFound: parsed.listingsFound, matched: parsed.observations.length, skipped: parsed.skipped, ...stored }, req.id);
    return reply.code(201).send({
      licenceStatus: "unlicensed",
      listingsFound: parsed.listingsFound,
      matched: parsed.observations.length,
      bestOfferAcceptedRejected: bestOffer,
      skipped: parsed.skipped,
      ...stored,
    });
  });

  // ───────────── Valuations ─────────────

  app.post("/api/assets/:id/valuations", async (req, reply) => {
    const u = user(req);
    const { id } = parse(idParams, req.params);
    await assertAssetAccess(ctx.pool, u, id);
    const b = parse(
      z.object({
        purpose: z.enum(["market", "insurance_replacement", "historical"]).default("market"),
        valuationDate: isoDate.optional(),
        exclusions: z.array(z.object({ observationId: uuid, reason: z.string().min(5).max(1000) })).default([]),
        supersedesValuationId: uuid.nullable().default(null),
      }),
      req.body ?? {},
    );
    if (b.purpose === "historical" && !b.valuationDate) throw badRequest("A historical valuation requires valuationDate");
    const { id: valuationId } = await runValuation(ctx.pool, {
      assetId: id,
      purpose: b.purpose,
      valuationDate: b.valuationDate,
      exclusions: b.exclusions,
      supersedesValuationId: b.supersedesValuationId,
      userId: u.id,
      requestId: req.id,
    });
    return reply.code(201).send(await getValuation(ctx.pool, valuationId));
  });
}
