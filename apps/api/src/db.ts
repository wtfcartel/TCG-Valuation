import { readdir, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import pg from "pg";
import { CSM_1_0_0_PARAMETERS, CSM_VERSION } from "@cardcore/engine";
import { SOURCE_DEFINITIONS } from "./sources/definitions.js";

// Return bigint / numeric columns as JS numbers. Minor-unit amounts stay far below 2^53.
pg.types.setTypeParser(20, (v) => Number(v)); // int8
pg.types.setTypeParser(1700, (v) => Number(v)); // numeric
pg.types.setTypeParser(1082, (v) => v); // date → 'YYYY-MM-DD' string, no TZ shifting
pg.types.setTypeParser(1184, (v) => new Date(v).toISOString()); // timestamptz → ISO-8601 UTC string

export type Db = pg.Pool;
export type Tx = pg.PoolClient;
export type Queryable = pg.Pool | pg.PoolClient;

export function createPool(connectionString: string): pg.Pool {
  return new pg.Pool({ connectionString, max: 10 });
}

export async function withTx<T>(pool: pg.Pool, fn: (tx: Tx) => Promise<T>): Promise<T> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const result = await fn(client);
    await client.query("COMMIT");
    return result;
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

export async function one<T extends pg.QueryResultRow>(db: Queryable, sql: string, params: unknown[] = []): Promise<T | null> {
  const { rows } = await db.query<T>(sql, params);
  return rows[0] ?? null;
}

export async function many<T extends pg.QueryResultRow>(db: Queryable, sql: string, params: unknown[] = []): Promise<T[]> {
  const { rows } = await db.query<T>(sql, params);
  return rows;
}

function migrationsDir(): string {
  // Works from src/ (tsx) and dist/ (bundled) — both sit beside ../migrations.
  return join(dirname(fileURLToPath(import.meta.url)), "..", "migrations");
}

export async function migrate(pool: pg.Pool): Promise<string[]> {
  await pool.query(`CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())`);
  const applied = new Set((await many<{ name: string }>(pool, "SELECT name FROM schema_migrations")).map((r) => r.name));
  const files = (await readdir(migrationsDir())).filter((f) => f.endsWith(".sql")).sort();
  const ran: string[] = [];
  for (const file of files) {
    if (applied.has(file)) continue;
    const sql = await readFile(join(migrationsDir(), file), "utf8");
    await withTx(pool, async (tx) => {
      await tx.query(sql);
      await tx.query("INSERT INTO schema_migrations (name) VALUES ($1)", [file]);
    });
    ran.push(file);
  }
  await ensureReferenceData(pool);
  return ran;
}

/** Idempotently register data sources and the current methodology version. */
export async function ensureReferenceData(pool: pg.Pool): Promise<void> {
  for (const s of SOURCE_DEFINITIONS) {
    await pool.query(
      `INSERT INTO data_sources (id, name, provides, licence_status, licence_notes, reliability_tier)
       VALUES ($1, $2, $3, $4, $5, $6)
       ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, provides = EXCLUDED.provides,
         licence_status = EXCLUDED.licence_status, licence_notes = EXCLUDED.licence_notes, reliability_tier = EXCLUDED.reliability_tier`,
      [s.id, s.name, s.provides, s.licenceStatus, s.licenceNotes, s.reliabilityTier],
    );
  }
  await pool.query(
    `INSERT INTO methodology_versions (id, name, summary, parameters, document_ref, effective_from)
     VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (id) DO NOTHING`,
    [
      CSM_VERSION,
      "Cardcore Comparable Sales Method",
      "Mean of the three most recent verified arm's-length completed sales of the closest equivalent asset, with dispersion-triggered escalation to 5–10 transactions, documented exclusions, progressive window widening and secondary comparables for thin markets, and a transparent evidence-based confidence classification.",
      JSON.stringify(CSM_1_0_0_PARAMETERS),
      "docs/methodology/CSM-1.0.0.md",
      "2026-09-26",
    ],
  );
}
