/**
 * Vercel entry (bundled to dist/vercel-app.js by `npm run build:vercel`): the whole Fastify API runs as
 * one Vercel Function, and the React PWA is served from Vercel's CDN. Local and Docker deployments use
 * server.ts instead.
 */
import type { IncomingMessage, ServerResponse } from "node:http";
import type { FastifyInstance } from "fastify";
import { buildApp } from "./app.js";
import { loadConfig, StartupError } from "./config.js";
import { createPool, migrate } from "./db.js";

let ready: Promise<FastifyInstance> | null = null;

async function init(): Promise<FastifyInstance> {
  const config = loadConfig();
  if (!config.databaseUrl) {
    throw new StartupError("No database is configured: DATABASE_URL is not set. Connect a Neon database in Vercel → Storage, then redeploy.");
  }
  const pool = createPool(config.databaseUrl);
  // Idempotent and lock-protected, so concurrent cold starts are safe.
  try {
    await migrate(pool, config);
  } catch (error) {
    await pool.end().catch(() => undefined);
    throw new StartupError(`Could not prepare the database (${describeDbError(error)}). Check the Neon connection in Vercel → Storage.`);
  }
  const app = await buildApp({ config: { ...config, webDistDir: null }, pool, logger: true, trustProxy: true });
  await app.ready();
  return app;
}

/** Short, secret-free description of a database error (connection strings are never included). */
function describeDbError(error: unknown): string {
  const e = error as { code?: string; message?: string };
  const message = (e.message ?? "unknown error").replace(/postgres(ql)?:\/\/\S+/gi, "[connection string]").slice(0, 200);
  return e.code ? `${e.code}: ${message}` : message;
}

export default async function handler(req: IncomingMessage, res: ServerResponse): Promise<void> {
  let app: FastifyInstance;
  try {
    ready ??= init().catch((error) => {
      ready = null; // retry initialisation on the next request
      throw error;
    });
    app = await ready;
  } catch (error) {
    // Report configuration problems clearly instead of an opaque 500; details go to the function log.
    console.error("Cardcore failed to start:", error);
    res.statusCode = 503;
    res.setHeader("content-type", "application/json");
    res.end(
      JSON.stringify({
        error: "startup_failed",
        message:
          error instanceof StartupError
            ? error.message
            : "The server could not start. See the function logs in Vercel → Logs for details.",
      }),
    );
    return;
  }
  app.server.emit("request", req, res);
}
