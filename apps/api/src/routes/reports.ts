import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { many } from "../db.js";
import { forbidden } from "../errors.js";
import { renderInsuranceReport, renderValuationReport } from "../pdf/render.js";
import { generateInsuranceAdjustmentReport, generateValuationReport, getReport } from "../services/reports.js";
import { assertCollectionAccess, assertScheduleAccess, canAccess, parse, user, uuid, type AppContext } from "./context.js";

export async function reportRoutes(app: FastifyInstance, ctx: AppContext) {
  app.get("/api/collections/:id/reports", async (req) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    await assertCollectionAccess(ctx.pool, u, id);
    return many(
      ctx.pool,
      `SELECT id, report_type, version, schema_version, payload_sha256, schedule_id, generated_at FROM reports WHERE collection_id = $1 ORDER BY generated_at DESC`,
      [id],
    );
  });

  app.post("/api/collections/:id/reports/valuation", async (req, reply) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    await assertCollectionAccess(ctx.pool, u, id);
    const b = parse(z.object({ purpose: z.enum(["market", "insurance_replacement"]).default("market") }), req.body ?? {});
    return reply.code(201).send(await generateValuationReport(ctx.pool, { collectionId: id, purpose: b.purpose, userId: u.id, requestId: req.id }));
  });

  app.post("/api/schedules/:id/reports/adjustment", async (req, reply) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    await assertScheduleAccess(ctx.pool, u, id);
    const b = parse(z.object({ fromSeq: z.number().int().min(1).optional() }), req.body ?? {});
    return reply.code(201).send(await generateInsuranceAdjustmentReport(ctx.pool, { scheduleId: id, fromSeq: b.fromSeq, userId: u.id, requestId: req.id }));
  });

  /** The insurer-facing JSON payload (API integration surface). */
  app.get("/api/reports/:id", async (req) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    const report = await getReport(ctx.pool, id);
    if (!canAccess(u, report.owner_user_id)) throw forbidden();
    const { owner_user_id: _owner, ...rest } = report;
    return rest;
  });

  app.get("/api/reports/:id/pdf", async (req, reply) => {
    const u = user(req);
    const { id } = parse(z.object({ id: uuid }), req.params);
    const report = await getReport(ctx.pool, id);
    if (!canAccess(u, report.owner_user_id)) throw forbidden();
    const meta = { sha256: report.payload_sha256, generatedAt: report.generated_at };
    const pdf =
      report.report_type === "valuation" ? await renderValuationReport(report.payload, meta) : await renderInsuranceReport(report.payload, meta);
    return reply
      .type("application/pdf")
      .header("content-disposition", `attachment; filename="cardcore-${report.report_type}-v${report.version}.pdf"`)
      .send(pdf);
  });
}
