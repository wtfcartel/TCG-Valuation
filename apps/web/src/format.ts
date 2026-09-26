export function money(minor: number | null | undefined, currency = "USD"): string {
  if (minor == null) return "—";
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(minor / 100);
}

export function toMinor(major: string): number {
  const n = Number(major);
  if (!Number.isFinite(n) || n < 0) throw new Error(`Invalid amount: ${major}`);
  return Math.round(n * 100);
}

export function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export const label = (s: string | null | undefined) => (s ?? "").replace(/_/g, " ");
