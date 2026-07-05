// Shared formatting helpers.

// South-African Rand, formatted R{:,.2f} (e.g. R1,234,567.00).
export function rand(value: number | null | undefined): string {
  const n = typeof value === "number" && isFinite(value) ? value : 0;
  return `R${n.toLocaleString("en-ZA", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function num(value: number | null | undefined): string {
  const n = typeof value === "number" && isFinite(value) ? value : 0;
  return n.toLocaleString("en-ZA");
}

// Clamp convergence-style values into 0..100.
export function pct(value: number | null | undefined): number {
  const n = typeof value === "number" && isFinite(value) ? value : 0;
  return Math.max(0, Math.min(100, n));
}
