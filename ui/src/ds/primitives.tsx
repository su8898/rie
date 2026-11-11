// The RIE component set. Every rebuilt screen is composed from these, so spacing, type and
// states are decided once. Tones map to meaning (ok / warn / bad / info), never decoration.

import { ChevronRight, Loader2, type LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { Link } from "react-router-dom";
import type { Tone } from "./labels";

export const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

// ── Button ───────────────────────────────────────────────────────────────────
const BTN = {
  primary: "bg-ink-900 text-white hover:bg-ink-800 border-transparent",
  secondary: "bg-white text-ink-800 border-line-strong hover:bg-ink-50",
  ghost: "bg-transparent text-ink-700 border-transparent hover:bg-ink-100",
  danger: "bg-white text-bad-fg border-bad-line hover:bg-bad-bg",
};

export function Button({
  variant = "secondary", size = "md", icon: Icon, loading, children, className, ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof BTN; size?: "sm" | "md"; icon?: LucideIcon; loading?: boolean;
}) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md border font-medium transition",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-8 px-2.5 text-[13px]" : "h-9 px-3.5 text-sm", BTN[variant], className,
      )}
    >
      {loading ? <Loader2 size={15} className="animate-spin" aria-hidden /> : Icon ? <Icon size={15} aria-hidden /> : null}
      {children}
    </button>
  );
}

// ── Badge ────────────────────────────────────────────────────────────────────
const TONES: Record<Tone, string> = {
  ok: "bg-ok-bg text-ok-fg border-ok-line",
  warn: "bg-warn-bg text-warn-fg border-warn-line",
  bad: "bg-bad-bg text-bad-fg border-bad-line",
  info: "bg-info-bg text-info-fg border-info-line",
  neutral: "bg-ink-100 text-ink-600 border-line",
  brand: "bg-brand-50 text-brand-700 border-brand-200",
};
const DOTS: Record<Tone, string> = {
  ok: "bg-ok-fg", warn: "bg-warn-fg", bad: "bg-bad-fg", info: "bg-info-fg", neutral: "bg-ink-400", brand: "bg-brand-500",
};

export function Badge({ tone = "neutral", dot, children }: { tone?: Tone; dot?: boolean; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-xs font-medium leading-5", TONES[tone])}>
      {dot && <span className={cx("h-1.5 w-1.5 rounded-full", DOTS[tone])} aria-hidden />}
      {children}
    </span>
  );
}

/** An identifier: monospaced, so references line up and read as references. */
export function Ref({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cx("font-mono text-[13px] tracking-tight", className)}>{children}</span>;
}

// ── Page header ──────────────────────────────────────────────────────────────
export interface Crumb { label: string; to?: string }

export function PageHeader({
  crumbs, title, meta, subtitle, actions,
}: { crumbs: Crumb[]; title: ReactNode; meta?: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="mb-5 animate-rise">
      <nav aria-label="Breadcrumb" className="mb-1.5 flex items-center gap-1 text-xs text-ink-500">
        {crumbs.map((c, i) => (
          <span key={c.label} className="flex items-center gap-1">
            {i > 0 && <ChevronRight size={12} className="text-ink-300" aria-hidden />}
            {c.to ? <Link to={c.to} className="hover:text-ink-900 hover:underline">{c.label}</Link> : <span>{c.label}</span>}
          </span>
        ))}
      </nav>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-[26px] font-semibold leading-tight tracking-tight text-ink-900">{title}</h1>
            {meta}
          </div>
          {subtitle && <p className="mt-1 max-w-3xl text-sm text-ink-500">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

// ── Panel ────────────────────────────────────────────────────────────────────
export function Panel({
  title, description, actions, children, flush, className,
}: { title?: ReactNode; description?: ReactNode; actions?: ReactNode; children: ReactNode; flush?: boolean; className?: string }) {
  return (
    <section className={cx("rounded-lg border border-line bg-white shadow-panel", className)}>
      {(title || actions) && (
        <div className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink-900">{title}</h2>}
            {description && <p className="mt-0.5 text-[13px] text-ink-500">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={flush ? "" : "p-4"}>{children}</div>
    </section>
  );
}

// ── Stat ─────────────────────────────────────────────────────────────────────
export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone }) {
  return (
    <div className="rounded-lg border border-line bg-white px-4 py-3 shadow-panel">
      <div className="text-xs font-medium text-ink-500">{label}</div>
      <div className={cx("tnum mt-1 text-xl font-semibold tracking-tight", tone === "bad" ? "text-bad-fg" : tone === "ok" ? "text-ok-fg" : "text-ink-900")}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-ink-500">{hint}</div>}
    </div>
  );
}

// ── Tabs ─────────────────────────────────────────────────────────────────────
export function Tabs<T extends string>({
  tabs, value, onChange,
}: { tabs: { key: T; label: string; count?: number }[]; value: T; onChange: (k: T) => void }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((t) => (
        <button
          key={t.key} role="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)}
          className={cx(
            "-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition",
            value === t.key ? "border-brand-500 text-ink-900" : "border-transparent text-ink-500 hover:text-ink-800",
          )}
        >
          {t.label}
          {t.count != null && (
            <span className={cx("tnum rounded px-1.5 text-xs", value === t.key ? "bg-brand-50 text-brand-700" : "bg-ink-100 text-ink-500")}>{t.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

// ── Form controls ────────────────────────────────────────────────────────────
const CONTROL =
  "h-9 w-full rounded-md border border-line-strong bg-white px-2.5 text-sm text-ink-900 placeholder:text-ink-400 " +
  "transition focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 disabled:bg-ink-50 disabled:text-ink-400";

export function Field({
  label, hint, error, required, children, className,
}: { label: string; hint?: ReactNode; error?: string | null; required?: boolean; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <span className="mb-1 flex items-baseline gap-1 text-[13px] font-medium text-ink-700">
        {label}
        {required && <span className="text-bad-fg" aria-hidden>*</span>}
      </span>
      {children}
      {error ? <span className="mt-1 block text-xs text-bad-fg">{error}</span> : hint ? <span className="mt-1 block text-xs text-ink-500">{hint}</span> : null}
    </label>
  );
}

export function Input({ invalid, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return <input {...rest} className={cx(CONTROL, invalid && "border-bad-fg focus:border-bad-fg focus:ring-bad-bg", className)} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...rest} className={cx(CONTROL, "pr-7", className)}>{children}</select>;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={cx(CONTROL, "h-auto py-2 leading-relaxed", className)} />;
}

export function Checkbox({ label, hint, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 rounded-md border border-line px-3 py-2.5 transition hover:border-line-strong has-[:checked]:border-brand-200 has-[:checked]:bg-brand-50/50">
      <input type="checkbox" {...rest} className="mt-0.5 h-4 w-4 rounded border-line-strong accent-[#12807a]" />
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink-800">{label}</span>
        {hint && <span className="block text-xs text-ink-500">{hint}</span>}
      </span>
    </label>
  );
}

// ── States ───────────────────────────────────────────────────────────────────
export function EmptyState({ icon: Icon, title, body, action }: { icon?: LucideIcon; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      {Icon && <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-ink-100 text-ink-500"><Icon size={18} aria-hidden /></div>}
      <div className="text-sm font-semibold text-ink-900">{title}</div>
      {body && <p className="mt-1 max-w-sm text-[13px] text-ink-500">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 px-6 py-12 text-sm text-ink-500" role="status">
      <Loader2 size={16} className="animate-spin" aria-hidden /> {label}…
    </div>
  );
}

export function ErrorBlock({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-bad-line bg-bad-bg px-4 py-3 text-sm text-bad-fg" role="alert">
      <span>{message}</span>
      {onRetry && <Button size="sm" variant="secondary" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

/** Label and value pairs for a record's facts. */
export function Facts({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
      {items.map((it) => (
        <div key={it.label} className="min-w-0">
          <dt className="text-xs text-ink-500">{it.label}</dt>
          <dd className="mt-0.5 truncate text-sm text-ink-900">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}
