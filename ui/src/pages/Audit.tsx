// Recovery audit. Claims that were paid and later look wrong: paid on a high-risk assessment, or
// billed by a practice now rated high risk. An investigator reviews each one and either recovers
// the money or clears it.

import { Play, ScanSearch, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, Pager, type Column } from "../ds/DataTable";
import { DISPOSITIONS, RISK, humanise, shortDate, workError } from "../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, PageHeader, Ref, Select, Stat, cx } from "../ds/primitives";
import type { Tone } from "../ds/labels";
import { rand } from "../format";
import type { AuditItem, AuditRoi, Band, Disposition } from "../types";
import { ViewPills, useListParams } from "./work/shared";

const STATUS: Record<string, { label: string; tone: Tone }> = {
  OPEN: { label: "Not started", tone: "info" }, UNDER_REVIEW: { label: "Under review", tone: "brand" },
  RECOVERED: { label: "Recovered", tone: "ok" }, CLEARED: { label: "Cleared", tone: "neutral" },
};
const OUTCOMES: Record<string, string> = {
  RECOVERED_FULL: "Recovered in full", RECOVERED_PARTIAL: "Recovered in part", WRITTEN_OFF: "Written off",
  NOT_PURSUED: "Not pursued", CLEARED: "Nothing to recover",
};
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? workError(e.message) : fallback);
/** The sweep's reason, as the server recorded it, in plain words. Practice numbers are kept exactly. */
function why(reason: string): React.ReactNode {
  const practice = reason.match(/^high-risk provider (\S+) \(score ([\d.]+)\)$/);
  if (practice) return <>Billed by practice <Ref>{practice[1]}</Ref>, risk score {practice[2]} of 100</>;
  const paid = reason.match(/^(\w+)\/(\w+) determination, paid$/);
  if (paid) return `Paid on a ${RISK[paid[1] as Band]?.label.toLowerCase() ?? paid[1]} risk assessment (${DISPOSITIONS[paid[2] as Disposition]?.label.toLowerCase() ?? paid[2]})`;
  return reason;
}

export default function AuditPage() {
  const toast = useToast();
  const { user } = useAuth();
  const { value, page, pageSize, set, reset } = useListParams();
  const [items, setItems] = useState<AuditItem[] | null>(null);
  const [roi, setRoi] = useState<AuditRoi | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sweeping, setSweeping] = useState(false);
  const [threshold, setThreshold] = useState("20");
  const [recovering, setRecovering] = useState<AuditItem | null>(null);
  const [recover, setRecover] = useState({ amount: "", outcome: "" });
  const [clearing, setClearing] = useState<AuditItem | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const mayAct = user?.role === "INVESTIGATOR" || user?.role === "ADMIN";
  const blocked = mayAct ? undefined : "Only investigators can work recovery items.";
  const load = useCallback(async () => {
    setError(null);
    try {
      const [i, r] = await Promise.all([api.auditItems(), api.auditRoi()]);
      setItems(i); setRoi(r);
    } catch (e) {
      setError(message(e, "The recovery items could not be loaded."));
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const status = value("status");
  const all = items ?? [];
  const shown = useMemo(() => {
    const needle = value("q").trim().toLowerCase();
    return all.filter((a) => (!status || a.status === status) && (!needle || a.claim_id.toLowerCase().includes(needle) || a.reason.toLowerCase().includes(needle) || (a.assigned_to ?? "").toLowerCase().includes(needle)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, status, value("q")]);
  const pageRows = shown.slice((page - 1) * pageSize, page * pageSize);
  const count = (k: string) => (roi ? roi.by_status[k] ?? 0 : undefined);
  const views = [
    { key: "", label: "All", count: roi?.n_items },
    { key: "OPEN", label: "Not started", count: count("OPEN") },
    { key: "UNDER_REVIEW", label: "Under review", count: count("UNDER_REVIEW") },
    { key: "RECOVERED", label: "Recovered", count: count("RECOVERED") },
    { key: "CLEARED", label: "Cleared", count: count("CLEARED") },
  ];

  async function run(fn: () => Promise<unknown>, done: string | ((r: unknown) => string), close: () => void) {
    setBusy(true);
    setFormError(null);
    try {
      const res = await fn();
      toast.success(typeof done === "string" ? done : done(res));
      close();
      await load();
    } catch (e) {
      setFormError(message(e, "The action could not be completed."));
    } finally {
      setBusy(false);
    }
  }
  const amount = Number(recover.amount);
  const amountError = !recovering ? null : recover.amount === "" || !(amount >= 0) ? "Enter the amount recovered, or 0." : amount > recovering.amount_at_stake ? "This is more than was paid." : null;

  const columns: Column<AuditItem>[] = [
    { key: "claim", header: "Claim", render: (a) => <div><Link to={`/claims/${encodeURIComponent(a.claim_id)}`} className="font-medium text-brand-700 hover:underline"><Ref>{a.claim_id}</Ref></Link><div className="text-xs text-ink-500">Opened {shortDate(a.opened_at)}</div></div> },
    { key: "why", header: "Why it is here", render: (a) => <span className="block max-w-[40ch] text-[13px] text-ink-700">{why(a.reason)}</span> },
    { key: "status", header: "Status", render: (a) => <div><Badge tone={STATUS[a.status]?.tone ?? "neutral"} dot>{STATUS[a.status]?.label ?? a.status}</Badge><div className="mt-1 text-xs text-ink-500">{a.recovery_outcome ? OUTCOMES[a.recovery_outcome] ?? humanise(a.recovery_outcome) : a.assigned_to ? `With ${a.assigned_to}` : ""}</div></div> },
    { key: "paid", header: "Paid", align: "right", render: (a) => <span className="tnum text-ink-800">{rand(a.amount_at_stake)}</span> },
    { key: "recovered", header: "Recovered", align: "right", render: (a) => <span className={cx("tnum font-medium", a.amount_recovered > 0 ? "text-ok-fg" : "text-ink-400")}>{a.amount_recovered > 0 ? rand(a.amount_recovered) : "—"}</span> },
    { key: "actions", header: "", align: "right", render: (a) => (
      <div className="flex justify-end gap-1 whitespace-nowrap">
        {a.actions.includes("review") && <Button size="sm" variant="ghost" icon={Play} disabled={!mayAct} title={blocked} onClick={() => run(() => api.auditAction(a.id, "review"), "The item is now yours to review.", () => undefined)}>Start review</Button>}
        {a.actions.includes("recover") && <Button size="sm" variant="ghost" disabled={!mayAct} title={blocked} onClick={() => { setRecover({ amount: String(a.amount_at_stake), outcome: "" }); setAttempted(false); setFormError(null); setRecovering(a); }}>Record recovery</Button>}
        {a.actions.includes("clear") && <Button size="sm" variant="ghost" disabled={!mayAct} title={blocked} onClick={() => { setFormError(null); setClearing(a); }}>Clear</Button>}
      </div>
    ) },
  ];

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Integrity" }, { label: "Recovery audit" }]}
        title="Recovery audit"
        subtitle="Paid claims that now look wrong. An investigator reviews each one and either recovers the money or clears it."
        actions={<Button variant="primary" icon={ScanSearch} disabled={!mayAct} title={mayAct ? undefined : "Only investigators can run the sweep."} onClick={() => { setFormError(null); setSweeping(true); }}>Find paid claims to review</Button>}
      />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Items" value={roi ? roi.n_items : "…"} hint={roi ? `${(roi.by_status.OPEN ?? 0) + (roi.by_status.UNDER_REVIEW ?? 0)} still open` : undefined} />
        <Stat label="Paid on these claims" value={roi ? rand(roi.amount_at_stake) : "…"} />
        <Stat label="Recovered" value={roi ? rand(roi.amount_recovered) : "…"} tone="ok" />
        <Stat label="Recovery rate" value={roi ? `${roi.recovery_rate}%` : "…"} hint="Of the amount paid on these claims" />
      </div>

      <ViewPills views={views} value={status} label="Status" onChange={(k) => reset(k ? { status: k } : {})} />
      <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-line bg-white p-3 shadow-panel">
        <div className="w-full sm:w-80"><Input placeholder="Claim, reason or person" aria-label="Search recovery items" value={value("q")} onChange={(e) => set({ q: e.target.value })} /></div>
        {value("q") && <Button size="sm" variant="ghost" icon={X} onClick={() => set({ q: null })}>Clear</Button>}
      </div>
      {formError && !sweeping && !recovering && !clearing && <div className="mb-3"><ErrorBlock message={formError} /></div>}
      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={columns} rows={pageRows} rowKey={(a) => String(a.id)} loading={items === null}
          empty={<EmptyState title={status || value("q") ? "No item matches" : "Nothing to recover"} body={status || value("q") ? "Change the view or the search." : "Run the sweep to look for paid claims that should be reviewed."} />}
          footer={<Pager page={page} pageSize={pageSize} total={shown.length} unit="items" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
        />
      )}

      <Dialog
        open={sweeping} onClose={() => setSweeping(false)} title="Find paid claims to review"
        description="Looks through every paid claim and opens an item for each one that was paid on a high-risk assessment, or was billed by a practice whose risk score is at or above the level you set. A claim that already has an item is skipped."
        footer={<><Button onClick={() => setSweeping(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { const t = Number(threshold); if (threshold !== "" && t >= 0 && t <= 100) void run(() => api.auditSweep(t), (r) => { const n = (r as { n: number }).n; return n ? `${n} item${n === 1 ? "" : "s"} opened.` : "No new paid claims need review."; }, () => setSweeping(false)); else setFormError("Enter a score from 0 to 100."); }}>Run the sweep</Button></>}
      >
        <div className="space-y-3">
          <Field label="Practice risk score, at or above" required hint="0 to 100. A lower number opens more items.">
            <Input type="number" min={0} max={100} value={threshold} onChange={(e) => setThreshold(e.target.value)} />
          </Field>
          {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
        </div>
      </Dialog>

      <Dialog
        open={recovering !== null} onClose={() => setRecovering(null)} title={recovering ? `Record recovery: ${recovering.claim_id}` : ""} description={recovering ? `${rand(recovering.amount_at_stake)} was paid on this claim. This closes the item.` : undefined}
        footer={<><Button onClick={() => setRecovering(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (recovering && !amountError) void run(() => api.auditAction(recovering.id, "recover", { amount, ...(recover.outcome ? { outcome: recover.outcome } : {}) }), "Recovery recorded.", () => setRecovering(null)); }}>Record recovery</Button></>}
      >
        <div className="space-y-4">
          <Field label="Amount recovered (R)" required error={attempted ? amountError : null}>
            <Input type="number" min={0} step="0.01" value={recover.amount} onChange={(e) => setRecover({ ...recover, amount: e.target.value })} />
          </Field>
          <Field label="Outcome" hint="Leave on automatic to record full or partial recovery from the amount.">
            <Select value={recover.outcome} onChange={(e) => setRecover({ ...recover, outcome: e.target.value })}>
              <option value="">Automatic, from the amount</option>
              {["RECOVERED_FULL", "RECOVERED_PARTIAL", "WRITTEN_OFF", "NOT_PURSUED"].map((k) => <option key={k} value={k}>{OUTCOMES[k]}</option>)}
            </Select>
          </Field>
          {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
        </div>
      </Dialog>

      <ConfirmDialog
        open={clearing !== null} onClose={() => setClearing(null)} busy={busy} title={clearing ? `Clear the item on ${clearing.claim_id}?` : ""} confirmLabel="Clear item"
        description={formError ?? "Use this when the payment was correct and there is nothing to recover. This closes the item."}
        onConfirm={() => clearing && run(() => api.auditAction(clearing.id, "clear"), "Item cleared.", () => setClearing(null))}
      />
    </div>
  );
}
