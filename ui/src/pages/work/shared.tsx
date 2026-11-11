// Pieces the case and dispute screens share: the view pills, the URL-backed list state, and the
// history panel that reads an item's transition log in plain words.

import { History } from "lucide-react";
import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { dateTime } from "../../ds/labels";
import { EmptyState, Panel, cx } from "../../ds/primitives";
import type { HistoryEntry } from "../../types";

export interface View { key: string; label: string; count?: number; alert?: boolean }

export function ViewPills({ views, value, onChange, label }: { views: View[]; value: string; onChange: (k: string) => void; label: string }) {
  return (
    <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label={label}>
      {views.map((v) => (
        <button
          key={v.key || "default"} role="tab" aria-selected={value === v.key} onClick={() => onChange(v.key)}
          className={cx("rounded-full border px-3 py-1.5 text-[13px] font-medium transition", value === v.key ? "border-ink-900 bg-ink-900 text-white" : "border-line-strong bg-white text-ink-600 hover:border-ink-400 hover:text-ink-900")}
        >
          {v.label}
          {v.count != null && <span className={cx("tnum ml-1.5", v.alert && v.count > 0 && value !== v.key ? "font-semibold text-bad-fg" : "opacity-70")}>{v.count}</span>}
        </button>
      ))}
    </div>
  );
}

/** Filters, sort and page kept in the page address, so a list can be bookmarked or shared. */
export function useListParams(defaultSize = 25) {
  const [params, setParams] = useSearchParams();
  const value = (k: string) => params.get(k) ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("size"))) ? Number(params.get("size")) : defaultSize;
  const set = (changes: Record<string, string | null>, keepPage = false) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v); else next.delete(k);
    }
    if (!keepPage) next.delete("page");
    setParams(next, { replace: true });
  };
  const reset = (keep: Record<string, string> = {}) => setParams(keep, { replace: true });
  return { params, value, page, pageSize, set, reset, query: params.toString() };
}

export function HistoryPanel({ entries, describe }: { entries: HistoryEntry[]; describe: (h: HistoryEntry) => { title: string; note?: ReactNode } }) {
  return (
    <Panel title="History" description="Every step and every change, with who made it." flush>
      {entries.length === 0 ? <EmptyState icon={History} title="Nothing has happened yet" body="Steps taken on this item are listed here." /> : (
        <ol className="divide-y divide-line">
          {entries.map((h, i) => {
            const { title, note } = describe(h);
            return (
              <li key={i} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink-900">{title}</div>
                  {note && <div className="text-[13px] text-ink-600">{note}</div>}
                </div>
                <div className="text-[13px] text-ink-500">{h.actor} · {dateTime(h.at)}</div>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}
