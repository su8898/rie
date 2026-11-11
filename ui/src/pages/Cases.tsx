// Cases. Review and investigation work: a pricing question for a handler, a fraud hold or a
// recovery for an investigator. The worklist opens on what is still open; each case is a record.

import { Plus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { DataTable, Pager, type Column, type Sort } from "../ds/DataTable";
import { CASE_LANES, CASE_PRIORITIES, CASE_STATUS, CASE_VERDICTS, dueText, workError } from "../ds/labels";
import { Dialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, PageHeader, Ref, Select, Stat, Textarea, cx } from "../ds/primitives";
import { rand } from "../format";
import type { CaseAnalytics, CaseItem, CaseSearch } from "../types";
import { ViewPills, useListParams } from "./work/shared";

const VIEW_PARAMS: Record<string, Record<string, string | boolean>> = {
  "": { open_only: true }, mine: { mine: true }, unassigned: { status: "OPEN" }, overdue: { overdue: true },
  escalated: { status: "ESCALATED" }, closed: { status: "CLOSED" }, all: {},
};
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? workError(e.message) : fallback);

export default function CasesPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const { value, page, pageSize, set, reset, query } = useListParams();
  const [data, setData] = useState<CaseSearch | null>(null);
  const [analytics, setAnalytics] = useState<CaseAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);
  const [form, setForm] = useState({ lane: "REVIEW", reason: "", claim_id: "", priority: "3", stake: "" });
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const view = value("view") in VIEW_PARAMS ? value("view") : "";
  const sort: Sort = { key: value("sort") || "opened", direction: value("dir") === "asc" ? "asc" : "desc" };
  const filtered = Boolean(value("q") || value("lane"));

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.caseSearch({ ...VIEW_PARAMS[view], q: value("q"), lane: value("lane"), sort: sort.key, direction: sort.direction, limit: pageSize, offset: (page - 1) * pageSize }));
    } catch (e) {
      setError(message(e, "The cases could not be loaded."));
    } finally {
      setLoading(false);
    }
    // `query` is the whole view, filter, sort and page state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { api.caseAnalytics().then(setAnalytics).catch(() => setAnalytics(null)); }, []);

  const c = data?.counts;
  const views = [
    { key: "", label: "Open", count: c ? c.OPEN + c.IN_REVIEW + c.ESCALATED : undefined },
    { key: "mine", label: "Assigned to me", count: c?.MINE },
    { key: "unassigned", label: "Unassigned", count: c?.OPEN },
    { key: "overdue", label: "Past due", count: c?.OVERDUE, alert: true },
    { key: "escalated", label: "Escalated", count: c?.ESCALATED },
    { key: "closed", label: "Closed", count: c?.CLOSED },
    { key: "all", label: "All" },
  ];

  const reasonError = !form.reason.trim() ? "Say why the case is being opened." : null;
  const stakeError = form.stake !== "" && !(Number(form.stake) >= 0) ? "Enter an amount in rand, or leave it blank." : null;
  async function openCase() {
    setAttempted(true);
    if (reasonError || stakeError) return;
    setBusy(true);
    setFormError(null);
    try {
      if (form.claim_id.trim() && !(await api.getClaim(form.claim_id.trim()).then(() => true, () => false))) {
        setFormError("There is no claim with that reference.");
        return;
      }
      const made = await api.openCase({ lane: form.lane, reason: form.reason.trim(), claim_id: form.claim_id.trim() || null, priority: Number(form.priority), rand_at_stake: Number(form.stake) || 0 });
      toast.success(`Case ${made.id} opened.`);
      navigate(`/cases/${made.id}`);
    } catch (e) {
      setFormError(message(e, "The case could not be opened."));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<CaseItem>[] = [
    { key: "opened", header: "Case", sortable: true, render: (r) => <div><div className="font-medium text-ink-900">Case {r.id}</div><div className="max-w-[40ch] truncate text-xs text-ink-500" title={r.reason}>{r.reason}</div></div> },
    { key: "claim", header: "Claim", render: (r) => r.claim_id ? <Ref className="text-ink-700">{r.claim_id}</Ref> : <span className="text-ink-400">—</span> },
    { key: "lane", header: "Kind", render: (r) => <span className="text-ink-700">{CASE_LANES[r.lane]?.label ?? r.lane}</span> },
    { key: "priority", header: "Priority", sortable: true, render: (r) => <span className={cx(r.priority <= 2 ? "font-medium text-ink-900" : "text-ink-700")}>{CASE_PRIORITIES[r.priority]?.label ?? r.priority}</span> },
    { key: "status", header: "Status", render: (r) => (
      <div>
        <Badge tone={CASE_STATUS[r.status]?.tone ?? "neutral"} dot>{CASE_STATUS[r.status]?.label ?? r.status}</Badge>
        <div className="mt-1 text-xs text-ink-500">{r.status === "CLOSED" ? CASE_VERDICTS[r.verdict ?? ""] ?? "No verdict recorded" : r.assigned_to ? `With ${r.assigned_to}` : ""}</div>
      </div>
    ) },
    { key: "due", header: "Due", sortable: true, render: (r) => r.status === "CLOSED" ? <span className="text-ink-400">—</span> : <span className={cx(r.overdue ? "font-medium text-bad-fg" : "text-ink-700")}>{dueText(r.days_to_sla, r.overdue)}</span> },
    { key: "stake", header: "At stake", align: "right", sortable: true, render: (r) => <span className="tnum text-ink-900">{r.rand_at_stake > 0 ? rand(r.rand_at_stake) : "—"}</span> },
  ];

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Work" }, { label: "Cases" }]}
        title="Cases"
        subtitle="Review and investigation work. A billing review goes to a claims handler; a fraud hold or a recovery goes to an investigator."
        actions={<Button variant="primary" icon={Plus} onClick={() => { setForm({ lane: "REVIEW", reason: "", claim_id: "", priority: "3", stake: "" }); setAttempted(false); setFormError(null); setOpening(true); }}>Open a case</Button>}
      />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Open cases" value={analytics ? analytics.open : "…"} hint={analytics ? `${analytics.n} in total` : undefined} />
        <Stat label="Past their due date" value={analytics ? analytics.overdue : "…"} tone={analytics?.overdue ? "bad" : undefined} />
        <Stat label="At stake in open cases" value={analytics ? rand(analytics.rand_at_stake_open) : "…"} />
        <Stat label="Recovered and prevented" value={analytics ? rand(analytics.rand_recovered + analytics.rand_prevented) : "…"} tone="ok" hint={analytics ? `${rand(analytics.rand_recovered)} recovered` : undefined} />
      </div>

      <ViewPills views={views} value={view} label="Views" onChange={(k) => reset(k ? { view: k } : {})} />
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-4">
        <Input className="sm:col-span-2" placeholder="Case number, claim, reason or person" aria-label="Search cases" value={value("q")} onChange={(e) => set({ q: e.target.value })} />
        <Select aria-label="Kind" value={value("lane")} onChange={(e) => set({ lane: e.target.value })}>
          <option value="">Any kind</option>
          {Object.entries(CASE_LANES).map(([k, l]) => <option key={k} value={k}>{l.label}</option>)}
        </Select>
        {filtered && <div className="flex items-center"><Button size="sm" variant="ghost" icon={X} onClick={() => set({ q: null, lane: null })}>Clear filters</Button></div>}
      </div>
      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={columns} rows={data?.rows ?? []} rowKey={(r) => String(r.id)} loading={loading}
          sort={sort} onSort={(s) => set({ sort: s.key === "opened" ? null : s.key, dir: s.direction === "asc" ? "asc" : null }, true)}
          onRowClick={(r) => navigate(`/cases/${r.id}`)}
          empty={<EmptyState title={filtered ? "No case matches" : view === "" ? "No open cases" : "Nothing in this view"} body={filtered ? "Change or clear the filters." : "Cases are opened here, or from a claim that needs a closer look."} />}
          footer={<Pager page={page} pageSize={pageSize} total={data?.total ?? 0} unit="cases" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
        />
      )}

      <Dialog
        open={opening} onClose={() => setOpening(false)} wide title="Open a case" description="The priority sets the due date. The case starts unassigned, in the queue of the role that owns its kind."
        footer={<><Button onClick={() => setOpening(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={openCase}>Open case</Button></>}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Kind" required hint={CASE_LANES[form.lane]?.help}>
            <Select value={form.lane} onChange={(e) => setForm({ ...form, lane: e.target.value })}>
              {Object.entries(CASE_LANES).map(([k, l]) => <option key={k} value={k}>{l.label}</option>)}
            </Select>
          </Field>
          <Field label="Priority" required hint={`Due within ${CASE_PRIORITIES[Number(form.priority)].days} day${CASE_PRIORITIES[Number(form.priority)].days === 1 ? "" : "s"}.`}>
            <Select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
              {Object.entries(CASE_PRIORITIES).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
            </Select>
          </Field>
          <Field label="Reason" required error={attempted ? reasonError : null} className="sm:col-span-2">
            <Textarea rows={3} maxLength={500} value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} placeholder="What needs to be looked at, and why" />
          </Field>
          <Field label="Claim reference" hint="Optional. Links the case to a claim.">
            <Input className="font-mono" value={form.claim_id} onChange={(e) => setForm({ ...form, claim_id: e.target.value })} />
          </Field>
          <Field label="Amount at stake (R)" error={attempted ? stakeError : null} hint="Optional.">
            <Input type="number" min={0} step="0.01" value={form.stake} onChange={(e) => setForm({ ...form, stake: e.target.value })} />
          </Field>
          {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg sm:col-span-2" role="alert">{formError}</p>}
        </div>
      </Dialog>
    </div>
  );
}
