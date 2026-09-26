import { roundMinor } from "./money.js";
import type { Statistics } from "./types.js";

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

export function median(values: number[]): number {
  if (values.length === 0) throw new RangeError("median of empty set");
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 1
    ? sorted[mid]!
    : roundMinor((sorted[mid - 1]! + sorted[mid]!) / 2);
}

/**
 * Descriptive statistics over a set of minor-unit amounts.
 *
 * Dispersion is defined as (max − min) / mean × 100. It is deliberately simple so a
 * reviewer can recompute it by hand from the comparable schedule in the report.
 */
export function describe(values: number[]): Statistics {
  if (values.length === 0) throw new RangeError("statistics of empty set");
  const count = values.length;
  const sum = values.reduce((acc, v) => acc + v, 0);
  const mean = sum / count;
  const minMinor = Math.min(...values);
  const maxMinor = Math.max(...values);
  const variance = values.reduce((acc, v) => acc + (v - mean) ** 2, 0) / count;
  return {
    count,
    meanMinor: roundMinor(mean),
    medianMinor: median(values),
    minMinor,
    maxMinor,
    rangeMinor: maxMinor - minMinor,
    dispersionPct: mean === 0 ? 0 : round2(((maxMinor - minMinor) / mean) * 100),
    coefficientOfVariationPct: mean === 0 ? 0 : round2((Math.sqrt(variance) / mean) * 100),
  };
}

export function deviationPct(value: number, reference: number): number {
  return reference === 0 ? 0 : round2((Math.abs(value - reference) / reference) * 100);
}
