// The one table. Sortable headers, a clickable row, loading and empty states, and a pager —
// so every list in the product behaves the same way.

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, ChevronsUpDown } from "lucide-react";
import type { ReactNode } from "react";
import { cx, LoadingBlock } from "./primitives";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
  sortable?: boolean;
  width?: string;
}

export interface Sort { key: string; direction: "asc" | "desc" }

export function DataTable<T>({
  columns, rows, rowKey, sort, onSort, onRowClick, loading, empty, footer,
}: {
  columns: Column<T>[]; rows: T[]; rowKey: (row: T) => string; sort?: Sort; onSort?: (s: Sort) => void;
  onRowClick?: (row: T) => void; loading?: boolean; empty?: ReactNode; footer?: ReactNode;
}) {
  const toggle = (key: string) =>
    onSort?.({ key, direction: sort?.key === key && sort.direction === "desc" ? "asc" : "desc" });
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-white shadow-panel">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line bg-ink-50/70 text-left">
              {columns.map((c) => {
                const active = sort?.key === c.key;
                const Icon = !active ? ChevronsUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;
                return (
                  <th
                    key={c.key} scope="col" style={c.width ? { width: c.width } : undefined}
                    aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}
                    className={cx("px-4 py-2.5 text-xs font-medium text-ink-500", c.align === "right" && "text-right")}
                  >
                    {c.sortable && onSort ? (
                      <button onClick={() => toggle(c.key)} className={cx("inline-flex items-center gap-1 hover:text-ink-900", active && "text-ink-900")}>
                        {c.header} <Icon size={12} aria-hidden />
                      </button>
                    ) : c.header}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className={cx("divide-y divide-line", loading && rows.length > 0 && "opacity-50")}>
            {rows.map((row) => (
              <tr
                key={rowKey(row)} onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cx("align-top transition", onRowClick && "cursor-pointer hover:bg-brand-50/40")}
              >
                {columns.map((c) => (
                  <td key={c.key} className={cx("px-4 py-3", c.align === "right" && "text-right")}>{c.render(row)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {loading && rows.length === 0 ? <LoadingBlock /> : rows.length === 0 ? empty : null}
      {footer && <div className="border-t border-line bg-ink-50/40 px-4 py-2.5">{footer}</div>}
    </div>
  );
}

export function Pager({
  page, pageSize, total, onPage, onPageSize, unit = "rows",
}: { page: number; pageSize: number; total: number; onPage: (p: number) => void; onPageSize?: (n: number) => void; unit?: string }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const btn = "inline-flex h-7 w-7 items-center justify-center rounded border border-line-strong bg-white text-ink-600 transition hover:bg-ink-50 disabled:opacity-40";
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-[13px] text-ink-500">
      <span className="tnum">{from.toLocaleString("en-ZA")} to {Math.min(page * pageSize, total).toLocaleString("en-ZA")} of {total.toLocaleString("en-ZA")} {unit}</span>
      <div className="flex items-center gap-3">
        {onPageSize && (
          <label className="flex items-center gap-1.5">
            Rows
            <select value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))} className="h-7 rounded border border-line-strong bg-white px-1 text-[13px] text-ink-800">
              {[25, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        )}
        <div className="flex items-center gap-1.5">
          <button className={btn} disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page"><ChevronLeft size={14} /></button>
          <span className="tnum">Page {page} of {pages}</span>
          <button className={btn} disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page"><ChevronRight size={14} /></button>
        </div>
      </div>
    </div>
  );
}
