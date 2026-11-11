// Claims worklist. One row per claim with its status in plain language, who billed, what was
// billed and what is payable. Filters, sort order and page live in the URL, so a view can be
// bookmarked or sent to a colleague, and the global search lands here.

import { Download, FileText, Plus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, Pager, type Column, type Sort } from "../ds/DataTable";
import { CLAIM_TYPES, claimStatus, DISPOSITIONS, RISK, shortDate } from "../ds/labels";
import { useToast } from "../ds/overlays";
import { Badge, Button, cx, EmptyState, ErrorBlock, Input, PageHeader, Ref, Select } from "../ds/primitives";
import { rand } from "../format";
import type { ClaimRow } from "../types";

// Saved views: the questions a handler opens this page to answer.
const VIEWS: { key: string; label: string; params: Record<string, string> }[] = [
  { key: "all", label: "All claims", params: {} },
  { key: "ready", label: "Ready to pay", params: { eligible: "true" } },
  { key: "held", label: "Held", params: { eligible: "false" } },
  { key: "review", label: "Pricing review", params: { needs_review: "true" } },
  { key: "fraud", label: "Fraud review", params: { disposition: "FRAUD" } },
];
const VIEW_KEYS = ["eligible", "needs_review", "disposition"];
const FILTER_KEYS = ["q", "claim_type", "band", "disposition", "provider_id", "lodged_from", "lodged_to", "eligible", "needs_review"];

const COLUMNS: Column<ClaimRow>[] = [
  {
    key: "claim", header: "Claim", sortable: true, width: "20%",
    render: (r) => (
      <div>
        <Ref className="font-medium text-brand-700">{r.claim_id}</Ref>
        <div className="mt-0.5 text-xs text-ink-500">{r.claim_type ? CLAIM_TYPES[r.claim_type] ?? r.claim_type : "No claim record"}</div>
      </div>
    ),
  },
  {
    key: "lodged", header: "Lodged", sortable: true,
    render: (r) => <span className="whitespace-nowrap text-ink-700">{shortDate(r.lodged_on)}</span>,
  },
  {
    key: "provider", header: "Billed by",
    render: (r) =>
      r.providers.length === 0 ? <span className="text-ink-400">—</span> : (
        <div><Ref>{r.providers[0]}</Ref>{r.providers.length > 1 && <span className="ml-1.5 text-xs text-ink-500">+{r.providers.length - 1} more</span>}</div>
      ),
  },
  { key: "status", header: "Status", render: (r) => { const s = claimStatus(r); return <Badge tone={s.tone} dot>{s.label}</Badge>; } },
  { key: "score", header: "Risk", sortable: true, render: (r) => <Badge tone={RISK[r.band].tone}>{RISK[r.band].label}</Badge> },
  { key: "billed", header: "Billed", align: "right", render: (r) => <span className="tnum text-ink-600">{rand(r.billed)}</span> },
  {
    key: "payable", header: "Payable", align: "right", sortable: true,
    render: (r) => (
      <div>
        <span className="tnum font-semibold text-ink-900">{rand(r.net_payable)}</span>
        {r.billed > r.net_payable && <div className="tnum text-xs text-bad-fg">−{rand(r.billed - r.net_payable)}</div>}
      </div>
    ),
  },
];

function toCsv(rows: ClaimRow[]): string {
  const cell = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const head = ["Claim", "Type", "Lodged", "Accident date", "Billed by", "Status", "Risk", "Billed", "Payable", "Eligible to pay"];
  const body = rows.map((r) => [
    r.claim_id, r.claim_type ? CLAIM_TYPES[r.claim_type] ?? r.claim_type : "", r.lodged_on ?? "", r.accident_date ?? "",
    r.providers.join("; "), claimStatus(r).label, RISK[r.band].label, r.billed.toFixed(2), r.net_payable.toFixed(2), r.eligible_to_pay ? "Yes" : "No",
  ].map(cell).join(","));
  return [head.map(cell).join(","), ...body].join("\n");
}

export default function ClaimsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState<ClaimRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("size"))) ? Number(params.get("size")) : 25;
  const sort: Sort = { key: params.get("sort") ?? "received", direction: params.get("dir") === "asc" ? "asc" : "desc" };
  const value = (k: string) => params.get(k) ?? "";
  const canCreate = user?.role === "HANDLER" || user?.role === "MEDICAL_OFFICER";
  const filters = Object.fromEntries(FILTER_KEYS.map((k) => [k, value(k)]));
  const query = params.toString();

  const set = (changes: Record<string, string | null>, keepPage = false) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v); else next.delete(k);
    }
    if (!keepPage) next.delete("page");
    setParams(next, { replace: true });
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.claimsWorklist({ ...filters, sort: sort.key, direction: sort.direction, limit: pageSize, offset: (page - 1) * pageSize });
      setRows(res.rows);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The claims list could not be loaded.");
    } finally {
      setLoading(false);
    }
    // `query` is the whole filter, sort and page state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);

  useEffect(() => { void load(); }, [load]);

  const activeView = VIEWS.find((v) => VIEW_KEYS.every((k) => (v.params[k] ?? "") === value(k)))?.key;
  const filtered = FILTER_KEYS.some((k) => value(k));

  async function exportCsv() {
    setExporting(true);
    try {
      const res = await api.claimsWorklist({ ...filters, sort: sort.key, direction: sort.direction, limit: 200, offset: 0 });
      const url = URL.createObjectURL(new Blob([toCsv(res.rows)], { type: "text/csv" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: "claims.csv" });
      a.click();
      URL.revokeObjectURL(url);
      toast.success(res.total > res.rows.length ? `Exported the first ${res.rows.length} of ${res.total} claims.` : `Exported ${res.rows.length} claims.`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "The export failed.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Work" }, { label: "Claims" }]}
        title="Claims"
        subtitle="Every claim and invoice the Fund has received, with its current status and what is payable."
        actions={<>
          <Button icon={Download} onClick={exportCsv} loading={exporting}>Export</Button>
          {canCreate && <Button variant="primary" icon={Plus} onClick={() => navigate("/claims/new")}>New claim</Button>}
        </>}
      />

      <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Saved views">
        {VIEWS.map((v) => (
          <button
            key={v.key} role="tab" aria-selected={activeView === v.key}
            onClick={() => set(Object.fromEntries(VIEW_KEYS.map((k) => [k, v.params[k] ?? null])))}
            className={cx(
              "rounded-full border px-3 py-1.5 text-[13px] font-medium transition",
              activeView === v.key ? "border-ink-900 bg-ink-900 text-white" : "border-line-strong bg-white text-ink-600 hover:border-ink-400 hover:text-ink-900",
            )}
          >
            {v.label}
          </button>
        ))}
      </div>

      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-2 lg:grid-cols-6">
        <Input className="lg:col-span-2" placeholder="Reference, accident or claimant" aria-label="Search" value={value("q")} onChange={(e) => set({ q: e.target.value })} />
        <Select aria-label="Claim type" value={value("claim_type")} onChange={(e) => set({ claim_type: e.target.value })}>
          <option value="">Any type</option>
          {Object.entries(CLAIM_TYPES).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </Select>
        <Select aria-label="Risk" value={value("band")} onChange={(e) => set({ band: e.target.value })}>
          <option value="">Any risk</option>
          {Object.entries(RISK).map(([k, r]) => <option key={k} value={k}>{r.label} risk</option>)}
        </Select>
        <Select aria-label="Status" value={value("disposition")} onChange={(e) => set({ disposition: e.target.value })}>
          <option value="">Any status</option>
          {Object.entries(DISPOSITIONS).map(([k, d]) => <option key={k} value={k}>{d.label}</option>)}
        </Select>
        <Input placeholder="Practice number" aria-label="Billed by" value={value("provider_id")} onChange={(e) => set({ provider_id: e.target.value })} />
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-500 sm:flex-nowrap lg:col-span-2">
          <span className="shrink-0">Lodged from</span>
          <Input type="date" aria-label="Lodged from" value={value("lodged_from")} onChange={(e) => set({ lodged_from: e.target.value })} />
          <span>to</span>
          <Input type="date" aria-label="Lodged to" value={value("lodged_to")} onChange={(e) => set({ lodged_to: e.target.value })} />
        </div>
        {filtered && (
          <div className="flex items-center lg:col-span-4">
            <Button size="sm" variant="ghost" icon={X} onClick={() => setParams(new URLSearchParams(), { replace: true })}>Clear filters</Button>
          </div>
        )}
      </div>

      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={COLUMNS} rows={rows} rowKey={(r) => r.claim_id} loading={loading}
          sort={sort} onSort={(s) => set({ sort: s.key, dir: s.direction })}
          onRowClick={(r) => navigate(`/claims/${encodeURIComponent(r.claim_id)}`)}
          empty={
            <EmptyState
              icon={FileText} title={filtered ? "No claims match these filters" : "No claims yet"}
              body={filtered ? "Widen the filters, or clear them to see every claim." : "Claims appear here as soon as they are submitted."}
              action={filtered ? <Button onClick={() => setParams(new URLSearchParams(), { replace: true })}>Clear filters</Button> : undefined}
            />
          }
          footer={<Pager page={page} pageSize={pageSize} total={total} unit="claims" onPage={(p) => set({ page: String(p) }, true)} onPageSize={(n) => set({ size: String(n) })} />}
        />
      )}
    </div>
  );
}
