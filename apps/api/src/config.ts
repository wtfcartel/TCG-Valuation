import { existsSync } from "node:fs";

export interface Config {
  databaseUrl: string;
  jwtSecret: string;
  port: number;
  photoStorageDir: string;
  /** "vercel-blob" on Vercel (no persistent disk); "local" elsewhere. */
  photoStorage: "local" | "vercel-blob";
  /** Vercel Cron sends `Authorization: Bearer <CRON_SECRET>`; cron routes are disabled when unset. */
  cronSecret: string | null;
  enableDemoSource: boolean;
  enableTcgdex: boolean;
  webDistDir: string | null;
  enableEcbFx: boolean;
  poketraceApiKey: string | null;
  poketraceCommercialLicence: boolean;
}

function bool(value: string | undefined, fallback: boolean): boolean {
  if (value == null || value === "") return fallback;
  return ["1", "true", "yes"].includes(value.toLowerCase());
}

/** Load .env from the working directory or the repo root (dev convenience; real env vars win). */
function loadDotEnv(): void {
  for (const path of [".env", "../../.env"]) {
    if (existsSync(path)) {
      process.loadEnvFile(path);
      return;
    }
  }
}

/** A configuration problem the operator must fix; its message is safe to show (never contains secrets). */
export class StartupError extends Error {}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  if (env === process.env) loadDotEnv();
  const production = env.NODE_ENV === "production";
  const jwtSecret = env.JWT_SECRET ?? (production ? "" : "dev-only-insecure-secret-change-me");
  if (jwtSecret.length < 16) throw new StartupError("JWT_SECRET is not set (or is shorter than 16 characters) in the environment variables");
  return {
    // DATABASE_URL (Neon, Docker, local); POSTGRES_URL is what some Vercel Postgres integrations set.
    databaseUrl:
      env.DATABASE_URL ||
      env.POSTGRES_URL ||
      (production ? "" : "postgres://cardcore:cardcore@localhost:5432/cardcore"),
    jwtSecret,
    port: Number(env.PORT ?? 8080),
    photoStorageDir: env.PHOTO_STORAGE_DIR ?? "./storage/photos",
    photoStorage: env.PHOTO_STORAGE === "vercel-blob" || (env.VERCEL && env.PHOTO_STORAGE !== "local") ? "vercel-blob" : "local",
    cronSecret: env.CRON_SECRET && env.CRON_SECRET.length >= 16 ? env.CRON_SECRET : null,
    enableDemoSource: bool(env.ENABLE_DEMO_SOURCE, !production),
    enableTcgdex: bool(env.ENABLE_TCGDEX, true),
    webDistDir: env.WEB_DIST_DIR ?? null,
    enableEcbFx: bool(env.ENABLE_ECB_FX, env.NODE_ENV !== "test"),
    poketraceApiKey: env.POKETRACE_API_KEY || null,
    poketraceCommercialLicence: bool(env.POKETRACE_COMMERCIAL_LICENCE, false),
  };
}
