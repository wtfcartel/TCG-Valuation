import type { FastifyRequest } from "fastify";
import { z } from "zod";
import type { Config } from "../config.js";
import type { Db, Queryable } from "../db.js";
import { one } from "../db.js";
import type { AuthUser, TokenService } from "../auth.js";
import { requireUser } from "../auth.js";
import { badRequest, forbidden, notFound } from "../errors.js";
import type { SourceRegistry } from "../sources/registry.js";

export interface AppContext {
  config: Config;
  photos: import("../services/photo-store.js").PhotoStore;
  pool: Db;
  tokens: TokenService;
  sources: SourceRegistry;
}

export function parse<T extends z.ZodTypeAny>(schema: T, value: unknown): z.infer<T> {
  const result = schema.safeParse(value);
  if (!result.success) {
    throw badRequest(result.error.issues.map((i) => `${i.path.join(".") || "body"}: ${i.message}`).join("; "));
  }
  return result.data;
}

export const isoDate = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "expected YYYY-MM-DD");
export const currency = z.string().regex(/^[A-Z]{3}$/, "expected ISO-4217 code");
export const minor = z.number().int().nonnegative();
export const uuid = z.string().uuid();

export function user(req: FastifyRequest): AuthUser {
  return requireUser(req);
}

function canAccess(u: AuthUser, ownerUserId: string): boolean {
  return u.id === ownerUserId || u.role === "admin";
}

export async function assertCollectionAccess(db: Queryable, u: AuthUser, collectionId: string) {
  const c = await one<{ id: string; owner_user_id: string; base_currency: string; name: string }>(
    db,
    `SELECT id, owner_user_id, base_currency, name FROM collections WHERE id = $1`,
    [collectionId],
  );
  if (!c) throw notFound("Collection");
  if (!canAccess(u, c.owner_user_id)) throw forbidden();
  return c;
}

export async function assertAssetAccess(db: Queryable, u: AuthUser, assetId: string) {
  const a = await one<{ id: string; owner_user_id: string; collection_id: string }>(
    db,
    `SELECT a.id, c.owner_user_id, a.collection_id FROM assets a JOIN collections c ON c.id = a.collection_id WHERE a.id = $1`,
    [assetId],
  );
  if (!a) throw notFound("Asset");
  if (!canAccess(u, a.owner_user_id)) throw forbidden();
  return a;
}

export async function assertValuationAccess(db: Queryable, u: AuthUser, valuationId: string) {
  const v = await one<{ id: string; asset_id: string; owner_user_id: string }>(
    db,
    `SELECT v.id, v.asset_id, c.owner_user_id FROM valuations v JOIN assets a ON a.id = v.asset_id
     JOIN collections c ON c.id = a.collection_id WHERE v.id = $1`,
    [valuationId],
  );
  if (!v) throw notFound("Valuation");
  if (!canAccess(u, v.owner_user_id)) throw forbidden();
  return v;
}

export async function assertScheduleAccess(db: Queryable, u: AuthUser, scheduleId: string) {
  const s = await one<{ id: string; owner_user_id: string; collection_id: string }>(
    db,
    `SELECT s.id, c.owner_user_id, s.collection_id FROM insurance_schedules s JOIN collections c ON c.id = s.collection_id WHERE s.id = $1`,
    [scheduleId],
  );
  if (!s) throw notFound("Insurance schedule");
  if (!canAccess(u, s.owner_user_id)) throw forbidden();
  return s;
}

export { canAccess };
