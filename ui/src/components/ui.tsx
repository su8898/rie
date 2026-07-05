// Small presentational primitives shared across pages: coloured chips for
// band / disposition / maturity / mode, a card shell, a convergence bar,
// and loading / error / empty states.

import { useMemo, useState, type ReactNode } from "react";
import type { Band, Disposition } from "../types";

// ── Band chip (GREEN=emerald, AMBER=amber, RED=rose) ─────────────────────────
const BAND_STYLE: Record<Band, string> = {
  GREEN: "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
  AMBER: "bg-amber-100 text-amber-800 ring-amber-600/20",
  RED: "bg-rose-100 text-rose-800 ring-rose-600/20",
};

export function BandChip({ band }: { band: Band }) {
  const cls = BAND_STYLE[band] ?? "bg-slate-100 text-slate-700 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${cls}`}
    >
      {band}
    </span>
  );
}

export function BandDot({ band }: { band: Band }) {
  const color =
    band === "GREEN"
      ? "bg-emerald-500"
      : band === "AMBER"
        ? "bg-amber-500"
        : band === "RED"
          ? "bg-rose-500"
          : "bg-slate-400";
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${color}`} />;
}

// ── Disposition chip (worst-first palette) ───────────────────────────────────
const DISP_STYLE: Record<Disposition, string> = {
  FRAUD: "bg-rose-100 text-rose-800 ring-rose-600/20",
  MERITS: "bg-orange-100 text-orange-800 ring-orange-600/20",
  COMPLIANCE: "bg-amber-100 text-amber-800 ring-amber-600/20",
  PREAUTH: "bg-violet-100 text-violet-800 ring-violet-600/20",
  SI_GATE: "bg-sky-100 text-sky-800 ring-sky-600/20",
  ADJUSTED: "bg-blue-100 text-blue-800 ring-blue-600/20",
  CLEAN: "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
};

export function DispositionChip({ disposition }: { disposition: Disposition }) {
  const cls =
    DISP_STYLE[disposition] ?? "bg-slate-100 text-slate-700 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}
    >
      {disposition}
    </span>
  );
}

// ── Maturity chip (GROUNDED / HEURISTIC / UNVALIDATED) ───────────────────────
export function MaturityChip({ maturity }: { maturity: string }) {
  const cls =
    maturity === "GROUNDED"
      ? "bg-emerald-100 text-emerald-800 ring-emerald-600/20"
      : maturity === "HEURISTIC"
        ? "bg-amber-100 text-amber-800 ring-amber-600/20"
        : maturity === "UNVALIDATED"
          ? "bg-slate-200 text-slate-600 ring-slate-500/20"
          : "bg-slate-100 text-slate-600 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${cls}`}
    >
      {maturity}
    </span>
  );
}

// ── Signal-mode chip (SHADOW / ADVISORY / SCORED) ────────────────────────────
export function ModeChip({ mode }: { mode: string }) {
  const cls =
    mode === "SCORED"
      ? "bg-rose-100 text-rose-800 ring-rose-600/20"
      : mode === "ADVISORY"
        ? "bg-sky-100 text-sky-800 ring-sky-600/20"
        : mode === "SHADOW"
          ? "bg-slate-200 text-slate-500 ring-slate-500/20"
          : "bg-slate-100 text-slate-600 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${cls}`}
    >
      {mode}
    </span>
  );
}

// ── Yes / no tick ────────────────────────────────────────────────────────────
export function YesNo({ value }: { value: boolean }) {
  return value ? (
    <span className="font-semibold text-emerald-600" title="yes">
      ✓
    </span>
  ) : (
    <span className="font-semibold text-slate-300" title="no">
      ✗
    </span>
  );
}

// ── Convergence bar (0–100) ──────────────────────────────────────────────────
export function ConvergenceBar({ value }: { value: number }) {
  const v = Math.max(0, Math.min(100, value));
  const color =
    v >= 66 ? "bg-emerald-500" : v >= 33 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-28 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${v}%` }} />
      </div>
      <span className="tnum w-9 text-right text-xs text-slate-500">
        {Math.round(v)}
      </span>
    </div>
  );
}

// ── Card shell ───────────────────────────────────────────────────────────────
export function Card({
  title,
  children,
  className = "",
}: {
  title?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-slate-200 bg-white shadow-sm ${className}`}
    >
      {title != null && (
        <div className="border-b border-slate-100 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
          {title}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

// ── Stat card ────────────────────────────────────────────────────────────────
export function Stat({
  label,
  value,
  sub,
  accent = "text-slate-900",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`tnum mt-1 text-2xl font-semibold ${accent}`}>{value}</div>
      {sub != null && <div className="mt-1 text-xs text-slate-400">{sub}</div>}
    </div>
  );
}

// ── State helpers ────────────────────────────────────────────────────────────
export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="p-6 text-sm text-slate-400">{label}</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
      <span className="font-semibold">Error:</span> {message}
    </div>
  );
}

export function Empty({ label = "Nothing here yet." }: { label?: string }) {
  return (
    <div className="rounded-md border border-dashed border-slate-200 bg-white p-8 text-center text-sm text-slate-400">
      {label}
    </div>
  );
}

// ── Muted code pill (reason / signal codes) ──────────────────────────────────
export function CodePill({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
      {children}
    </span>
  );
}

// ── Generic state-machine chip ───────────────────────────────────────────────
// Colours states by intent (terminal-good = emerald, terminal-bad = rose,
// in-flight = sky/amber). Falls back to a neutral slate chip for anything else.
const GOOD_STATES = new Set([
  "ACCEPTED",
  "RAF_ACCEPTED",
  "UPHELD",
  "PAYABLE",
  "PAID",
  "SETTLED",
  "FINALIZED",
  "ORDER_PAID",
  "ACTIVE",
  "ASSEMBLED",
  "CLOSED",
]);
const BAD_STATES = new Set([
  "REJECTED",
  "RAF_REJECTED",
  "DISMISSED",
  "REPUDIATED",
  "REJECTED_COMPLIANCE",
  "TERMINATED",
  "LAPSED",
  "SUSPENDED",
]);
const WARN_STATES = new Set([
  "PENDING",
  "APPEALED",
  "HPCSA_APPEAL",
  "HELD",
  "SUBMITTED",
  "ISSUED",
  "RECEIVED",
]);

export function StateChip({ state }: { state: string }) {
  const cls = GOOD_STATES.has(state)
    ? "bg-emerald-100 text-emerald-800 ring-emerald-600/20"
    : BAD_STATES.has(state)
      ? "bg-rose-100 text-rose-800 ring-rose-600/20"
      : WARN_STATES.has(state)
        ? "bg-amber-100 text-amber-800 ring-amber-600/20"
        : "bg-sky-100 text-sky-800 ring-sky-600/20";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${cls}`}
    >
      {state}
    </span>
  );
}

// ── Toast (fixed, dismissible) ───────────────────────────────────────────────
export function Toast({
  message,
  tone = "error",
  onClose,
}: {
  message: string;
  tone?: "error" | "success";
  onClose: () => void;
}) {
  const cls =
    tone === "success"
      ? "border-emerald-300 bg-emerald-50 text-emerald-800"
      : "border-rose-300 bg-rose-50 text-rose-800";
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex justify-center px-4">
      <div
        className={`pointer-events-auto flex max-w-xl items-start gap-3 rounded-lg border px-4 py-3 text-sm shadow-lg ${cls}`}
      >
        <span className="flex-1">{message}</span>
        <button
          onClick={onClose}
          className="shrink-0 rounded px-1 text-current opacity-60 transition hover:opacity-100"
          aria-label="Dismiss"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

// ── Party-risk rating chip ───────────────────────────────────────────────────
// CRITICAL=rose, HIGH=orange, ELEVATED=amber, WATCH=sky, LOW=slate.
export function RatingChip({ rating }: { rating: string }) {
  const cls =
    rating === "CRITICAL"
      ? "bg-rose-100 text-rose-800 ring-rose-600/20"
      : rating === "HIGH"
        ? "bg-orange-100 text-orange-800 ring-orange-600/20"
        : rating === "ELEVATED"
          ? "bg-amber-100 text-amber-800 ring-amber-600/20"
          : rating === "WATCH"
            ? "bg-sky-100 text-sky-800 ring-sky-600/20"
            : "bg-slate-200 text-slate-600 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${cls}`}
    >
      {rating}
    </span>
  );
}

// ── Horizontal 0–100 bar with a right-aligned numeric read-out ───────────────
// `tone` picks the fill colour scheme: "score" ramps rose→amber→emerald by
// magnitude (higher = worse for risk), "neutral" is a flat slate fill.
export function Bar({
  value,
  tone = "neutral",
  width = "w-24",
}: {
  value: number;
  tone?: "score" | "neutral";
  width?: string;
}) {
  const v = Math.max(0, Math.min(100, value));
  const fill =
    tone === "score"
      ? v >= 55
        ? "bg-rose-500"
        : v >= 35
          ? "bg-amber-500"
          : "bg-emerald-500"
      : "bg-slate-400";
  return (
    <div className="flex items-center gap-2">
      <div className={`h-2 ${width} overflow-hidden rounded-full bg-slate-200`}>
        <div className={`h-full rounded-full ${fill}`} style={{ width: `${v}%` }} />
      </div>
      <span className="tnum w-9 text-right text-xs text-slate-500">
        {Math.round(v)}
      </span>
    </div>
  );
}

// ── Muted "low-n" tag (too few claims to score robustly) ─────────────────────
export function LowNTag() {
  return (
    <span
      title="too few claims to score robustly"
      className="inline-flex items-center rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-400"
    >
      low-n
    </span>
  );
}

// ── Client-side pagination ───────────────────────────────────────────────────
// `usePaged` slices an in-memory list; `<Pagination>` is the matching footer.
// Page auto-clamps when the underlying list shrinks (filter / delete) so the
// caller never renders an out-of-range empty page.
export function usePaged<T>(rows: T[], pageSize = 25) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const clamped = Math.min(page, pageCount - 1);
  const slice = useMemo(
    () => rows.slice(clamped * pageSize, clamped * pageSize + pageSize),
    [rows, clamped, pageSize],
  );
  return { page: clamped, setPage, pageCount, total: rows.length, slice };
}

export function Pagination({
  page,
  pageCount,
  total,
  onPage,
  unit = "rows",
}: {
  page: number;
  pageCount: number;
  total: number;
  onPage: (p: number) => void;
  unit?: string;
}) {
  const btn =
    "rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40";
  return (
    <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
      <span className="tnum">
        {total.toLocaleString("en-ZA")} {unit}
        {pageCount > 1 && ` · page ${page + 1} of ${pageCount}`}
      </span>
      {pageCount > 1 && (
        <div className="flex items-center gap-1">
          <button className={btn} disabled={page <= 0} onClick={() => onPage(0)}>
            «
          </button>
          <button className={btn} disabled={page <= 0} onClick={() => onPage(page - 1)}>
            Prev
          </button>
          <button
            className={btn}
            disabled={page >= pageCount - 1}
            onClick={() => onPage(page + 1)}
          >
            Next
          </button>
          <button
            className={btn}
            disabled={page >= pageCount - 1}
            onClick={() => onPage(pageCount - 1)}
          >
            »
          </button>
        </div>
      )}
    </div>
  );
}
