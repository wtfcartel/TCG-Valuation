/**
 * Development seed: a demo collector with a small collection, synthetic evidence, valuations,
 * an insurance schedule, a sale and both report types. Uses the public API surface so the seed
 * exercises the same code paths as the app. Refuses to run in production.
 */
import { addDays } from "@cardcore/engine";
import { buildApp } from "./app.js";
import { loadConfig } from "./config.js";
import { createPool, migrate, one } from "./db.js";
import { today } from "./services/valuation.js";
import { promoteToAdmin } from "./services/admin.js";

const config = loadConfig();
if (process.env.NODE_ENV === "production") throw new Error("Refusing to seed demo data in production");
const pool = createPool(config.databaseUrl);
await migrate(pool, config);
const app = await buildApp({ config: { ...config, enableDemoSource: true }, pool });

async function call(method: string, url: string, token?: string, payload?: unknown) {
  const res = await app.inject({
    method: method as "GET",
    url,
    headers: token ? { authorization: `Bearer ${token}` } : {},
    ...(payload !== undefined ? { payload: payload as object } : {}),
  });
  if (res.statusCode >= 400) throw new Error(`${method} ${url} → ${res.statusCode}: ${res.body}`);
  return res.json();
}

try {
  const email = "demo@cardcore.local";
  const password = "cardcore-demo-password";
  const existing = await one(pool, `SELECT id FROM users WHERE email = $1`, [email]);
  if (existing) {
    console.log(`Demo user already exists — log in as ${email} / ${password}`);
  } else {
    await call("POST", "/api/auth/register", undefined, { email, password, displayName: "Demo Collector", baseCurrency: "USD" });
    await promoteToAdmin(pool, email); // demo data only: lets the demo account record FX rates
    const { token } = await call("POST", "/api/auth/login", undefined, { email, password });
    const me = await call("GET", "/api/me", token);
    const collectionId = me.collections[0].id;

    for (let d = 0; d <= 730; d += 7) {
      await call("POST", "/api/fx-rates", token, {
        baseCurrency: "EUR",
        quoteCurrency: "USD",
        rate: 1.08 + 0.02 * Math.sin(d / 60),
        rateDate: addDays(today(), -d),
        source: "Synthetic demo rate (replace with ECB reference rates)",
      });
    }

    const cards = [
      { game: "pokemon", setCode: "base1", setName: "Base Set", cardNumber: "4/102", cardName: "Charizard", edition: "unlimited", variant: "holo", grading: { gradingCompany: "PSA", grade: "9", certNumber: "40123456" }, price: 180_000, daysAgo: 500 },
      { game: "pokemon", setCode: "neo1", setName: "Neo Genesis", cardNumber: "9/111", cardName: "Lugia", edition: "1st", variant: "holo", grading: { gradingCompany: "BGS", grade: "8.5", certNumber: "0011223344" }, price: 95_000, daysAgo: 300 },
      { game: "one_piece", setCode: "OP01", setName: "Romance Dawn", cardNumber: "OP01-120", cardName: "Shanks", language: "ja", variant: "alt_art", grading: { condition: "NM" }, price: 32_000, daysAgo: 200 },
      { game: "mtg", setCode: "LEA", setName: "Limited Edition Alpha", cardNumber: "232", cardName: "Lightning Bolt", variant: "normal", grading: { gradingCompany: "CGC", grade: "7", certNumber: "CGC-998877" }, price: 120_000, daysAgo: 420 },
      { game: "pokemon", productType: "sealed", category: "booster_box", setCode: "sv3pt5", setName: "Scarlet & Violet 151", cardNumber: null, cardName: "151 Booster Bundle", variant: null, grading: {}, price: 6_000, daysAgo: 250 },
    ];
    const assetIds: string[] = [];
    for (const c of cards) {
      const identity = await call("POST", "/api/catalog/cards", token, {
        game: c.game,
        productType: c.productType ?? "single",
        category: c.category ?? "card",
        setCode: c.setCode,
        setName: c.setName,
        cardNumber: c.cardNumber,
        cardName: c.cardName,
        language: c.language ?? "en",
        edition: c.edition ?? null,
        variant: c.variant,
      });
      const asset = await call("POST", `/api/collections/${collectionId}/assets`, token, {
        cardIdentityId: identity.id,
        quantity: 1,
        acquisitionDate: addDays(today(), -c.daysAgo),
        acquisitionPriceMinor: c.price,
        acquisitionCurrency: "USD",
        acquisitionSource: "Seed data",
        ...c.grading,
      });
      assetIds.push(asset.id);
      await call("POST", `/api/assets/${asset.id}/evidence/import`, token, { sourceId: "demo" });
      await call("POST", `/api/assets/${asset.id}/valuations`, token, { purpose: "historical", valuationDate: addDays(today(), -Math.min(c.daysAgo - 1, 120)) });
      await call("POST", `/api/assets/${asset.id}/valuations`, token, { purpose: "historical", valuationDate: addDays(today(), -45) });
      await call("POST", `/api/assets/${asset.id}/valuations`, token, { purpose: "market" });
    }

    const schedule = await call("POST", `/api/collections/${collectionId}/schedules`, token, {
      insurerName: "Example Collectibles Insurance",
      policyReference: "ECI-POL-2026-0001",
      customerReference: "CUST-DEMO",
    });
    await call("POST", `/api/schedules/${schedule.id}/reconcile`, token);
    await call("POST", `/api/assets/${assetIds[3]}/disposals`, token, {
      effectiveDate: today(),
      quantity: 1,
      proceedsMinor: 135_000,
      currency: "USD",
      counterparty: "Auction sale",
    });
    await call("POST", `/api/collections/${collectionId}/reports/valuation`, token, { purpose: "market" });
    await call("POST", `/api/schedules/${schedule.id}/reports/adjustment`, token, {});
    console.log(`Seeded demo data — log in as ${email} / ${password}`);
  }
} finally {
  await app.close();
  await pool.end();
}
