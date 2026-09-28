import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { buildApp } from "../src/app.js";
import { loadConfig } from "../src/config.js";
import { createPool, migrate, type Db } from "../src/db.js";

const DATABASE_URL = process.env.TEST_DATABASE_URL ?? "postgres://cardcore:cardcore@localhost:5432/cardcore_test";
let app: FastifyInstance;
let pool: Db;

async function call(method: string, url: string, token?: string, body?: unknown, ip = "10.0.0.1") {
  const res = await app.inject({
    method: method as "GET",
    url,
    remoteAddress: ip,
    headers: token ? { authorization: `Bearer ${token}` } : {},
    ...(body !== undefined ? { payload: body as object } : {}),
  });
  return { status: res.statusCode, body: res.headers["content-type"]?.toString().includes("json") ? res.json() : res.body, headers: res.headers };
}

beforeAll(async () => {
  pool = createPool(DATABASE_URL);
  await pool.query("DROP SCHEMA public CASCADE; CREATE SCHEMA public;");
  await migrate(pool);
  const config = { ...loadConfig({ NODE_ENV: "test" } as NodeJS.ProcessEnv), databaseUrl: DATABASE_URL, adminEmails: ["boss@example.com"] };
  app = await buildApp({ config, pool });
});
afterAll(async () => {
  await app?.close();
  await pool?.end();
});

describe("accounts, roles and sessions", () => {
  let admin = "";
  let collector = "";
  let collectorId = "";

  it("bootstraps admins from ADMIN_EMAILS and sends security headers", async () => {
    const a = await call("POST", "/api/auth/register", undefined, { email: "boss@example.com", password: "boss password 1", displayName: "Boss" });
    expect(a.body.user.role).toBe("admin");
    admin = a.body.token;
    const c = await call("POST", "/api/auth/register", undefined, { email: "carol@example.com", password: "carol password 1", displayName: "Carol" });
    expect(c.body.user.role).toBe("collector");
    collector = c.body.token;
    collectorId = c.body.user.id;
    expect(a.headers["x-frame-options"]).toBe("DENY");
    expect(a.headers["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(a.headers["cache-control"]).toBe("no-store");
  });

  it("lets only admins manage roles, and role changes apply to existing sessions immediately", async () => {
    expect((await call("GET", "/api/admin/users", collector)).status).toBe(403);
    const users = await call("GET", "/api/admin/users", admin);
    expect(users.body.map((u: { email: string }) => u.email)).toEqual(["boss@example.com", "carol@example.com"]);
    const fx = { baseCurrency: "EUR", quoteCurrency: "USD", rate: 1.1, rateDate: "2026-09-01", source: "ECB manual" };
    expect((await call("POST", "/api/fx-rates", collector, fx)).status).toBe(403);
    const promoted = await call("PATCH", `/api/admin/users/${collectorId}/role`, admin, { role: "valuer" });
    expect(promoted.body.role).toBe("valuer");
    expect((await call("POST", "/api/fx-rates", collector, fx)).status).toBe(201); // same token, new role
    const me = (await call("GET", "/api/me", admin)).body.id;
    expect((await call("PATCH", `/api/admin/users/${me}/role`, admin, { role: "collector" })).status).toBe(400);
    const audit = await call("GET", `/api/audit?entityType=user&entityId=${collectorId}`, admin);
    expect(audit.body.map((r: { action: string }) => r.action)).toContain("user.role_changed");
  });

  it("issues one-time reset links that revoke existing sessions", async () => {
    const link = await call("POST", `/api/admin/users/${collectorId}/password-reset`, admin);
    expect(link.status).toBe(201);
    const auditRows = await pool.query(`SELECT detail::text AS d FROM audit_events WHERE action = 'user.password_reset_issued'`);
    expect(auditRows.rows[0].d).not.toContain(link.body.token); // token never stored in the audit trail
    const short = await call("POST", "/api/auth/password-reset/confirm", undefined, { token: link.body.token, newPassword: "short" });
    expect(short.status).toBe(400);
    const ok = await call("POST", "/api/auth/password-reset/confirm", undefined, { token: link.body.token, newPassword: "carol new password" });
    expect(ok.status).toBe(200);
    expect((await call("GET", "/api/me", collector)).status).toBe(401); // old session revoked
    const reuse = await call("POST", "/api/auth/password-reset/confirm", undefined, { token: link.body.token, newPassword: "carol another pw" });
    expect(reuse.status).toBe(400);
    expect((await call("POST", "/api/auth/login", undefined, { email: "carol@example.com", password: "carol password 1" })).status).toBe(401);
    const login = await call("POST", "/api/auth/login", undefined, { email: "carol@example.com", password: "carol new password" });
    expect(login.status).toBe(200);
    collector = login.body.token;
  });

  it("changes password with the current one, keeps the caller signed in and signs out other sessions", async () => {
    const other = (await call("POST", "/api/auth/login", undefined, { email: "carol@example.com", password: "carol new password" })).body.token;
    expect((await call("POST", "/api/auth/change-password", collector, { currentPassword: "wrong", newPassword: "carol third password" })).status).toBe(401);
    const changed = await call("POST", "/api/auth/change-password", collector, { currentPassword: "carol new password", newPassword: "carol third password" });
    expect(changed.status).toBe(200);
    expect((await call("GET", "/api/me", changed.body.token)).status).toBe(200);
    expect((await call("GET", "/api/me", collector)).status).toBe(401); // the pre-change token is revoked too
    collector = changed.body.token;
    expect((await call("GET", "/api/me", other)).status).toBe(401);
  });

  it("rate-limits repeated failed logins", async () => {
    for (let i = 0; i < 10; i += 1) {
      expect((await call("POST", "/api/auth/login", undefined, { email: "boss@example.com", password: "nope" }, "10.9.9.9")).status).toBe(401);
    }
    const blocked = await call("POST", "/api/auth/login", undefined, { email: "boss@example.com", password: "boss password 1" }, "10.9.9.9");
    expect(blocked.status).toBe(429);
    // A different client address is not affected.
    expect((await call("POST", "/api/auth/login", undefined, { email: "boss@example.com", password: "boss password 1" }, "10.1.1.1")).status).toBe(200);
  });

  it("records an independent methodology review (admin only) that reports then cite", async () => {
    const reviewer = await call("POST", "/api/reviewers", admin, { name: "Jordan Reviewer", credentials: "CA", organisation: "Example Assurance" });
    expect(reviewer.status).toBe(201);
    expect((await call("POST", "/api/reviewers", collector, { name: "X Y", credentials: "CPA" })).status).toBe(403);
    const review = await call("POST", "/api/methodology/CSM-1.1.0/reviews", admin, {
      reviewerId: reviewer.body.id,
      reviewDate: "2026-09-28",
      scopeStatement: "Design of the comparable selection, statistics, escalation and confidence rules.",
      conclusion: "The rules are appropriate for the stated purposes.",
    });
    expect(review.status).toBe(201);
    const m = await call("GET", "/api/methodology", collector);
    expect(m.body.reviews[0]).toMatchObject({ reviewer_name: "Jordan Reviewer", methodology_version_id: "CSM-1.1.0" });
    const { methodologyReviewStatement } = await import("../src/services/reports.js");
    const statement = methodologyReviewStatement(m.body.reviews, "CSM-1.1.0");
    expect(statement).toMatch(/Jordan Reviewer, CA of Example Assurance/);
    expect(statement).toMatch(/methodology only.*has not reviewed, audited or certified the individual valuations/);
  });
});
