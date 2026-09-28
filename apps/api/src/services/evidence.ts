import type { Queryable } from "../db.js";
import type { SourcedObservation } from "../sources/types.js";

const SHARED_SCOPE = "00000000-0000-0000-0000-000000000000";

/**
 * Write sourced observations to the market-data layer. Duplicates are ignored: for shared sources the
 * key is (source, reference); for owner-scoped (user-uploaded) sources it is per uploader.
 */
export async function storeObservations(
  db: Queryable,
  sourceId: string,
  cardIdentityId: string,
  observations: SourcedObservation[],
  userId: string,
): Promise<{ inserted: number; duplicates: number }> {
  const src = await db.query<{ owner_scoped: boolean }>(`SELECT owner_scoped FROM data_sources WHERE id = $1`, [sourceId]);
  if (!src.rows[0]) throw new Error(`Unknown data source ${sourceId}`);
  const ownerScope = src.rows[0].owner_scoped ? userId : SHARED_SCOPE;
  let inserted = 0;
  for (const o of observations) {
    const res = await db.query(
      `INSERT INTO price_observations (source_id, source_reference, source_url, card_identity_id, observation_kind, grading_company, grade,
         condition, observed_at, venue, amount_minor, currency, buyers_premium_minor, arms_length, verification_status, verification_notes,
         fetched_at, raw_payload, ingested_by, owner_scope)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,now(),$17,$18,$19)
       ON CONFLICT (source_id, source_reference, owner_scope) DO NOTHING`,
      [
        sourceId,
        o.sourceReference,
        o.sourceUrl,
        cardIdentityId,
        o.kind,
        o.gradingCompany,
        o.grade,
        o.condition,
        o.observedAt,
        o.venue,
        o.amountMinor,
        o.currency,
        o.buyersPremiumMinor,
        o.armsLength,
        o.verificationStatus,
        o.verificationNotes,
        JSON.stringify(o.raw ?? {}),
        userId,
        ownerScope,
      ],
    );
    inserted += res.rowCount ?? 0;
  }
  return { inserted, duplicates: observations.length - inserted };
}

/** Minimal RFC-4180 CSV parser (quoted fields, escaped quotes, CRLF). */
export function parseCsv(text: string): Array<Record<string, string>> {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i]!;
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(field);
      field = "";
      if (row.some((c) => c.trim() !== "")) rows.push(row);
      row = [];
    } else {
      field += ch;
    }
  }
  row.push(field);
  if (row.some((c) => c.trim() !== "")) rows.push(row);
  const [header, ...body] = rows;
  if (!header) return [];
  const keys = header.map((h) => h.trim().toLowerCase());
  return body.map((r) => Object.fromEntries(keys.map((k, i) => [k, (r[i] ?? "").trim()])));
}
