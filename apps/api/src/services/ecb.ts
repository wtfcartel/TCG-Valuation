import * as cheerio from "cheerio";
import type { Queryable } from "../db.js";

/**
 * European Central Bank euro foreign-exchange reference rates.
 * Free to reuse with attribution; published around 16:00 CET on TARGET business days.
 * Rates are quoted as 1 EUR = rate × currency, which is exactly how `fx_rates` stores them
 * (base EUR); USD→AUD etc. resolve as cross rates via EUR.
 */
export const ECB_SOURCE = "ECB euro foreign exchange reference rates";
export const ECB_FEEDS = {
  daily: "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml",
  last90Days: "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml",
  full: "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml",
} as const;
export type EcbFeed = keyof typeof ECB_FEEDS;

export interface EcbRate {
  date: string;
  currency: string;
  rate: number;
}

export function parseEcbXml(xml: string): EcbRate[] {
  const $ = cheerio.load(xml, { xml: true });
  const out: EcbRate[] = [];
  $("Cube[time]").each((_, day) => {
    const date = $(day).attr("time") ?? "";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return;
    $(day)
      .children("Cube[currency]")
      .each((__, el) => {
        const currency = ($(el).attr("currency") ?? "").toUpperCase();
        const rate = Number($(el).attr("rate"));
        if (/^[A-Z]{3}$/.test(currency) && rate > 0) out.push({ date, currency, rate });
      });
  });
  return out;
}

/** Insert rates (idempotent: existing date/currency rows for the ECB source are left untouched). */
export async function storeEcbRates(db: Queryable, rates: EcbRate[], feedUrl: string): Promise<number> {
  let inserted = 0;
  for (let i = 0; i < rates.length; i += 2000) {
    const batch = rates.slice(i, i + 2000);
    const res = await db.query(
      `INSERT INTO fx_rates (base_currency, quote_currency, rate, rate_date, source, source_url)
       SELECT 'EUR', c, r, d::date, $4, $5 FROM unnest($1::text[], $2::numeric[], $3::text[]) AS t(c, r, d)
       ON CONFLICT (base_currency, quote_currency, rate_date, source) DO NOTHING`,
      [batch.map((r) => r.currency), batch.map((r) => r.rate), batch.map((r) => r.date), ECB_SOURCE, feedUrl],
    );
    inserted += res.rowCount ?? 0;
  }
  return inserted;
}

export interface EcbImportResult {
  feed: EcbFeed;
  fetched: number;
  inserted: number;
  latestDate: string | null;
}

export async function importEcbRates(db: Queryable, feed: EcbFeed, fetchImpl: typeof fetch = fetch): Promise<EcbImportResult> {
  const url = ECB_FEEDS[feed];
  const res = await fetchImpl(url, { headers: { accept: "application/xml" } });
  if (!res.ok) throw new Error(`ECB feed ${feed} responded ${res.status}`);
  const rates = parseEcbXml(await res.text());
  if (rates.length === 0) throw new Error(`ECB feed ${feed} contained no rates`);
  const inserted = await storeEcbRates(db, rates, url);
  const latestDate = rates.reduce<string | null>((max, r) => (max == null || r.date > max ? r.date : max), null);
  return { feed, fetched: rates.length, inserted, latestDate };
}

/**
 * Keep rates current: on start, back-fill 90 days if the table has no ECB rates yet, then fetch
 * the daily feed every few hours. Failures are logged, never fatal — valuations simply reject
 * foreign-currency evidence without a rate (NO_FX_RATE) until one exists.
 */
export function startEcbScheduler(
  db: Queryable,
  log: { info: (o: object, m: string) => void; warn: (o: object, m: string) => void },
  opts: { intervalMs?: number; fetchImpl?: typeof fetch } = {},
): () => void {
  const run = async () => {
    try {
      const existing = await db.query(`SELECT 1 FROM fx_rates WHERE source = $1 LIMIT 1`, [ECB_SOURCE]);
      const result = await importEcbRates(db, existing.rowCount ? "daily" : "last90Days", opts.fetchImpl);
      log.info(result, "ECB FX rates imported");
    } catch (error) {
      log.warn({ err: (error as Error).message }, "ECB FX import failed");
    }
  };
  void run();
  const timer = setInterval(run, opts.intervalMs ?? 6 * 60 * 60 * 1000);
  timer.unref();
  return () => clearInterval(timer);
}
