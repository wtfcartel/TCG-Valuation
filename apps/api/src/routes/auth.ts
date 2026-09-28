import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { hashPassword, verifyPassword } from "../auth.js";
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

export async function authRoutes(app: FastifyInstance, ctx: AppContext) {
  app.post("/api/auth/register", async (req, reply) => {
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
    const u = await one<{ id: string; email: string; role: "collector" | "valuer" | "admin"; password_hash: string }>(
      ctx.pool,
      `SELECT id, email, role, password_hash FROM users WHERE email = $1`,
      [body.email],
    );
    if (!u || !(await verifyPassword(body.password, u.password_hash))) {
      throw new HttpError(401, "Invalid email or password", "unauthorized");
    }
    const token = await ctx.tokens.sign(u);
    return { token, user: { id: u.id, email: u.email, role: u.role } };
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
