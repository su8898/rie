// Disputes. Every objection to a decision of the Fund: who raised it, about what, where it
// stands and by when it must be dealt with. Each dispute opens as its own record.

import { Plus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { DataTable, Pager, type Column, type Sort } from "../ds/DataTable";
import { DISPUTE_CHANNELS, DISPUTE_RAISERS, DISPUTE_STATUS, DISPUTE_SUBJECTS, dueText, shortDate, workError } from "../ds/labels";
import { Dialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, PageHeader, Ref, Select, Stat, Textarea, cx } from "../ds/primitives";
import type { DisputeItem, DisputeSearch } from "../types";
import { ViewPills, useListParams } from "./work/shared";

const VIEW_PARAMS: Record<string, Record<string, string | boolean>> = {
  "": { open_only: true }, new: { status: "LODGED" }, overdue: { overdue: true }, referred: { status: "REFERRED" }, all: {},
};
const OPEN_STATES = ["LODGED", "UNDER_RECONSIDERATION", "REJECTED", "REFERRED"];
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? workError(e.message) : fallback);

export default function DisputesPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const { value, page, pageSize, set, reset, query } = useListParams();
  const [data, setData] = useState<DisputeSearch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lodging, setLodging] = useState(false);
  const [form, setForm] = useState({ claim_id: "", subject: "TARIFF", raised_by: "PROVIDER", grounds: "" });
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const view = value("view") in VIEW_PARAMS ? value("view") : "";
  const sort: Sort = { key: value("sort") || "opened", direction: value("dir") === "asc" ? "asc" : "desc" };
  const filterKeys = ["q", "subject", "raised_by", "status"];
  const filtered = filterKeys.some((k) => value(k));

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.disputeSearch({
        ...VIEW_PARAMS[view], ...(value("status") ? { status: value("status"), open_only: undefined } : {}),
        q: value("q"), subject: value("subject"), raised_by: value("raised_by"),
        sort: sort.key, direction: sort.direction, limit: pageSize, offset: (page - 1) * pageSize,
      }));
    } catch (e) {
      setError(message(e, "The disputes could not be loaded."));
    } finally {
      setLoading(false);
    }
    // `query` is the whole view, filter, sort and page state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);
  useEffect(() => { void load(); }, [load]);

  const c = data?.counts;
  const closedCount = c ? (c.UPHELD ?? 0) + (c.RESOLVED ?? 0) + (c.WITHDRAWN ?? 0) : undefined;
  const views = [
    { key: "", label: "Open", count: c?.OPEN },
    { key: "new", label: "New", count: c?.LODGED },
    { key: "overdue", label: "Past deadline", count: c?.OVERDUE, alert: true },
    { key: "referred", label: "Referred", count: c?.REFERRED },
    { key: "all", label: "All", count: c && closedCount != null ? c.OPEN + closedCount : undefined },
  ];

  const errors = { claim: !form.claim_id.trim() ? "Enter the claim reference." : null, grounds: !form.grounds.trim() ? "Record the grounds of the objection." : null };
  async function lodge() {
    setAttempted(true);
    if (errors.claim || errors.grounds) return;
    setBusy(true);
    setFormError(null);
    try {
      if (!(await api.getClaim(form.claim_id.trim()).then(() => true, () => false))) {
        setFormError("There is no claim with that reference.");
        return;
      }
      const made = await api.lodgeDispute({ claim_id: form.claim_id.trim(), subject: form.subject, raised_by: form.raised_by, grounds: form.grounds.trim() });
      toast.success(`Dispute ${made.id} lodged.`);
      navigate(`/disputes/${made.id}`);
    } catch (e) {
      setFormError(message(e, "The dispute could not be lodged."));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<DisputeItem>[] = [
    { key: "opened", header: "Dispute", sortable: true, render: (r) => <div><div className="font-medium text-ink-900">Dispute {r.id}</div><div className="text-xs text-ink-500">Lodged {shortDate(r.opened_at)}</div></div> },
    { key: "claim", header: "Claim", render: (r) => <Ref className="text-ink-700">{r.claim_id}</Ref> },
    { key: "subject", header: "About", render: (r) => <div><div className="text-ink-800">{DISPUTE_SUBJECTS[r.subject] ?? r.subject}</div><div className="text-xs text-ink-500">Raised by the {(DISPUTE_RAISERS[r.raised_by] ?? r.raised_by).toLowerCase()}</div></div> },
    { key: "status", header: "Status", render: (r) => (
      <div>
        <Badge tone={DISPUTE_STATUS[r.status]?.tone ?? "neutral"} dot>{DISPUTE_STATUS[r.status]?.label ?? r.status}</Badge>
        {r.channel && r.channel !== "INTERNAL" && <div className="mt-1 text-xs text-ink-500">{DISPUTE_CHANNELS[r.channel] ?? r.channel}</div>}
      </div>
    ) },
    { key: "deadline", header: "Deadline", sortable: true, render: (r) => !OPEN_STATES.includes(r.status) ? <span className="text-ink-400">—</span> : (
      <div><div className={cx(r.overdue ? "font-medium text-bad-fg" : "text-ink-700")}>{dueText(r.days_to_deadline, r.overdue)}</div><div className="text-xs text-ink-500">{shortDate(r.deadline)}</div></div>
    ) },
    { key: "outcome", header: "Outcome", render: (r) => <span className="block max-w-[34ch] truncate text-[13px] text-ink-600" title={r.outcome ?? ""}>{r.outcome || "—"}</span> },
  ];

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Work" }, { label: "Disputes" }]}
        title="Disputes"
        subtitle="Objections to a decision of the Fund. Each is reconsidered internally first; legal may refer one to the HPCSA tribunal or to court."
        actions={<Button variant="primary" icon={Plus} onClick={() => { setForm({ claim_id: "", subject: "TARIFF", raised_by: "PROVIDER", grounds: "" }); setAttempted(false); setFormError(null); setLodging(true); }}>Lodge a dispute</Button>}
      />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Open" value={c ? c.OPEN : "…"} />
        <Stat label="New, not yet started" value={c ? c.LODGED : "…"} tone={c?.LODGED ? "warn" : undefined} />
        <Stat label="Past their deadline" value={c ? c.OVERDUE : "…"} tone={c?.OVERDUE ? "bad" : undefined} />
        <Stat label="Upheld" value={c ? c.UPHELD : "…"} hint={closedCount != null ? `of ${closedCount} closed` : undefined} />
      </div>

      <ViewPills views={views} value={view} label="Views" onChange={(k) => reset(k ? { view: k } : {})} />
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-2 lg:grid-cols-5">
        <Input className="lg:col-span-2" placeholder="Dispute number, claim or grounds" aria-label="Search disputes" value={value("q")} onChange={(e) => set({ q: e.target.value })} />
        <Select aria-label="About" value={value("subject")} onChange={(e) => set({ subject: e.target.value })}>
          <option value="">About anything</option>
          {Object.entries(DISPUTE_SUBJECTS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </Select>
        <Select aria-label="Raised by" value={value("raised_by")} onChange={(e) => set({ raised_by: e.target.value })}>
          <option value="">Raised by anyone</option>
          {Object.entries(DISPUTE_RAISERS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </Select>
        <Select aria-label="Status" value={value("status")} onChange={(e) => set({ status: e.target.value })}>
          <option value="">Any status in this view</option>
          {Object.entries(DISPUTE_STATUS).map(([k, s]) => <option key={k} value={k}>{s.label}</option>)}
        </Select>
        {filtered && <div className="flex items-center lg:col-span-5"><Button size="sm" variant="ghost" icon={X} onClick={() => set(Object.fromEntries(filterKeys.map((k) => [k, null])))}>Clear filters</Button></div>}
      </div>
      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={columns} rows={data?.rows ?? []} rowKey={(r) => String(r.id)} loading={loading}
          sort={sort} onSort={(s) => set({ sort: s.key === "opened" ? null : s.key, dir: s.direction === "asc" ? "asc" : null }, true)}
          onRowClick={(r) => navigate(`/disputes/${r.id}`)}
          empty={<EmptyState title={filtered ? "No dispute matches" : view === "" ? "No open disputes" : "Nothing in this view"} body={filtered ? "Change or clear the filters." : "A dispute is lodged here, or arrives from a practice over the provider channel."} />}
          footer={<Pager page={page} pageSize={pageSize} total={data?.total ?? 0} unit="disputes" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
        />
      )}

      <Dialog
        open={lodging} onClose={() => setLodging(false)} wide title="Lodge a dispute" description="The deadline is set 180 days from today."
        footer={<><Button onClick={() => setLodging(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={lodge}>Lodge dispute</Button></>}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Claim reference" required error={attempted ? errors.claim : null} className="sm:col-span-2">
            <Input className="font-mono" value={form.claim_id} onChange={(e) => setForm({ ...form, claim_id: e.target.value })} />
          </Field>
          <Field label="What is disputed" required hint={form.subject === "SERIOUS_INJURY" ? "A referral of this kind goes to the HPCSA tribunal." : "A referral of this kind goes to court."}>
            <Select value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })}>
              {Object.entries(DISPUTE_SUBJECTS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </Select>
          </Field>
          <Field label="Raised by" required>
            <Select value={form.raised_by} onChange={(e) => setForm({ ...form, raised_by: e.target.value })}>
              {Object.entries(DISPUTE_RAISERS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </Select>
          </Field>
          <Field label="Grounds" required error={attempted ? errors.grounds : null} className="sm:col-span-2">
            <Textarea rows={4} maxLength={2000} value={form.grounds} onChange={(e) => setForm({ ...form, grounds: e.target.value })} placeholder="What the objector says is wrong, and why" />
          </Field>
          {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg sm:col-span-2" role="alert">{formError}</p>}
        </div>
      </Dialog>
    </div>
  );
}
