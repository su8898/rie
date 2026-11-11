// The ready-to-pay list: claims cleared for payment that are not paid yet. Used on the Payments
// page and when adding claims to a run. A claim that cannot be added says why.

import { Link } from "react-router-dom";
import { CLAIM_TYPES, PAYMENT_SOURCES, QUEUE_BLOCKS, shortDate } from "../../ds/labels";
import { Badge, EmptyState, Ref, cx } from "../../ds/primitives";
import { rand } from "../../format";
import type { QueueRow } from "../../types";

export const selectable = (r: QueueRow) => r.blocked === null && r.source !== null && (r.amount ?? 0) > 0;

export function matches(r: QueueRow, q: string): boolean {
  const needle = q.trim().toLowerCase();
  return !needle || r.claim_id.toLowerCase().includes(needle) || r.providers.some((p) => p.toLowerCase().includes(needle));
}

export function ReadyToPayTable({
  rows, selected, onChange, selectableRows = true, emptyBody,
}: {
  rows: QueueRow[]; selected: Set<string>; onChange: (next: Set<string>) => void; selectableRows?: boolean; emptyBody: string;
}) {
  const open = rows.filter(selectable);
  const allOn = open.length > 0 && open.every((r) => selected.has(r.claim_id));
  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    onChange(next);
  };
  const toggleAll = () => {
    const next = new Set(selected);
    for (const r of open) { if (allOn) next.delete(r.claim_id); else next.add(r.claim_id); }
    onChange(next);
  };
  if (rows.length === 0) return <EmptyState title="Nothing is waiting to be paid" body={emptyBody} />;
  const th = "px-4 py-2.5 text-xs font-medium text-ink-500";
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-line bg-ink-50/70 text-left">
            {selectableRows && (
              <th className="w-10 px-4 py-2.5">
                <input type="checkbox" className="h-4 w-4 accent-brand-600" checked={allOn} disabled={open.length === 0} onChange={toggleAll} aria-label="Select every claim that can be paid" />
              </th>
            )}
            <th className={th}>Claim</th>
            <th className={th}>Paid as</th>
            <th className={th}>Billed by</th>
            <th className={th}>Lodged</th>
            <th className={cx(th, "text-right")}>Amount</th>
            <th className={th}>Availability</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => {
            const ok = selectable(r);
            return (
              <tr key={r.claim_id} className={cx("align-top", selected.has(r.claim_id) && "bg-brand-50/50")}>
                {selectableRows && (
                  <td className="px-4 py-3">
                    <input type="checkbox" className="h-4 w-4 accent-brand-600 disabled:opacity-40" checked={selected.has(r.claim_id)} disabled={!ok} onChange={() => toggle(r.claim_id)} aria-label={`Select claim ${r.claim_id}`} />
                  </td>
                )}
                <td className="px-4 py-3">
                  <Link to={`/claims/${encodeURIComponent(r.claim_id)}`} className="font-medium text-brand-700 hover:underline"><Ref>{r.claim_id}</Ref></Link>
                  <div className="text-xs text-ink-500">{r.claim_type ? CLAIM_TYPES[r.claim_type] ?? r.claim_type : "No claim record"}</div>
                </td>
                <td className="px-4 py-3 text-ink-700">{r.source ? PAYMENT_SOURCES[r.source] : "—"}</td>
                <td className="px-4 py-3">{r.providers.length ? <Ref className="text-ink-700">{r.providers.join(", ")}</Ref> : <span className="text-ink-400">—</span>}</td>
                <td className="px-4 py-3 text-ink-700">{shortDate(r.lodged_on)}</td>
                <td className="tnum px-4 py-3 text-right font-medium text-ink-900">{r.amount != null ? rand(r.amount) : "—"}</td>
                <td className="px-4 py-3">
                  {ok ? <Badge tone="ok" dot>Ready</Badge> : r.in_batch ? (
                    <Link to={`/payments/runs/${r.in_batch.id}`} className="text-[13px] text-brand-700 hover:underline">In payment run {r.in_batch.id}</Link>
                  ) : <Badge tone="warn">{QUEUE_BLOCKS[r.blocked ?? ""] ?? "Cannot be paid yet"}</Badge>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
