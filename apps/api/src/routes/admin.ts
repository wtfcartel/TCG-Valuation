import { createHash, randomBytes } from "node:crypto";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { requireRole } from "../auth.js";
import { audit } from "../audit.js";
import { many, one } from "../db.js";
import { badRequest, notFound } from "../errors.js";
import { parse, uuid, type AppContext } from "./context.js";

export const RESET_TOKEN_TTL_HOURS = 24;

export function hashResetToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

export async function adminRoutes(app: FastifyInstance, ctx: AppContext) {
  app.get("/api/admin/users", async (req) => {
    requireRole(req, "admin");
    return many(ctx.pool, `SELECT id, email, display_name, role, base_currency, created_at FROM users ORDER BY created_at`);
  });

  app.patch("/api/admin/users/:id/role", async (req) => {
    const admin = requireRole(req, "admin");
    const { id } = parse(z.object({ id: uuid }), req.params);
    const { role } = parse(z.object({ role: z.enum(["collector", "valuer", "admin"]) }), req.body);
    if (id === admin.id) throw badRequest("You cannot change your own role");
    const before = await one<{ role: string }>(ctx.pool, `SELECT role FROM users WHERE id = $1`, [id]);
    if (!before) throw notFound("User");
    const row = await one(ctx.pool, `UPDATE users SET role = $2 WHERE id = $1 RETURNING id, email, display_name, role`, [id, role]);
    await audit(ctx.pool, admin.id, "user.role_changed", "user", id, { from: before.role, to: role }, req.id);
    return row;
  });

  /** Issue a one-time reset link for a user (delivered by the admin until email is configured). */
  app.post("/api/admin/users/:id/password-reset", async (req, reply) => {
    const admin = requireRole(req, "admin");
    const { id } = parse(z.object({ id: uuid }), req.params);
    const target = await one(ctx.pool, `SELECT 1 FROM users WHERE id = $1`, [id]);
    if (!target) throw notFound("User");
    const token = randomBytes(32).toString("base64url");
    const row = await one<{ expires_at: string }>(
      ctx.pool,
      `INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_by)
       VALUES ($1, $2, now() + make_interval(hours => $3), $4) RETURNING expires_at`,
      [id, hashResetToken(token), RESET_TOKEN_TTL_HOURS, admin.id],
    );
    // The token itself is never written to the audit trail or logs.
    await audit(ctx.pool, admin.id, "user.password_reset_issued", "user", id, { expiresAt: row!.expires_at }, req.id);
    return reply.code(201).send({ token, expiresAt: row!.expires_at });
  });
}
