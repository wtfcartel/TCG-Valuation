/**
 * Vercel entry (bundled to dist/vercel-app.js by `npm run build:vercel`): the whole Fastify API runs as
 * one Vercel Function, and the React PWA is served from Vercel's CDN. Local and Docker deployments use
 * server.ts instead.
 */
import type { IncomingMessage, ServerResponse } from "node:http";
import type { FastifyInstance } from "fastify";
import { buildApp } from "./app.js";
import { loadConfig } from "./config.js";
import { createPool, migrate } from "./db.js";

let ready: Promise<FastifyInstance> | null = null;

async function init(): Promise<FastifyInstance> {
  const config = loadConfig();
  const pool = createPool(config.databaseUrl);
  // Idempotent and lock-protected, so concurrent cold starts are safe.
  await migrate(pool, config);
  const app = await buildApp({ config: { ...config, webDistDir: null }, pool, logger: true, trustProxy: true });
  await app.ready();
  return app;
}

export default async function handler(req: IncomingMessage, res: ServerResponse): Promise<void> {
  ready ??= init().catch((error) => {
    ready = null; // retry initialisation on the next request
    throw error;
  });
  const app = await ready;
  app.server.emit("request", req, res);
}
