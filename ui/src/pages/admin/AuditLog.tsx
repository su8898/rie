// The audit log: every change made in Administration and to the practice register. Who, what,
// when. Entries are never edited or removed.

import { Download, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../api";
import { DataTable, Pager, type Column } from "../../ds/DataTable";
import { AUDIT_AREAS, dateTime, describeAudit } from "../../ds/labels";
import { useToast } from "../../ds/overlays";
import { Button, EmptyState, ErrorBlock, Input, Ref, Select } from "../../ds/primitives";
import type { AdminAuditRow } from "../../types";
import { SectionHeader, errorText } from "./shared";

const FILTERS = ["area", "actor", "q", "date_from", "date_to"];
const area = (a: AdminAuditRow) => a.action.split(".")[0];

export default function AuditLogAdmin() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState<AdminAuditRow[]>([]);
  const [total, setTotal] = useState(0);
  const [facets, setFacets] = useState<{ actors: string[]; areas: string[] }>({ actors: [], areas: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);

  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("size"))) ? Number(params.get("size")) : 50;
  const value = (k: string) => params.get(k) ?? "";
  const filters = Object.fromEntries(FILTERS.map((k) => [k, value(k)]));
  const filtered = FILTERS.some((k) => value(k));
  const query = params.toString();
  const set = (changes: Record<string, string | null>, keepPage = false) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v); else next.delete(k);
    }
    if (!keepPage) next.delete("page");
    setParams(next, { replace: true });
  };

  useEffect(() => { api.auditFacets().then(setFacets).catch(() => undefined); }, []);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.auditSearch({ ...filters, limit: pageSize, offset: (page - 1) * pageSize });
      setRows(res.rows);
      setTotal(res.total);
    } catch (e) {
      setError(errorText(e, "The audit log could not be loaded."));
    } finally {
      setLoading(false);
    }
    // `query` is the whole filter and page state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);
  useEffect(() => { void load(); }, [load]);

  async function exportCsv() {
    try {
      const res = await api.auditSearch({ ...filters, limit: 200, offset: 0 });
      const cell = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
      const lines = [["When", "Who", "Area", "Change", "Subject", "Action code", "Detail"].map(cell).join(","),
        ...res.rows.map((a) => [a.at, a.actor, AUDIT_AREAS[area(a)] ?? area(a), describeAudit(a).title, a.target, a.action, JSON.stringify(a.detail ?? {})].map(cell).join(","))];
      const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
      Object.assign(document.createElement("a"), { href: url, download: "audit-log.csv" }).click();
      URL.revokeObjectURL(url);
      toast.success(res.total > res.rows.length ? `Exported the first ${res.rows.length} of ${res.total} entries.` : `Exported ${res.rows.length} entries.`);
    } catch (e) {
      toast.error(errorText(e, "The export failed."));
    }
  }

  const columns: Column<AdminAuditRow>[] = [
    { key: "when", header: "When", width: "170px", render: (a) => <span className="tnum whitespace-nowrap text-ink-700">{dateTime(a.at)}</span> },
    { key: "who", header: "Who", render: (a) => <span className="font-medium text-ink-900">{a.actor}</span> },
    { key: "area", header: "Area", render: (a) => <span className="text-ink-700">{AUDIT_AREAS[area(a)] ?? area(a)}</span> },
    { key: "what", header: "Change", render: (a) => {
      const { title, note } = describeAudit(a);
      return (
        <div>
          <div className="text-ink-900">{title}{a.target && <> <Ref className="text-ink-600">{a.target}</Ref></>}</div>
          {note && <div className="text-[13px] text-ink-500">{note}</div>}
          {expanded === a.id && <pre className="mt-2 max-w-xl overflow-x-auto rounded border border-line bg-ink-50 p-2 text-xs text-ink-700">{a.action}{"\n"}{JSON.stringify(a.detail ?? {}, null, 2)}</pre>}
        </div>
      );
    } },
    { key: "raw", header: "", align: "right", render: (a) => <Button size="sm" variant="ghost" onClick={() => setExpanded(expanded === a.id ? null : a.id)}>{expanded === a.id ? "Hide record" : "Show record"}</Button> },
  ];

  return (
    <div>
      <SectionHeader
        title="Audit log" description="Every change made in Administration and to the practice register: who made it, what changed and when. Entries cannot be edited or removed."
        actions={<Button icon={Download} onClick={exportCsv}>Export</Button>}
      />
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-2 xl:grid-cols-4">
        <Input className="sm:col-span-2" placeholder="Subject, for example a user or a code" aria-label="Search the audit log" value={filters.q} onChange={(e) => set({ q: e.target.value })} />
        <Select aria-label="Area" value={filters.area} onChange={(e) => set({ area: e.target.value })}>
          <option value="">Any area</option>
          {[...new Set([...Object.keys(AUDIT_AREAS), ...facets.areas])].map((k) => <option key={k} value={k}>{AUDIT_AREAS[k] ?? k}</option>)}
        </Select>
        <Select aria-label="Who" value={filters.actor} onChange={(e) => set({ actor: e.target.value })}>
          <option value="">Anyone</option>
          {facets.actors.map((k) => <option key={k} value={k}>{k}</option>)}
        </Select>
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-500 sm:col-span-2 sm:flex-nowrap">
          <span className="shrink-0">From</span>
          <Input type="date" aria-label="From date" value={filters.date_from} onChange={(e) => set({ date_from: e.target.value })} />
          <span>to</span>
          <Input type="date" aria-label="To date" value={filters.date_to} onChange={(e) => set({ date_to: e.target.value })} />
        </div>
        {filtered && <div className="flex items-center sm:col-span-2"><Button size="sm" variant="ghost" icon={X} onClick={() => set(Object.fromEntries(FILTERS.map((k) => [k, null])))}>Clear filters</Button></div>}
      </div>
      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={columns} rows={rows} rowKey={(a) => String(a.id)} loading={loading}
          empty={<EmptyState title={filtered ? "No entry matches" : "Nothing has been changed yet"} body={filtered ? "Change or clear the filters." : "Changes appear here as they are made."} />}
          footer={<Pager page={page} pageSize={pageSize} total={total} unit="entries" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 50 ? null : String(n) })} />}
        />
      )}
    </div>
  );
}
