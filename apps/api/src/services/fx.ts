import type { FxLookup, FxQuote } from "@cardcore/engine";
import type { Queryable } from "../db.js";
import { many } from "../db.js";

interface FxRow {
  id: string;
  base_currency: string;
  quote_currency: string;
  rate: number;
  rate_date: string;
  source: string;
}

/**
 * Load documented FX rates and expose a synchronous, look-ahead-free lookup for the engine.
 * Resolution order: direct rate, inverse rate, then a cross rate via EUR or USD (ECB rates
 * are EUR-based). Every quote carries its source so the report can document it.
 */
export async function loadFxLookup(db: Queryable, upTo: string): Promise<FxLookup> {
  const rows = await many<FxRow>(
    db,
    `SELECT id, base_currency, quote_currency, rate, rate_date, source FROM fx_rates WHERE rate_date <= $1 ORDER BY rate_date DESC, fetched_at DESC`,
    [upTo],
  );
  const byPair = new Map<string, FxRow[]>();
  for (const row of rows) {
    const key = `${row.base_currency}>${row.quote_currency}`;
    const list = byPair.get(key) ?? [];
    list.push(row);
    byPair.set(key, list);
  }

  const latest = (from: string, to: string, onDate: string): FxRow | undefined =>
    byPair.get(`${from}>${to}`)?.find((r) => r.rate_date <= onDate);

  const pair = (from: string, to: string, onDate: string): FxQuote | null => {
    const direct = latest(from, to, onDate);
    if (direct) return { rate: direct.rate, rateId: direct.id, rateDate: direct.rate_date, source: direct.source };
    const inverse = latest(to, from, onDate);
    if (inverse) {
      return { rate: 1 / inverse.rate, rateId: inverse.id, rateDate: inverse.rate_date, source: `${inverse.source} (inverted)` };
    }
    return null;
  };

  return (from, to, onDate) => {
    if (from === to) return { rate: 1, rateId: null, rateDate: onDate, source: "identity" };
    const quote = pair(from, to, onDate);
    if (quote) return quote;
    for (const via of ["EUR", "USD"]) {
      if (via === from || via === to) continue;
      const a = pair(from, via, onDate);
      const b = pair(via, to, onDate);
      if (a && b) {
        return {
          rate: a.rate * b.rate,
          rateId: null,
          rateDate: a.rateDate < b.rateDate ? a.rateDate : b.rateDate,
          source: `cross via ${via}: ${a.source}; ${b.source}`,
        };
      }
    }
    return null;
  };
}

export function convertAt(fx: FxLookup, amountMinor: number, from: string, to: string, onDate: string): number | null {
  const quote = fx(from, to, onDate);
  return quote ? Math.round(amountMinor * quote.rate) : null;
}
