import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createPool, migrate, type Db } from "../src/db.js";
import { ECB_SOURCE, importEcbRates, parseEcbXml } from "../src/services/ecb.js";
import { loadFxLookup } from "../src/services/fx.js";

const DATABASE_URL = process.env.TEST_DATABASE_URL ?? "postgres://cardcore:cardcore@localhost:5432/cardcore_test";
const xml = readFileSync(join(__dirname, "fixtures", "ecb-hist-sample.xml"), "utf8");
let pool: Db;

beforeAll(async () => {
  pool = createPool(DATABASE_URL);
  await pool.query("DROP SCHEMA public CASCADE; CREATE SCHEMA public;");
  await migrate(pool);
});
afterAll(async () => pool?.end());

describe("ECB reference rates", () => {
  it("parses the ECB XML envelope", () => {
    const rates = parseEcbXml(xml);
    expect(rates).toHaveLength(6);
    expect(rates[0]).toEqual({ date: "2026-09-25", currency: "USD", rate: 1.1712 });
  });

  it("imports idempotently and enables cross rates such as USD→AUD", async () => {
    const fakeFetch = (async () => new Response(xml, { status: 200 })) as typeof fetch;
    const first = await importEcbRates(pool, "last90Days", fakeFetch);
    expect(first).toMatchObject({ fetched: 6, inserted: 6, latestDate: "2026-09-25" });
    const again = await importEcbRates(pool, "daily", fakeFetch);
    expect(again.inserted).toBe(0);

    const fx = await loadFxLookup(pool, "2026-09-28");
    const usdAud = fx("USD", "AUD", "2026-09-28")!;
    expect(usdAud.rate).toBeCloseTo(1.7803 / 1.1712, 8);
    expect(usdAud.rateDate).toBe("2026-09-25");
    expect(usdAud.source).toContain(ECB_SOURCE);
    // Look-ahead is impossible: on 2026-09-24 the 24th's rates are used.
    expect(fx("EUR", "USD", "2026-09-24")!.rate).toBe(1.169);
  });

  it("fails loudly on an empty or failed feed", async () => {
    await expect(importEcbRates(pool, "daily", (async () => new Response("", { status: 503 })) as typeof fetch)).rejects.toThrow(/503/);
    await expect(importEcbRates(pool, "daily", (async () => new Response("<x/>", { status: 200 })) as typeof fetch)).rejects.toThrow(/no rates/);
  });
});
