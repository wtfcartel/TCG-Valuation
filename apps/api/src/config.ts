import { existsSync } from "node:fs";

export interface Config {
  databaseUrl: string;
  jwtSecret: string;
  port: number;
  photoStorageDir: string;
  enableDemoSource: boolean;
  enableTcgdex: boolean;
  webDistDir: string | null;
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

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  if (env === process.env) loadDotEnv();
  const production = env.NODE_ENV === "production";
  const jwtSecret = env.JWT_SECRET ?? (production ? "" : "dev-only-insecure-secret-change-me");
  if (jwtSecret.length < 16) throw new Error("JWT_SECRET must be set to at least 16 characters");
  return {
    databaseUrl: env.DATABASE_URL ?? "postgres://cardcore:cardcore@localhost:5432/cardcore",
    jwtSecret,
    port: Number(env.PORT ?? 8080),
    photoStorageDir: env.PHOTO_STORAGE_DIR ?? "./storage/photos",
    enableDemoSource: bool(env.ENABLE_DEMO_SOURCE, !production),
    enableTcgdex: bool(env.ENABLE_TCGDEX, true),
    webDistDir: env.WEB_DIST_DIR ?? null,
  };
}
