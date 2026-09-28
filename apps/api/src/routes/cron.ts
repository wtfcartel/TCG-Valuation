import { timingSafeEqual } from "node:crypto";
import type { FastifyInstance, FastifyRequest } from "fastify";
import { audit } from "../audit.js";
import { HttpError } from "../errors.js";
import { ECB_SOURCE, importEcbRates } from "../services/ecb.js";
import type { AppContext } from "./context.js";

/** Scheduled jobs for serverless hosting (Vercel Cron). Replaces the in-process timer used by server.ts. */
export async function cronRoutes(app: FastifyInstance, ctx: AppContext) {
  const authorise = (req: FastifyRequest) => {
    const secret = ctx.config.cronSecret;
    const header = req.headers.authorization ?? "";
    const expected = `Bearer ${secret}`;
    if (!secret || header.length !== expected.length || !timingSafeEqual(Buffer.from(header), Buffer.from(expected))) {
      throw new HttpError(401, "Unauthorized", "unauthorized");
    }
  };

  app.get("/api/cron/ecb", async (req) => {
    authorise(req);
    const existing = await ctx.pool.query(`SELECT 1 FROM fx_rates WHERE source = $1 LIMIT 1`, [ECB_SOURCE]);
    let result;
    try {
      result = await importEcbRates(ctx.pool, existing.rowCount ? "daily" : "last90Days");
    } catch (error) {
      throw new HttpError(502, `ECB import failed: ${(error as Error).message}`, "upstream_error");
    }
    await audit(ctx.pool, null, "fx_rate.ecb_imported", "fx_rate", result.feed, { ...result, trigger: "cron" }, req.id);
    return result;
  });
}
