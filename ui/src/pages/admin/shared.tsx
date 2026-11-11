// Shared pieces of the administration screens: a section heading, a small list loader, the
// recent-changes panel that shows each setting's audit trail, and the error text helper.

import { History } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../../api";
import { dateTime, describeAudit } from "../../ds/labels";
import { EmptyState, Panel, Ref } from "../../ds/primitives";
import type { AdminAuditRow } from "../../types";

export const errorText = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export function SectionHeader({ title, description, actions }: { title: string; description: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 max-w-3xl">
        <h2 className="text-lg font-semibold text-ink-900">{title}</h2>
        <p className="mt-0.5 text-sm text-ink-600">{description}</p>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

/** Load a list once and on demand. `version` changes force a reload. */
export function useList<T>(loader: () => Promise<T[]>, fallback: string) {
  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await loader());
    } catch (e) {
      setError(errorText(e, fallback));
    } finally {
      setLoading(false);
    }
    // The loader is a stable API call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  return { rows, loading, error, reload };
}

/** The last changes made in one area of the settings, from the audit log. */
export function RecentChanges({ area, version }: { area: string; version: number }) {
  const [rows, setRows] = useState<AdminAuditRow[] | null>(null);
  useEffect(() => {
    api.auditSearch({ area, limit: 8 }).then((r) => setRows(r.rows)).catch(() => setRows([]));
  }, [area, version]);
  return (
    <Panel
      title="Recent changes" flush className="mt-4"
      actions={<Link to={`/admin/audit?area=${area}`} className="text-[13px] text-brand-700 hover:underline">Open the audit log</Link>}
    >
      {rows === null ? <div className="px-4 py-6 text-sm text-ink-500">Loading</div> : rows.length === 0 ? (
        <EmptyState icon={History} title="No changes recorded" body="Changes made here are listed with who made them." />
      ) : (
        <ol className="divide-y divide-line">
          {rows.map((a) => {
            const { title, note } = describeAudit(a);
            return (
              <li key={a.id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 px-4 py-2.5">
                <div className="min-w-0 text-sm">
                  <span className="font-medium text-ink-900">{title}</span>
                  {a.target && <> <Ref className="text-ink-600">{a.target}</Ref></>}
                  {note && <span className="ml-2 text-[13px] text-ink-500">{note}</span>}
                </div>
                <div className="text-[13px] text-ink-500">{a.actor} · {dateTime(a.at)}</div>
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}
