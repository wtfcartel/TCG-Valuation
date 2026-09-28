import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { AttemptLimiter, hashPassword, verifyPassword } from "../auth.js";
import { hashResetToken } from "./admin.js";
import { audit } from "../audit.js";
import { one, withTx } from "../db.js";
import { HttpError, conflict } from "../errors.js";
import { currency, parse, user, type AppContext } from "./context.js";

const registerSchema = z.object({
  email: z.string().email().transform((e) => e.toLowerCase()),
  password: z.string().min(10, "password must be at least 10 characters"),
  displayName: z.string().min(1).max(120),
  baseCurrency: currency.default("USD"),
});

const loginSchema = z.object({ email: z.string().email().transform((e) => e.toLowerCase()), password: z.string() });

const newPassword = z.string().min(10, "password must be at least 10 characters").max(200);

export async function authRoutes(app: FastifyInstance, ctx: AppContext) {
  // 10 failed logins per email+IP per 15 minutes; 20 registrations / reset attempts per IP per hour.
  const loginLimiter = new AttemptLimiter(10, 15 * 60 * 1000);
  const ipLimiter = new AttemptLimiter(20, 60 * 60 * 1000);

  app.post("/api/auth/register", async (req, reply) => {
    ipLimiter.check(`register:${req.ip}`);
    ipLimiter.fail(`register:${req.ip}`);
    const body = parse(registerSchema, req.body);
    const existing = await one(ctx.pool, `SELECT 1 FROM users WHERE email = $1`, [body.email]);
    if (existing) throw conflict("An account with this email already exists");
    const passwordHash = await hashPassword(body.password);
    const created = await withTx(ctx.pool, async (tx) => {
      // Bootstrap: addresses listed in ADMIN_EMAILS become admins on registration.
      const role = ctx.config.adminEmails.includes(body.email) ? "admin" : "collector";
      const u = await one<{ id: string; email: string; role: "collector" | "admin" }>(
        tx,
        `INSERT INTO users (email, password_hash, display_name, base_currency, role) VALUES ($1,$2,$3,$4,$5) RETURNING id, email, role`,
        [body.email, passwordHash, body.displayName, body.baseCurrency, role],
      );
      const c = await one<{ id: string }>(
        tx,
        `INSERT INTO collections (owner_user_id, name, base_currency) VALUES ($1, $2, $3) RETURNING id`,
        [u!.id, "My collection", body.baseCurrency],
      );
      await audit(tx, u!.id, "user.registered", "user", u!.id, { collectionId: c!.id }, req.id);
      return u!;
    });
    const token = await ctx.tokens.sign(created);
    return reply.code(201).send({ token, user: created });
  });

  app.post("/api/auth/login", async (req) => {
    const body = parse(loginSchema, req.body);
    const key = `${body.email}|${req.ip}`;
    loginLimiter.check(key);
    const u = await one<{ id: string; email: string; role: "collector" | "valuer" | "admin"; password_hash: string; session_version: number }>(
      ctx.pool,
      `SELECT id, email, role, password_hash, session_version FROM users WHERE email = $1`,
      [body.email],
    );
    if (!u || !(await verifyPassword(body.password, u.password_hash))) {
      loginLimiter.fail(key);
      await audit(ctx.pool, u?.id ?? null, "auth.login_failed", "user", u?.id ?? body.email, { ip: req.ip }, req.id);
      throw new HttpError(401, "Invalid email or password", "unauthorized");
    }
    loginLimiter.reset(key);
    const token = await ctx.tokens.sign(u, u.session_version);
    return { token, user: { id: u.id, email: u.email, role: u.role } };
  });

  app.post("/api/auth/change-password", async (req) => {
    const current = user(req);
    const b = parse(z.object({ currentPassword: z.string(), newPassword }), req.body);
    const key = `change:${current.id}`;
    loginLimiter.check(key);
    const row = await one<{ password_hash: string; email: string; role: "collector" | "valuer" | "admin" }>(
      ctx.pool,
      `SELECT password_hash, email, role FROM users WHERE id = $1`,
      [current.id],
    );
    if (!row || !(await verifyPassword(b.currentPassword, row.password_hash))) {
      loginLimiter.fail(key);
      throw new HttpError(401, "Current password is incorrect", "unauthorized");
    }
    const bumped = await one<{ session_version: number }>(
      ctx.pool,
      `UPDATE users SET password_hash = $2, session_version = session_version + 1 WHERE id = $1 RETURNING session_version`,
      [current.id, await hashPassword(b.newPassword)],
    );
    await audit(ctx.pool, current.id, "user.password_changed", "user", current.id, {}, req.id);
    // Sessions issued before this second are now rejected; return a fresh one for the caller.
    return { token: await ctx.tokens.sign({ id: current.id, email: row.email, role: row.role }, bumped!.session_version) };
  });

  app.post("/api/auth/password-reset/confirm", async (req) => {
    ipLimiter.check(`reset:${req.ip}`);
    const b = parse(z.object({ token: z.string().min(20).max(200), newPassword }), req.body);
    const hash = hashResetToken(b.token);
    const updated = await withTx(ctx.pool, async (tx) => {
      const t = await one<{ id: string; user_id: string }>(
        tx,
        `SELECT id, user_id FROM password_reset_tokens WHERE token_hash = $1 AND used_at IS NULL AND expires_at > now() FOR UPDATE`,
        [hash],
      );
      if (!t) return null;
      await tx.query(`UPDATE password_reset_tokens SET used_at = now() WHERE id = $1`, [t.id]);
      await tx.query(`UPDATE users SET password_hash = $2, session_version = session_version + 1 WHERE id = $1`, [t.user_id, await hashPassword(b.newPassword)]);
      await audit(tx, t.user_id, "user.password_reset_completed", "user", t.user_id, {}, req.id);
      return t.user_id;
    });
    if (!updated) {
      ipLimiter.fail(`reset:${req.ip}`);
      throw new HttpError(400, "This reset link is invalid, expired or already used", "bad_request");
    }
    return { ok: true };
  });

  app.get("/api/me", async (req) => {
    const u = user(req);
    const profile = await one(
      ctx.pool,
      `SELECT id, email, display_name, role, base_currency, created_at FROM users WHERE id = $1`,
      [u.id],
    );
    const collections = await ctx.pool.query(`SELECT id, name, base_currency FROM collections WHERE owner_user_id = $1 ORDER BY created_at`, [u.id]);
    return { ...profile, collections: collections.rows };
  });
}
