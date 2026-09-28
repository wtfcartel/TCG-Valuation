import { existsSync } from "node:fs";
import { resolve } from "node:path";
import Fastify, { type FastifyInstance } from "fastify";
import multipart from "@fastify/multipart";
import fastifyStatic from "@fastify/static";
import { TokenService } from "./auth.js";
import type { Config } from "./config.js";
import type { Db } from "./db.js";
import { HttpError } from "./errors.js";
import { assetRoutes } from "./routes/assets.js";
import { authRoutes } from "./routes/auth.js";
import { catalogRoutes } from "./routes/catalog.js";
import { collectionRoutes } from "./routes/collections.js";
import type { AppContext } from "./routes/context.js";
import { insuranceRoutes } from "./routes/insurance.js";
import { reportRoutes } from "./routes/reports.js";
import { valuationRoutes } from "./routes/valuations.js";
import { adminRoutes } from "./routes/admin.js";
import { createRegistry, type SourceRegistry } from "./sources/registry.js";
import { createPhotoStore } from "./services/photo-store.js";
import { cronRoutes } from "./routes/cron.js";

export async function buildApp(opts: { config: Config; pool: Db; sources?: SourceRegistry; logger?: boolean; trustProxy?: boolean }): Promise<FastifyInstance> {
  // trustProxy: behind a hosting provider's load balancer, req.ip must come from X-Forwarded-For for rate limiting.
  const app = Fastify({ logger: opts.logger ?? false, bodyLimit: process.env.VERCEL ? 4 * 1024 * 1024 : 10 * 1024 * 1024, trustProxy: opts.trustProxy ?? false });
  const ctx: AppContext = {
    config: opts.config,
    pool: opts.pool,
    tokens: new TokenService(opts.config.jwtSecret),
    sources: opts.sources ?? createRegistry(opts.config),
    photos: createPhotoStore(opts.config),
  };

  await app.register(multipart, { limits: { fileSize: 15 * 1024 * 1024, files: 1 } });

  app.addHook("onRequest", async (req) => {
    const header = req.headers.authorization;
    // Cron routes authenticate with CRON_SECRET in the same header (Vercel Cron), not a user session.
    if (req.url.startsWith("/api/cron/")) return;
    if (header?.startsWith("Bearer ")) {
      let claims;
      try {
        claims = await ctx.tokens.verify(header.slice(7));
      } catch {
        throw new HttpError(401, "Invalid or expired token", "unauthorized");
      }
      // The database is authoritative: role changes apply immediately, and a password change/reset
      // (which bumps session_version) revokes every earlier session.
      const row = await ctx.pool.query<{ role: "collector" | "valuer" | "admin"; session_version: number }>(
        `SELECT role, session_version FROM users WHERE id = $1`,
        [claims.id],
      );
      const u = row.rows[0];
      if (!u || claims.sessionVersion !== u.session_version) throw new HttpError(401, "Session expired; please sign in again", "unauthorized");
      req.user = { id: claims.id, email: claims.email, role: u.role };
    }
  });

  app.addHook("onSend", async (req, reply) => {
    reply.header("X-Content-Type-Options", "nosniff");
    reply.header("X-Frame-Options", "DENY");
    reply.header("Referrer-Policy", "no-referrer");
    reply.header("Permissions-Policy", "camera=(self), geolocation=(), microphone=()");
    reply.header(
      "Content-Security-Policy",
      "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    );
    if (process.env.NODE_ENV === "production") reply.header("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
    if (req.url.startsWith("/api/")) reply.header("Cache-Control", "no-store");
  });

  app.setErrorHandler((error: Error, req, reply) => {
    if (error instanceof HttpError) {
      return reply.code(error.statusCode).send({ error: error.code, message: error.message });
    }
    const pgCode = (error as { code?: string }).code;
    if (pgCode === "23000" || pgCode === "23505" || pgCode === "23514") {
      return reply.code(409).send({ error: "conflict", message: error.message });
    }
    const statusCode = (error as Error & { statusCode?: number }).statusCode;
    if (statusCode && statusCode < 500) {
      return reply.code(statusCode).send({ error: "bad_request", message: error.message });
    }
    req.log.error(error);
    return reply.code(500).send({ error: "internal", message: "Internal server error" });
  });

  app.get("/api/health", async () => {
    await ctx.pool.query("SELECT 1");
    return { status: "ok" };
  });

  await authRoutes(app, ctx);
  await catalogRoutes(app, ctx);
  await collectionRoutes(app, ctx);
  await assetRoutes(app, ctx);
  await valuationRoutes(app, ctx);
  await insuranceRoutes(app, ctx);
  await reportRoutes(app, ctx);
  await adminRoutes(app, ctx);
  await cronRoutes(app, ctx);

  const webDir = opts.config.webDistDir ? resolve(opts.config.webDistDir) : null;
  if (webDir && existsSync(webDir)) {
    await app.register(fastifyStatic, { root: webDir, wildcard: false });
    app.setNotFoundHandler((req, reply) => {
      if (req.url.startsWith("/api/")) return reply.code(404).send({ error: "not_found", message: "Route not found" });
      return reply.sendFile("index.html");
    });
  }
  return app;
}
