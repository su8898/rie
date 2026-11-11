// Payments. Three lists behind one page: payment runs, claims that are ready to pay, and the
// remittance advice sent to practices. A run is assembled by one person, approved by a second
// and released by a third; each run opens as its own record.

import { Plus, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, Pager, type Column } from "../ds/DataTable";
import { REMITTANCE_STATUS, RUN_STATUS, dateTime, paymentError, shortDate } from "../ds/labels";
import { Dialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, PageHeader, Ref, Select, Stat, Tabs, Textarea, cx } from "../ds/primitives";
import { rand } from "../format";
import type { BatchStatus, QueueRow, RemittanceSummary, RunSummary } from "../types";
import { ReadyToPayTable, matches, selectable } from "./payments/ReadyToPay";

type Tab = "runs" | "ready" | "advice";
const STATUSES: BatchStatus[] = ["OPEN", "APPROVED", "PAID", "CANCELLED"];
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? paymentError(e.message) : fallback);

export default function PaymentsPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "ready" ? "ready" : params.get("tab") === "advice" ? "advice" : "runs";
  const canAssemble = user?.role === "HANDLER" || user?.role === "ADMIN";

  const [queue, setQueue] = useState<QueueRow[] | null>(null);
  const [counts, setCounts] = useState<Record<BatchStatus, number> | null>(null);
  const [creating, setCreating] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);

  const loadQueue = useCallback(() => {
    api.paymentsQueue().then(setQueue).catch(() => setQueue([]));
  }, []);
  useEffect(() => { loadQueue(); }, [loadQueue, version]);

  const ready = useMemo(() => (queue ?? []).filter(selectable), [queue]);
  const readyTotal = ready.reduce((s, r) => s + (r.amount ?? 0), 0);

  const set = (changes: Record<string, string | null>, keepPage = false) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v); else next.delete(k);
    }
    if (!keepPage) next.delete("page");
    setParams(next, { replace: true });
  };

  async function createRun() {
    setBusy(true);
    try {
      const run = await api.createBatch(note.trim() || undefined);
      toast.success(`Payment run ${run.id} created.`);
      navigate(`/payments/runs/${run.id}`);
    } catch (e) {
      toast.error(message(e, "The payment run could not be created."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Finance" }, { label: "Payments" }]}
        title="Payments"
        subtitle="Assemble a payment run, have it approved and released, and send each practice its remittance advice."
        actions={canAssemble && <Button variant="primary" icon={Plus} onClick={() => { setNote(""); setCreating(true); }}>New payment run</Button>}
      />

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Ready to pay" value={queue ? rand(readyTotal) : "…"} hint={queue ? `${ready.length} claim${ready.length === 1 ? "" : "s"} not in a run` : undefined} tone={ready.length ? "ok" : undefined} />
        <Stat label="Being assembled" value={counts ? counts.OPEN : "…"} hint="Runs that can still be changed" />
        <Stat label="Awaiting release" value={counts ? counts.APPROVED : "…"} hint="Approved, not yet paid" tone={counts?.APPROVED ? "warn" : undefined} />
        <Stat label="Paid" value={counts ? counts.PAID : "…"} hint="Runs released" />
      </div>

      <Tabs<Tab>
        tabs={[
          { key: "runs", label: "Payment runs", count: counts ? STATUSES.reduce((s, k) => s + counts[k], 0) : undefined },
          { key: "ready", label: "Ready to pay", count: queue?.length },
          { key: "advice", label: "Remittance advice" },
        ]}
        value={tab} onChange={(k) => setParams(k === "runs" ? {} : { tab: k }, { replace: true })}
      />

      <div className="mt-4">
        {tab === "runs" && <RunsTab params={params} set={set} onCounts={setCounts} version={version} />}
        {tab === "ready" && (
          <ReadyTab queue={queue} canAssemble={canAssemble} onDone={() => setVersion((v) => v + 1)} />
        )}
        {tab === "advice" && <AdviceTab params={params} set={set} />}
      </div>
      {tab !== "runs" && <CountsLoader onCounts={setCounts} version={version} />}

      <Dialog
        open={creating} onClose={() => setCreating(false)} title="New payment run"
        description="You assemble the run. A second administrator approves it and a third releases the payment."
        footer={<><Button onClick={() => setCreating(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={createRun}>Create run</Button></>}
      >
        <Field label="Note" hint="Optional. For example the payment date or the period this run covers.">
          <Textarea rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </Dialog>
    </div>
  );
}

/** Keeps the header figures current while another tab is showing. */
function CountsLoader({ onCounts, version }: { onCounts: (c: Record<BatchStatus, number>) => void; version: number }) {
  useEffect(() => {
    api.paymentRuns({ limit: 1 }).then((r) => onCounts(r.counts)).catch(() => undefined);
  }, [onCounts, version]);
  return null;
}

// ── Payment runs ─────────────────────────────────────────────────────────────
function RunsTab({
  params, set, onCounts, version,
}: {
  params: URLSearchParams; set: (c: Record<string, string | null>, keepPage?: boolean) => void;
  onCounts: (c: Record<BatchStatus, number>) => void; version: number;
}) {
  const navigate = useNavigate();
  const [rows, setRows] = useState<RunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<Record<BatchStatus, number> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("size"))) ? Number(params.get("size")) : 25;
  const status = params.get("status") ?? "";
  const q = params.get("q") ?? "";
  const direction = params.get("dir") === "asc" ? "asc" : "desc";

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.paymentRuns({ status, q, direction, limit: pageSize, offset: (page - 1) * pageSize });
      setRows(res.rows);
      setTotal(res.total);
      setCounts(res.counts);
      onCounts(res.counts);
    } catch (e) {
      setError(message(e, "The payment runs could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [status, q, direction, page, pageSize, onCounts]);
  useEffect(() => { void load(); }, [load, version]);

  const all = counts ? STATUSES.reduce((s, k) => s + counts[k], 0) : undefined;
  const views: { key: string; label: string; count?: number }[] = [
    { key: "", label: "All runs", count: all },
    ...STATUSES.map((k) => ({ key: k, label: RUN_STATUS[k].label, count: counts?.[k] })),
  ];
  const columns: Column<RunSummary>[] = [
    { key: "created", header: "Run", sortable: true, render: (r) => (
      <div>
        <div className="font-medium text-ink-900">Payment run {r.id}</div>
        <div className="max-w-[28ch] truncate text-xs text-ink-500">{r.note || "No note"}</div>
      </div>
    ) },
    { key: "when", header: "Created", render: (r) => <div><div className="text-ink-800">{shortDate(r.created_at)}</div><div className="text-xs text-ink-500">by {r.created_by}</div></div> },
    { key: "status", header: "Status", render: (r) => <Badge tone={RUN_STATUS[r.status].tone} dot>{RUN_STATUS[r.status].label}</Badge> },
    { key: "claims", header: "Claims", align: "right", render: (r) => <span className="tnum text-ink-800">{r.n_claims}</span> },
    { key: "total", header: "Total", align: "right", render: (r) => <span className="tnum font-medium text-ink-900">{rand(r.total)}</span> },
    { key: "approved", header: "Approved by", render: (r) => r.approved_by ?? <span className="text-ink-400">—</span> },
    { key: "paid", header: "Released", render: (r) => r.paid_by ? <div><div className="text-ink-800">{shortDate(r.paid_at)}</div><div className="text-xs text-ink-500">by {r.paid_by}</div></div> : <span className="text-ink-400">—</span> },
  ];

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Run status">
          {views.map((v) => (
            <button
              key={v.key || "all"} role="tab" aria-selected={status === v.key} onClick={() => set({ status: v.key || null })}
              className={cx("rounded-full border px-3 py-1.5 text-[13px] font-medium transition", status === v.key ? "border-ink-900 bg-ink-900 text-white" : "border-line-strong bg-white text-ink-600 hover:border-ink-400 hover:text-ink-900")}
            >
              {v.label}{v.count != null && <span className="tnum ml-1.5 opacity-70">{v.count}</span>}
            </button>
          ))}
        </div>
        <div className="ml-auto flex w-full items-center gap-2 sm:w-72">
          <Input placeholder="Run number, note, person or claim" aria-label="Search payment runs" value={q} onChange={(e) => set({ q: e.target.value })} />
          {(q || status) && <Button size="sm" variant="ghost" icon={X} onClick={() => set({ q: null, status: null })}>Clear</Button>}
        </div>
      </div>
      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={columns} rows={rows} rowKey={(r) => String(r.id)} loading={loading}
          sort={{ key: "created", direction }} onSort={(s) => set({ dir: s.direction === "asc" ? "asc" : null }, true)}
          onRowClick={(r) => navigate(`/payments/runs/${r.id}`)}
          empty={<EmptyState title={q || status ? "No payment run matches" : "No payment runs yet"} body={q || status ? "Change the search or the status." : "Create a payment run to start paying the claims that are ready."} />}
          footer={<Pager page={page} pageSize={pageSize} total={total} unit="runs" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
        />
      )}
    </>
  );
}

// ── Ready to pay ─────────────────────────────────────────────────────────────
function ReadyTab({ queue, canAssemble, onDone }: { queue: QueueRow[] | null; canAssemble: boolean; onDone: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [choosing, setChoosing] = useState(false);
  const [openRuns, setOpenRuns] = useState<RunSummary[]>([]);
  const [target, setTarget] = useState("new");
  const [busy, setBusy] = useState(false);

  const rows = useMemo(() => (queue ?? []).filter((r) => matches(r, q)), [queue, q]);
  const picked = (queue ?? []).filter((r) => selected.has(r.claim_id));
  const pickedTotal = picked.reduce((s, r) => s + (r.amount ?? 0), 0);

  async function openChooser() {
    setChoosing(true);
    try {
      const res = await api.paymentRuns({ status: "OPEN", limit: 100 });
      setOpenRuns(res.rows);
      setTarget(res.rows.length ? String(res.rows[0].id) : "new");
    } catch {
      setOpenRuns([]);
      setTarget("new");
    }
  }

  async function addToRun() {
    setBusy(true);
    try {
      const runId = target === "new" ? (await api.createBatch()).id : Number(target);
      const failed: string[] = [];
      for (const r of picked) {
        try {
          await api.addInstruction(runId, { claim_id: r.claim_id, source: r.source! });
        } catch (e) {
          failed.push(`${r.claim_id}: ${message(e, "could not be added")}`);
        }
      }
      const added = picked.length - failed.length;
      if (added) toast.success(`${added} claim${added === 1 ? "" : "s"} added to payment run ${runId}.`);
      failed.forEach((m) => toast.error(m));
      setSelected(new Set());
      setChoosing(false);
      onDone();
      navigate(`/payments/runs/${runId}`);
    } catch (e) {
      toast.error(message(e, "The claims could not be added."));
    } finally {
      setBusy(false);
    }
  }

  if (queue === null) return <div className="rounded-lg border border-line bg-white px-4 py-10 text-center text-sm text-ink-500 shadow-panel">Loading</div>;
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="w-full sm:w-72"><Input placeholder="Claim reference or practice number" aria-label="Search claims ready to pay" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <span className="text-[13px] text-ink-500">{rows.length} of {queue.length} claims</span>
        {canAssemble && (
          <div className="ml-auto flex items-center gap-3">
            {picked.length > 0 && <span className="tnum text-[13px] text-ink-700">{picked.length} selected, {rand(pickedTotal)}</span>}
            <Button variant="primary" disabled={picked.length === 0} onClick={openChooser}>Add to a payment run</Button>
          </div>
        )}
      </div>
      <div className="overflow-hidden rounded-lg border border-line bg-white shadow-panel">
        <ReadyToPayTable rows={rows} selected={selected} onChange={setSelected} selectableRows={canAssemble} emptyBody={q ? "No claim matches the search." : "Claims appear here once they are cleared for payment."} />
      </div>

      <Dialog
        open={choosing} onClose={() => setChoosing(false)} title="Add to a payment run"
        description={`${picked.length} claim${picked.length === 1 ? "" : "s"}, ${rand(pickedTotal)} in total.`}
        footer={<><Button onClick={() => setChoosing(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={addToRun}>Add claims</Button></>}
      >
        <Field label="Payment run" hint="Only runs that are still being assembled can take more claims.">
          <Select value={target} onChange={(e) => setTarget(e.target.value)}>
            {openRuns.map((r) => <option key={r.id} value={r.id}>Payment run {r.id}{r.note ? `: ${r.note}` : ""} ({r.n_claims} claim{r.n_claims === 1 ? "" : "s"}, {rand(r.total)})</option>)}
            <option value="new">A new payment run</option>
          </Select>
        </Field>
      </Dialog>
    </>
  );
}

// ── Remittance advice ────────────────────────────────────────────────────────
function AdviceTab({ params, set }: { params: URLSearchParams; set: (c: Record<string, string | null>, keepPage?: boolean) => void }) {
  const navigate = useNavigate();
  const [rows, setRows] = useState<RemittanceSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("size"))) ? Number(params.get("size")) : 25;
  const value = (k: string) => params.get(k) ?? "";
  const filters = { q: value("q"), status: value("status"), provider_id: value("provider_id"), date_from: value("date_from"), date_to: value("date_to") };
  const key = JSON.stringify(filters);
  const filtered = Object.values(filters).some(Boolean);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.remittanceSearch({ ...filters, limit: pageSize, offset: (page - 1) * pageSize });
      setRows(res.rows);
      setTotal(res.total);
    } catch (e) {
      setError(message(e, "The remittance advice could not be loaded."));
    } finally {
      setLoading(false);
    }
    // `key` is the whole filter state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, page, pageSize]);
  useEffect(() => { void load(); }, [load]);

  const columns: Column<RemittanceSummary>[] = [
    { key: "ref", header: "Advice", render: (r) => <div><Ref className="font-medium text-brand-700">{r.ref}</Ref><div className="text-xs text-ink-500">Issued {dateTime(r.issued_at)}</div></div> },
    { key: "practice", header: "Practice", render: (r) => <Ref className="text-ink-800">{r.provider_id}</Ref> },
    { key: "run", header: "Payment run", render: (r) => <span className="tnum text-ink-700">{r.batch_id}</span> },
    { key: "period", header: "Service period", render: (r) => <span className="text-ink-700">{r.period_from ? `${shortDate(r.period_from)} to ${shortDate(r.period_to)}` : "—"}</span> },
    { key: "claims", header: "Claims", align: "right", render: (r) => <span className="tnum">{r.n_claims}</span> },
    { key: "billed", header: "Billed", align: "right", render: (r) => <span className="tnum text-ink-600">{rand(r.total_billed)}</span> },
    { key: "paid", header: "Paid", align: "right", render: (r) => (
      <div><div className="tnum font-medium text-ink-900">{rand(r.total_paid)}</div>{r.total_reduced > 0 && <div className="tnum text-xs text-bad-fg">−{rand(r.total_reduced)}</div>}</div>
    ) },
    { key: "status", header: "Status", render: (r) => <Badge tone={REMITTANCE_STATUS[r.status]?.tone ?? "neutral"} dot>{REMITTANCE_STATUS[r.status]?.label ?? r.status}</Badge> },
  ];

  return (
    <>
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-2 lg:grid-cols-6">
        <Input className="lg:col-span-2" placeholder="Advice reference, practice or claim" aria-label="Search remittance advice" value={filters.q} onChange={(e) => set({ q: e.target.value })} />
        <Input placeholder="Practice number" aria-label="Practice number" value={filters.provider_id} onChange={(e) => set({ provider_id: e.target.value })} />
        <Select aria-label="Status" value={filters.status} onChange={(e) => set({ status: e.target.value })}>
          <option value="">Any status</option>
          {Object.entries(REMITTANCE_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </Select>
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-ink-500 sm:flex-nowrap lg:col-span-2">
          <span className="shrink-0">Services from</span>
          <Input type="date" aria-label="Services from" value={filters.date_from} onChange={(e) => set({ date_from: e.target.value })} />
          <span>to</span>
          <Input type="date" aria-label="Services to" value={filters.date_to} onChange={(e) => set({ date_to: e.target.value })} />
        </div>
        {filtered && (
          <div className="flex items-center lg:col-span-6">
            <Button size="sm" variant="ghost" icon={X} onClick={() => set({ q: null, status: null, provider_id: null, date_from: null, date_to: null })}>Clear filters</Button>
          </div>
        )}
      </div>
      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={columns} rows={rows} rowKey={(r) => r.ref} loading={loading}
          onRowClick={(r) => navigate(`/payments/remittances/${encodeURIComponent(r.ref)}`)}
          empty={<EmptyState title={filtered ? "No remittance advice matches" : "No remittance advice yet"} body={filtered ? "Change or clear the filters." : "An advice is issued to each practice when a payment run is released."} />}
          footer={<Pager page={page} pageSize={pageSize} total={total} unit="advices" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
        />
      )}
    </>
  );
}
