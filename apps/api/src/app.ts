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
import { createRegistry, type SourceRegistry } from "./sources/registry.js";

export async function buildApp(opts: { config: Config; pool: Db; sources?: SourceRegistry; logger?: boolean }): Promise<FastifyInstance> {
  const app = Fastify({ logger: opts.logger ?? false, bodyLimit: 5 * 1024 * 1024 });
  const ctx: AppContext = {
    config: opts.config,
    pool: opts.pool,
    tokens: new TokenService(opts.config.jwtSecret),
    sources: opts.sources ?? createRegistry(opts.config),
  };

  await app.register(multipart, { limits: { fileSize: 15 * 1024 * 1024, files: 1 } });

  app.addHook("onRequest", async (req) => {
    const header = req.headers.authorization;
    if (header?.startsWith("Bearer ")) {
      try {
        req.user = await ctx.tokens.verify(header.slice(7));
      } catch {
        throw new HttpError(401, "Invalid or expired token", "unauthorized");
      }
    }
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
