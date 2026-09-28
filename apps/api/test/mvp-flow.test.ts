import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { FastifyInstance } from "fastify";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildApp } from "../src/app.js";
import { loadConfig } from "../src/config.js";
import { createPool, migrate, type Db } from "../src/db.js";
import { today } from "../src/services/valuation.js";
import { addDays } from "@cardcore/engine";

const DATABASE_URL = process.env.TEST_DATABASE_URL ?? "postgres://cardcore:cardcore@localhost:5432/cardcore_test";

let app: FastifyInstance;
let pool: Db;

async function call(method: string, url: string, token?: string, body?: unknown) {
  const res = await app.inject({
    method: method as "GET",
    url,
    headers: token ? { authorization: `Bearer ${token}` } : {},
    ...(body !== undefined ? { payload: body as object } : {}),
  });
  const isJson = (res.headers["content-type"] ?? "").toString().includes("json");
  return { status: res.statusCode, body: isJson ? res.json() : res.rawPayload };
}

beforeAll(async () => {
  pool = createPool(DATABASE_URL);
  await pool.query("DROP SCHEMA public CASCADE; CREATE SCHEMA public;");
  await migrate(pool);
  const config = {
    ...loadConfig({ NODE_ENV: "test" } as NodeJS.ProcessEnv),
    databaseUrl: DATABASE_URL,
    enableDemoSource: true,
    enableTcgdex: false,
    photoStorageDir: await mkdtemp(join(tmpdir(), "cardcore-photos-")),
    adminEmails: ["admin@example.com"],
  };
  app = await buildApp({ config, pool });
});

afterAll(async () => {
  await app?.close();
  await pool?.end();
});

describe("Cardcore Phase 1 flow", () => {
  let token = "";
  let collectionId = "";
  let identityId = "";
  let identity2Id = "";
  let assetId = "";
  let asset2Id = "";
  let scheduleId = "";
  let marketValuationId = "";

  it("registers a user with a default collection", async () => {
    const reg = await call("POST", "/api/auth/register", undefined, {
      email: "Collector@Example.com",
      password: "correct horse battery",
      displayName: "Alex Collector",
      baseCurrency: "USD",
    });
    expect(reg.status).toBe(201);
    const login = await call("POST", "/api/auth/login", undefined, { email: "collector@example.com", password: "correct horse battery" });
    expect(login.status).toBe(200);
    token = login.body.token;
    const me = await call("GET", "/api/me", token);
    expect(me.body.collections).toHaveLength(1);
    collectionId = me.body.collections[0].id;
    expect((await call("GET", "/api/me")).status).toBe(401);
  });

  it("creates and searches catalogue identities", async () => {
    const card = await call("POST", "/api/catalog/cards", token, {
      game: "pokemon",
      setCode: "base1",
      setName: "Base Set",
      cardNumber: "4/102",
      cardName: "Charizard",
      language: "en",
      edition: "unlimited",
      variant: "holo",
    });
    expect(card.status).toBe(201);
    identityId = card.body.id;
    const again = await call("POST", "/api/catalog/cards", token, {
      game: "pokemon",
      setCode: "base1",
      setName: "Base Set",
      cardNumber: "4/102",
      cardName: "Charizard",
      language: "en",
      edition: "unlimited",
      variant: "holo",
    });
    expect(again.status).toBe(200);
    expect(again.body.id).toBe(identityId);
    const card2 = await call("POST", "/api/catalog/cards", token, {
      game: "one_piece",
      setCode: "OP01",
      setName: "Romance Dawn",
      cardNumber: "OP01-120",
      cardName: "Shanks",
      language: "ja",
      variant: "alt_art",
    });
    identity2Id = card2.body.id;
    const search = await call("GET", "/api/catalog/search?q=chari", token);
    expect(search.body.map((c: { id: string }) => c.id)).toContain(identityId);
  });

  it("adds graded and raw assets with purchase information", async () => {
    const a = await call("POST", `/api/collections/${collectionId}/assets`, token, {
      cardIdentityId: identityId,
      quantity: 1,
      acquisitionDate: addDays(today(), -400),
      acquisitionPriceMinor: 150_000,
      acquisitionCurrency: "USD",
      acquisitionSource: "Local card show",
      gradingCompany: "PSA",
      certNumber: "12345678",
      grade: "9",
    });
    expect(a.status).toBe(201);
    expect(a.body.asset_ref).toMatch(/^CC-\d+$/);
    assetId = a.body.id;
    const b = await call("POST", `/api/collections/${collectionId}/assets`, token, {
      cardIdentityId: identity2Id,
      quantity: 2,
      acquisitionDate: addDays(today(), -30),
      acquisitionPriceMinor: 40_000,
      acquisitionCurrency: "USD",
      condition: "NM",
    });
    asset2Id = b.body.id;
    const bad = await call("POST", `/api/collections/${collectionId}/assets`, token, {
      cardIdentityId: identityId,
      acquisitionDate: today(),
      acquisitionPriceMinor: 1,
      acquisitionCurrency: "USD",
      gradingCompany: "PSA",
    });
    expect(bad.status).toBe(400);
  });

  it("records documented FX rates (valuers/admins only)", async () => {
    const denied = await call("POST", "/api/fx-rates", token, { baseCurrency: "EUR", quoteCurrency: "USD", rate: 9, rateDate: today(), source: "made up" });
    expect(denied.status).toBe(403);
    const admin = await call("POST", "/api/auth/register", undefined, { email: "admin@example.com", password: "admin password 123", displayName: "Admin" });
    expect(admin.body.user.role).toBe("admin");
    for (const d of [today(), addDays(today(), -3)]) {
      const fx = await call("POST", "/api/fx-rates", admin.body.token, {
        baseCurrency: "EUR",
        quoteCurrency: "USD",
        rate: 1.1,
        rateDate: d,
        source: "ECB euro foreign exchange reference rate",
        sourceUrl: "https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html",
      });
      expect([200, 201]).toContain(fx.status);
    }
  });

  it("imports comparable-sale evidence and refuses restricted sources", async () => {
    const imp = await call("POST", `/api/assets/${assetId}/evidence/import`, token, { sourceId: "demo" });
    expect(imp.status).toBe(201);
    expect(imp.body.inserted).toBe(10);
    const dup = await call("POST", `/api/assets/${assetId}/evidence/import`, token, { sourceId: "demo" });
    expect(dup.body.inserted).toBe(0);
    const restricted = await call("POST", `/api/assets/${assetId}/evidence/import`, token, { sourceId: "ebay_marketplace_insights" });
    expect(restricted.status).toBe(422);
    await call("POST", `/api/assets/${asset2Id}/evidence/import`, token, { sourceId: "demo" });
  });

  it("calculates a three-sale market valuation with full audit detail", async () => {
    const v = await call("POST", `/api/assets/${assetId}/valuations`, token, { purpose: "market" });
    expect(v.status).toBe(201);
    marketValuationId = v.body.id;
    expect(v.body.status).toBe("concluded");
    expect(v.body.methodology_version_id).toBe("CSM-1.1.0");
    expect(["high", "moderate", "limited"]).toContain(v.body.confidence);
    const included = v.body.comparables.filter((c: { included: boolean }) => c.included);
    expect(included.length).toBeGreaterThanOrEqual(3);
    const rejectedCodes = v.body.comparables.filter((c: { included: boolean }) => !c.included).map((c: { rejection_code: string }) => c.rejection_code);
    expect(rejectedCodes).toContain("NOT_COMPLETED_SALE"); // asking price never used
    expect(rejectedCodes).toContain("UNVERIFIED");
    expect(rejectedCodes).toContain("NOT_ARMS_LENGTH");
    const mean = Math.round(included.reduce((s: number, c: { basis_amount_base_minor: number }) => s + c.basis_amount_base_minor, 0) / included.length);
    expect(v.body.unit_value_minor).toBe(mean);
    expect(v.body.mean_minor).toBe(mean);
    expect(v.body.median_minor).toBeTypeOf("number");
  });

  it("requires a documented reason to exclude a comparable, and never replaces the old valuation", async () => {
    const detail = await call("GET", `/api/valuations/${marketValuationId}`, token);
    const first = detail.body.comparables.find((c: { included: boolean }) => c.included);
    const noReason = await call("POST", `/api/assets/${assetId}/valuations`, token, {
      exclusions: [{ observationId: first.observation_id, reason: "" }],
    });
    expect(noReason.status).toBe(400);
    const withReason = await call("POST", `/api/assets/${assetId}/valuations`, token, {
      exclusions: [{ observationId: first.observation_id, reason: "Photos show surface scratch on slab; not equivalent" }],
      supersedesValuationId: marketValuationId,
    });
    expect(withReason.status).toBe(201);
    const excluded = withReason.body.comparables.find((c: { observation_id: string }) => c.observation_id === first.observation_id);
    expect(excluded.rejection_code).toBe("MANUAL_EXCLUSION");
    const list = await call("GET", `/api/assets/${assetId}/valuations`, token);
    expect(list.body).toHaveLength(2);
  });

  it("records manual overrides with identity and reason", async () => {
    const short = await call("POST", `/api/valuations/${marketValuationId}/overrides`, token, { overrideUnitValueMinor: 1, reason: "no" });
    expect(short.status).toBe(400);
    const ok = await call("POST", `/api/valuations/${marketValuationId}/overrides`, token, {
      overrideUnitValueMinor: 123_456,
      reason: "Private sale offer received in writing; evidence attached to file",
    });
    expect(ok.status).toBe(201);
    const v = await call("GET", `/api/valuations/${marketValuationId}`, token);
    expect(v.body.effective_unit_value_minor).toBe(123_456);
    expect(v.body.overrides[0].overridden_by_name).toBe("Alex Collector");
  });

  it("enforces append-only history at the database level", async () => {
    await expect(pool.query(`UPDATE valuations SET unit_value_minor = 1 WHERE id = $1`, [marketValuationId])).rejects.toThrow(/append-only/);
    await expect(pool.query(`DELETE FROM ownership_events`)).rejects.toThrow(/append-only/);
    await expect(pool.query(`TRUNCATE audit_events`)).rejects.toThrow(/append-only/);
  });

  it("builds the insurance schedule via reconciliation", async () => {
    const s = await call("POST", `/api/collections/${collectionId}/schedules`, token, {
      insurerName: "Example Mutual",
      policyReference: "POL-001",
      customerReference: "CUST-42",
    });
    expect(s.status).toBe(201);
    scheduleId = s.body.id;
    const r = await call("POST", `/api/schedules/${scheduleId}/reconcile`, token);
    expect(r.status).toBe(201);
    expect(r.body.events[0].event_type).toBe("initial_declaration");
    expect(r.body.events[0].previous_declared_minor).toBe(0);
    const sched = await call("GET", `/api/schedules/${scheduleId}`, token);
    expect(sched.body.scheduledAssets).toHaveLength(2);
    expect(sched.body.declaredValueMinor).toBeGreaterThan(0);
    expect(sched.body.chain.valid).toBe(true);
  });

  it("marks a card sold, creating a disposal adjustment event rather than overwriting value", async () => {
    const before = await call("GET", `/api/schedules/${scheduleId}`, token);
    const declaredBefore = before.body.declaredValueMinor;
    const insuredAsset = before.body.scheduledAssets.find((a: { assetId: string }) => a.assetId === assetId).valueMinor;

    const tooMany = await call("POST", `/api/assets/${assetId}/disposals`, token, {
      effectiveDate: today(),
      quantity: 2,
      proceedsMinor: 200_000,
      currency: "USD",
    });
    expect(tooMany.status).toBe(400);

    const sold = await call("POST", `/api/assets/${assetId}/disposals`, token, {
      effectiveDate: today(),
      quantity: 1,
      proceedsMinor: 200_000,
      currency: "USD",
      counterparty: "eBay buyer",
    });
    expect(sold.status).toBe(201);
    const ev = sold.body.insuranceEvents[0];
    expect(ev.event_type).toBe("disposal");
    expect(ev.previous_declared_minor).toBe(declaredBefore);
    expect(ev.revised_declared_minor).toBe(declaredBefore - insuredAsset);

    const after = await call("GET", `/api/schedules/${scheduleId}`, token);
    expect(after.body.events.map((e: { seq: number }) => e.seq)).toEqual([1, 2]);
    expect(after.body.chain.valid).toBe(true);

    const asset = await call("GET", `/api/assets/${assetId}`, token);
    expect(asset.body.current.status).toBe("disposed");
    expect(asset.body.current.disposalPriceMinor).toBe(200_000);
    expect(asset.body.current.insuranceStatus).toBe("removed");
  });

  it("updates the portfolio automatically and preserves history", async () => {
    const now = await call("GET", `/api/collections/${collectionId}/portfolio`, token);
    expect(now.status).toBe(200);
    expect(now.body.totals.realisedGainMinor).toBe(200_000 - 150_000);
    expect(now.body.positions.find((p: { assetId: string }) => p.assetId === assetId).heldQuantity).toBe(0);
    expect(now.body.totals.heldAssets).toBe(1);
    expect(now.body.byGradingCompany[0].key).toBe("Raw");

    const past = await call("GET", `/api/collections/${collectionId}/portfolio?date=${addDays(today(), -1)}`, token);
    expect(past.body.positions.find((p: { assetId: string }) => p.assetId === assetId).heldQuantity).toBe(1);
    expect(past.body.totals.realisedGainMinor).toBe(0);

    const history = await call("GET", `/api/collections/${collectionId}/portfolio/history?points=10`, token);
    expect(history.body.series.length).toBeGreaterThan(2);
    expect(history.body.series.at(-1).date).toBe(today());
  });

  it("produces historical valuations using only evidence available at that date", async () => {
    const notHeld = await call("POST", `/api/assets/${asset2Id}/valuations`, token, { purpose: "historical", valuationDate: addDays(today(), -60) });
    expect(notHeld.status).toBe(400);
    expect(notHeld.body.message).toMatch(/not held/);
    const date = addDays(today(), -20);
    const v = await call("POST", `/api/assets/${asset2Id}/valuations`, token, { purpose: "historical", valuationDate: date });
    expect(v.status).toBe(201);
    expect(v.body.purpose).toBe("historical");
    for (const c of v.body.comparables.filter((x: { included: boolean }) => x.included)) {
      expect(c.observed_at <= date).toBe(true);
    }
  });

  it("imports a saved eBay sold page as unlicensed evidence and discloses it in reports", async () => {
    const fmt = (d: string) => {
      const [y, m, day] = d.split("-");
      const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][Number(m) - 1];
      return `Sold  ${mon} ${Number(day)}, ${y}`;
    };
    const item = (id: string, daysAgo: number, title: string, price: string) =>
      `<li class="s-item"><span class="s-item__caption--signal POSITIVE"><span>${fmt(addDays(today(), -daysAgo))}</span></span>` +
      `<a href="https://www.ebay.com/itm/${id}"><div class="s-item__title"><span>${title}</span></div></a>` +
      `<span class="s-item__price"><span class="POSITIVE">${price}</span></span></li>`;
    const html = `<html><body><ul class="srp-results">${[
      item("400000000001", 1, "Shanks OP01-120 Japanese Alt Art Romance Dawn NM", "$171.00"),
      item("400000000002", 2, "One Piece Shanks OP01-120 Japanese Parallel NM", "$169.50"),
      item("400000000003", 3, "Shanks OP01-120 Japanese Alt Art NM", "$168.00"),
      item("400000000004", 4, "Shanks OP01-120 English Alt Art", "$90.00"),
    ].join("")}</ul></body></html>`;
    const imp = await call("POST", `/api/assets/${asset2Id}/evidence/ebay-page`, token, { html });
    expect(imp.status).toBe(201);
    expect(imp.body).toMatchObject({ licenceStatus: "unlicensed", listingsFound: 4, matched: 3, inserted: 3 });
    expect(imp.body.skipped).toEqual({ language_mismatch: 1 });

    const v = await call("POST", `/api/assets/${asset2Id}/valuations`, token, { purpose: "market" });
    const used = v.body.comparables.filter((c: { included: boolean }) => c.included);
    expect(used.every((c: { source_id: string; licence_status: string }) => c.source_id === "ebay_sold_scrape" && c.licence_status === "unlicensed")).toBe(true);
    expect(v.body.unit_value_minor).toBe(16_950);

    // The same eBay sale also arriving via another source is used once, preferring the non-scraped copy.
    const csv = await call("POST", `/api/assets/${asset2Id}/evidence/csv`, token, {
      csv: "sale_date,venue,amount,currency,source_reference,source_url,condition,arms_length,verified\n" +
        `${addDays(today(), -1)},eBay,171.00,USD,ebay:400000000001,https://www.ebay.com/itm/400000000001,NM,yes,yes\n`,
    });
    expect(csv.status).toBe(201);
    const v2 = await call("POST", `/api/assets/${asset2Id}/valuations`, token, { purpose: "market" });
    const dups = v2.body.comparables.filter((c: { rejection_code: string }) => c.rejection_code === "DUPLICATE_TRANSACTION");
    expect(dups).toHaveLength(1);
    expect(dups[0].source_id).toBe("ebay_sold_scrape");
    expect(v2.body.unit_value_minor).toBe(16_950);
  });

  it("generates an immutable, hashed valuation report and PDF", async () => {
    const vr = await call("POST", `/api/assets/${asset2Id}/valuations`, token, { purpose: "market" });
    expect(vr.status).toBe(201);
    const rep = await call("POST", `/api/collections/${collectionId}/reports/valuation`, token, { purpose: "market" });
    expect(rep.status).toBe(201);
    expect(rep.body.sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(rep.body.payload.methodology.reviewStatement).toMatch(/has not been independently reviewed/);
    expect(rep.body.payload.evidenceProvenance).toMatch(/UNLICENSED \/ SCRAPED EVIDENCE: 2 comparable/);
    const json = await call("GET", `/api/reports/${rep.body.id}`, token);
    expect(json.body.integrity.verified).toBe(true);
    const pdf = await call("GET", `/api/reports/${rep.body.id}/pdf`, token);
    expect(pdf.status).toBe(200);
    expect(Buffer.from(pdf.body as Buffer).subarray(0, 5).toString()).toBe("%PDF-");
  });

  it("generates an insurer adjustment payload and PDF", async () => {
    const rep = await call("POST", `/api/schedules/${scheduleId}/reports/adjustment`, token, {});
    expect(rep.status).toBe(201);
    const p = rep.body.payload;
    expect(p.policy.policyReference).toBe("POL-001");
    expect(p.previousDeclaredValueMinor).toBe(0);
    expect(p.assetsRemoved).toHaveLength(1);
    expect(p.assetsAdded).toHaveLength(2);
    expect(p.disclaimer).toMatch(/does not calculate premiums/);
    const next = await call("POST", `/api/schedules/${scheduleId}/reports/adjustment`, token, {});
    expect(next.status).toBe(400); // nothing new since last report
    const pdf = await call("GET", `/api/reports/${rep.body.id}/pdf`, token);
    expect(Buffer.from(pdf.body as Buffer).subarray(0, 5).toString()).toBe("%PDF-");
  });

  it("isolates users' collections and user-supplied evidence", async () => {
    const reg = await call("POST", "/api/auth/register", undefined, {
      email: "other@example.com",
      password: "another long password",
      displayName: "Other",
    });
    const other = reg.body.token;
    expect((await call("GET", `/api/assets/${assetId}`, other)).status).toBe(403);
    expect((await call("GET", `/api/collections/${collectionId}/portfolio`, other)).status).toBe(403);
    expect((await call("GET", `/api/reports/${"00000000-0000-0000-0000-000000000000"}`, other)).status).toBe(404);

    const manual = await call("POST", `/api/assets/${asset2Id}/evidence`, token, {
      observedAt: today(),
      venue: "Private sale",
      amountMinor: 1,
      currency: "USD",
      sourceReference: "private-1",
      sourceUrl: "https://example.com/invoice/1",
      verified: true,
      condition: "NM",
    });
    expect(manual.status).toBe(201);
    const count = await pool.query(`SELECT count(*)::int AS n FROM price_observations WHERE source_id = 'manual'`);
    expect(count.rows[0].n).toBe(1);
  });

  it("records every mutation in the audit trail", async () => {
    const audit = await call("GET", `/api/audit?entityType=asset&entityId=${assetId}`, token);
    const actions = audit.body.map((a: { action: string }) => a.action);
    expect(actions).toContain("asset.created");
    expect(actions).toContain("asset.disposed");
    expect(actions).toContain("evidence.imported");
    const full = await call("GET", `/api/audit?assetId=${assetId}`, token);
    const fullActions = full.body.map((a: { action: string }) => a.action);
    expect(fullActions).toContain("valuation.created");
    expect(fullActions).toContain("valuation.overridden");
  });
});
