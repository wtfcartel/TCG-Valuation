import type { ISODate } from "./types.js";

/** Round half away from zero to an integer (used for all minor-unit money rounding). */
export function roundMinor(value: number): number {
  if (!Number.isFinite(value)) throw new RangeError(`Cannot round non-finite value ${value}`);
  return value < 0 ? -Math.round(-value) : Math.round(value);
}

/** Convert integer minor units at a quoted rate (1 unit of source currency = `rate` units of target). */
export function convertMinor(amountMinor: number, rate: number): number {
  if (!(rate > 0)) throw new RangeError(`FX rate must be positive, got ${rate}`);
  return roundMinor(amountMinor * rate);
}

export function applyPercentage(amountMinor: number, pct: number): number {
  return roundMinor(amountMinor * (1 + pct / 100));
}

const DAY_MS = 86_400_000;

export function toDayNumber(date: ISODate): number {
  const ms = Date.parse(`${date.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(ms)) throw new RangeError(`Invalid ISO date: ${date}`);
  return Math.floor(ms / DAY_MS);
}

/** Whole days from `earlier` to `later` (positive when `earlier` precedes `later`). */
export function daysBetween(earlier: ISODate, later: ISODate): number {
  return toDayNumber(later) - toDayNumber(earlier);
}

export function addDays(date: ISODate, days: number): ISODate {
  return new Date((toDayNumber(date) + days) * DAY_MS).toISOString().slice(0, 10);
}
