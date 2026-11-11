// One payment run. Who assembled, approved and released it; the claims it pays; the remittance
// advice it produced; and everything that happened to it. Three different people must act:
// the page says whose turn it is and why a button is not available to you.

import { Ban, Check, CircleDollarSign, FileText, Pencil, Printer, Send, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { CLAIM_TYPES, PAYMENT_EVENTS, PAYMENT_SOURCES, REMITTANCE_STATUS, RUN_STATUS, dateTime, paymentError, shortDate } from "../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, LoadingBlock, PageHeader, Panel, Ref, Select, Stat, Tabs, Textarea, cx } from "../ds/primitives";
import { rand } from "../format";
import type { BatchDict, PaymentSource, QueueRow } from "../types";
import { ReadyToPayTable, matches, selectable } from "./payments/ReadyToPay";

type Tab = "claims" | "add" | "advice" | "history";
type Pending = "approve" | "pay" | "cancel" | "issue" | { remove: number; claim: string } | null;
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? paymentError(e.message) : fallback);
const OTHER_SOURCES: PaymentSource[] = ["INTERIM", "SETTLEMENT", "COURT_ORDER", "SUPPLIER", "UNDERTAKING_INVOICE"];

export default function PaymentRunPage() {
  const { id = "" } = useParams();
  const runId = Number(id);
  const toast = useToast();
  const { user } = useAuth();
  const [run, setRun] = useState<BatchDict | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("claims");
  const [pending, setPending] = useState<Pending>(null);
  const [busy, setBusy] = useState(false);
  const [editingNote, setEditingNote] = useState(false);
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      setRun(await api.getBatch(runId));
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "There is no payment run with that number." : message(e, "The payment run could not be loaded."));
    }
  }, [runId]);
  useEffect(() => { setRun(null); setTab("claims"); void load(); }, [load]);

  const crumbs = [{ label: "Finance" }, { label: "Payments", to: "/payments" }, { label: `Payment run ${id}` }];
  if (!Number.isInteger(runId) || error) {
    return <div><PageHeader crumbs={crumbs} title={`Payment run ${id}`} /><ErrorBlock message={error ?? "There is no payment run with that number."} onRetry={error ? load : undefined} /></div>;
  }
  if (!run) return <div><PageHeader crumbs={crumbs} title={`Payment run ${id}`} /><LoadingBlock /></div>;

  const me = user?.username;
  const isAdmin = user?.role === "ADMIN";
  const canAssemble = user?.role === "HANDLER" || isAdmin;
  const open = run.status === "OPEN";
  const status = RUN_STATUS[run.status];

  // Why an action is not available to this user, in the Fund's three-person rule.
  const approveBlock = !isAdmin ? "Only an administrator can approve a run."
    : me === run.created_by ? "You assembled this run, so a different administrator must approve it."
    : run.n_claims === 0 ? "Add at least one claim before the run is approved." : null;
  const payBlock = !isAdmin ? "Only an administrator can release a payment."
    : me === run.created_by || me === run.approved_by ? "You assembled or approved this run, so a different administrator must release it." : null;
  const canCancel = run.actions.includes("cancel") && (open ? canAssemble : isAdmin);

  async function act<T>(fn: () => Promise<T>, done: (r: T) => string, apply?: (r: T) => void) {
    setBusy(true);
    try {
      const res = await fn();
      apply?.(res);
      toast.success(done(res));
      setPending(null);
    } catch (e) {
      toast.error(message(e, "The action could not be completed."));
    } finally {
      setBusy(false);
    }
  }
  const apply = (r: BatchDict) => setRun(r);

  const steps = [
    { label: "Assembled", who: run.created_by, when: run.created_at, done: true },
    { label: "Approved", who: run.approved_by, when: run.events.find((e) => e.event === "APPROVED")?.at ?? null, done: Boolean(run.approved_by) },
    { label: "Released", who: run.paid_by, when: run.paid_at, done: Boolean(run.paid_by) },
  ];
  const nextStep = run.status === "OPEN"
    ? (approveBlock ?? "You can approve this run.")
    : run.status === "APPROVED" ? (payBlock ?? "You can release this payment.") : status.help;

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "claims", label: "Claims in this run", count: run.n_claims },
    ...(open && canAssemble ? [{ key: "add" as Tab, label: "Add claims" }] : []),
    { key: "advice", label: "Remittance advice", count: run.remittances.length },
    { key: "history", label: "History", count: run.events.length },
  ];

  return (
    <div>
      <PageHeader
        crumbs={crumbs}
        title={`Payment run ${run.id}`}
        meta={<Badge tone={status.tone} dot>{status.label}</Badge>}
        subtitle={run.note || "No note"}
        actions={
          <>
            {open && canAssemble && <Button icon={Pencil} onClick={() => { setNote(run.note ?? ""); setEditingNote(true); }}>Edit note</Button>}
            {canCancel && <Button variant="danger" icon={Ban} onClick={() => setPending("cancel")}>Cancel run</Button>}
            {open && <Button variant="primary" icon={Check} disabled={approveBlock !== null} title={approveBlock ?? undefined} onClick={() => setPending("approve")}>Approve</Button>}
            {run.status === "APPROVED" && <Button variant="primary" icon={Send} disabled={payBlock !== null} title={payBlock ?? undefined} onClick={() => setPending("pay")}>Release payment</Button>}
          </>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Total" value={rand(run.total)} tone={run.status === "PAID" ? "ok" : undefined} hint={run.status === "PAID" ? "Paid" : run.status === "CANCELLED" ? "Not paid" : "To be paid"} />
        <Stat label="Claims" value={run.n_claims} hint={`${new Set(run.instructions.flatMap((i) => i.providers)).size} practices`} />
        <Stat label="Created" value={shortDate(run.created_at)} hint={`by ${run.created_by}`} />
        <Stat label="Released" value={run.paid_at ? shortDate(run.paid_at) : "Not yet"} hint={run.paid_by ? `by ${run.paid_by}` : undefined} />
      </div>

      <Panel title="Three-person control" description="The person who assembles a run cannot approve it, and neither of them can release the payment." className="mb-4">
        <ol className="grid gap-3 sm:grid-cols-3">
          {steps.map((s, i) => (
            <li key={s.label} className={cx("flex items-start gap-3 rounded-md border px-3 py-2.5", s.done ? "border-ok-line bg-ok-bg" : "border-line bg-ink-50/60")}>
              <span className={cx("mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold", s.done ? "bg-ok-fg text-white" : "border border-line-strong bg-white text-ink-500")}>
                {s.done ? <Check size={13} aria-hidden /> : i + 1}
              </span>
              <div className="min-w-0">
                <div className="text-sm font-medium text-ink-900">{s.label}</div>
                <div className="truncate text-[13px] text-ink-600">{s.who ? `${s.who}${s.when ? `, ${shortDate(s.when)}` : ""}` : run.status === "CANCELLED" ? "Did not happen" : "Waiting"}</div>
              </div>
            </li>
          ))}
        </ol>
        <p className="mt-3 text-[13px] text-ink-600">{nextStep}</p>
      </Panel>

      <Tabs<Tab> tabs={tabs} value={tab} onChange={setTab} />

      <div className="mt-4">
        {tab === "claims" && (
          <div className="overflow-hidden rounded-lg border border-line bg-white shadow-panel">
            {run.instructions.length === 0 ? (
              <EmptyState icon={CircleDollarSign} title="No claims in this run yet" body={open && canAssemble ? "Add the claims this run should pay." : "Nothing was added to this run."} action={open && canAssemble ? <Button variant="primary" onClick={() => setTab("add")}>Add claims</Button> : undefined} />
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-line bg-ink-50/70 text-left text-xs font-medium text-ink-500">
                      <th className="px-4 py-2.5 font-medium">Claim</th><th className="px-4 py-2.5 font-medium">Paid as</th><th className="px-4 py-2.5 font-medium">Billed by</th>
                      <th className="px-4 py-2.5 text-right font-medium">Amount</th><th className="px-4 py-2.5 font-medium">Payment</th>{open && canAssemble && <th className="px-4 py-2.5" />}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {run.instructions.map((i) => (
                      <tr key={i.id} className="align-top">
                        <td className="px-4 py-3">
                          <Link to={`/claims/${encodeURIComponent(i.claim_id)}`} className="font-medium text-brand-700 hover:underline"><Ref>{i.claim_id}</Ref></Link>
                          <div className="text-xs text-ink-500">{i.claim_type ? CLAIM_TYPES[i.claim_type] ?? i.claim_type : ""}</div>
                        </td>
                        <td className="px-4 py-3 text-ink-700">{PAYMENT_SOURCES[i.source] ?? i.source}</td>
                        <td className="px-4 py-3">{i.providers.length ? <Ref className="text-ink-700">{i.providers.join(", ")}</Ref> : <span className="text-ink-400">—</span>}</td>
                        <td className="tnum px-4 py-3 text-right font-medium text-ink-900">{rand(i.amount)}</td>
                        <td className="px-4 py-3">{i.paid ? <Badge tone="ok" dot>Paid</Badge> : run.status === "CANCELLED" ? <Badge>Not paid</Badge> : <Badge tone="info">Pending</Badge>}</td>
                        {open && canAssemble && (
                          <td className="px-4 py-3 text-right">
                            <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setPending({ remove: i.id, claim: i.claim_id })}>Remove</Button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {run.instructions.length > 0 && (
              <div className="flex justify-end gap-2 border-t border-line bg-ink-50/40 px-4 py-2.5 text-sm"><span className="text-ink-500">Run total</span><span className="tnum font-semibold text-ink-900">{rand(run.total)}</span></div>
            )}
          </div>
        )}

        {tab === "add" && open && canAssemble && <AddClaims run={run} onChange={apply} />}

        {tab === "advice" && (
          <Panel
            title="Remittance advice" flush
            description="One advice per practice, issued when the payment is released. It lists what was billed, what was paid and why any line was reduced."
            actions={run.status === "PAID" && isAdmin && run.remittances.length === 0 && run.n_claims > 0 ? <Button size="sm" icon={FileText} onClick={() => setPending("issue")}>Issue advice</Button> : undefined}
          >
            {run.remittances.length === 0 ? (
              <EmptyState icon={FileText} title="No remittance advice" body={run.status === "PAID" ? "No advice was issued for this run. Settlements paid to claimants do not produce one." : "Advice is issued when the payment is released."} />
            ) : (
              <ul className="divide-y divide-line">
                {run.remittances.map((r) => (
                  <li key={r.ref} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <Link to={`/payments/remittances/${encodeURIComponent(r.ref)}`} className="font-medium text-brand-700 hover:underline"><Ref>{r.ref}</Ref></Link>
                      <div className="text-[13px] text-ink-500">Practice <Ref>{r.provider_id}</Ref>, {r.n_claims} claim{r.n_claims === 1 ? "" : "s"}, paid <span className="tnum">{rand(r.total_paid)}</span></div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={REMITTANCE_STATUS[r.status]?.tone ?? "neutral"} dot>{REMITTANCE_STATUS[r.status]?.label ?? r.status}</Badge>
                      <a href={api.remittancePrintUrl(r.ref)} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong bg-white px-2.5 text-[13px] font-medium text-ink-800 hover:bg-ink-50"><Printer size={14} aria-hidden /> Print</a>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        )}

        {tab === "history" && (
          <Panel title="History" description="Every change to this run, with who made it." flush>
            <ol className="divide-y divide-line">
              {[...run.events].reverse().map((e, i) => (
                <li key={i} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3">
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-ink-900">{PAYMENT_EVENTS[e.event] ?? e.event}</span>
                    {typeof e.detail?.claim_id === "string" && <> <Ref className="text-ink-600">{e.detail.claim_id}</Ref></>}
                    {e.amount != null && <span className="tnum ml-2 text-sm text-ink-700">{rand(e.amount)}</span>}
                    {e.event === "NOTE_CHANGED" && <span className="ml-2 text-[13px] text-ink-500">{typeof e.detail?.note === "string" ? `"${e.detail.note}"` : "Note cleared"}</span>}
                  </div>
                  <div className="text-[13px] text-ink-500">{e.actor} · {dateTime(e.at)}</div>
                </li>
              ))}
            </ol>
          </Panel>
        )}
      </div>

      <ConfirmDialog
        open={pending === "approve"} onClose={() => setPending(null)} busy={busy} title={`Approve payment run ${run.id}?`} confirmLabel="Approve run"
        description={`${run.n_claims} claim${run.n_claims === 1 ? "" : "s"}, ${rand(run.total)}. After approval the run cannot be changed, only released or cancelled.`}
        onConfirm={() => act(() => api.approveBatch(run.id), () => `Payment run ${run.id} approved.`, apply)}
      />
      <ConfirmDialog
        open={pending === "pay"} onClose={() => setPending(null)} busy={busy} title={`Release ${rand(run.total)}?`} confirmLabel="Release payment"
        description={`This pays ${run.n_claims} claim${run.n_claims === 1 ? "" : "s"} and sends a remittance advice to each practice. It cannot be undone.`}
        onConfirm={() => act(() => api.payBatch(run.id), () => `Payment run ${run.id} released.`, (r) => { apply(r); setTab("advice"); })}
      />
      <ConfirmDialog
        open={pending === "cancel"} onClose={() => setPending(null)} busy={busy} danger title={`Cancel payment run ${run.id}?`} confirmLabel="Cancel run"
        description="Nothing is paid. The claims go back to the ready-to-pay list. A cancelled run cannot be reopened."
        onConfirm={() => act(() => api.cancelBatch(run.id), () => `Payment run ${run.id} cancelled.`, apply)}
      />
      <ConfirmDialog
        open={pending === "issue"} onClose={() => setPending(null)} busy={busy} title="Issue remittance advice?" confirmLabel="Issue advice"
        description="One advice is created for each practice paid by this run."
        onConfirm={() => act(() => api.issueRemittances(run.id), (r) => (r.length ? `${r.length} remittance advice issued.` : "Nothing to issue for this run."), () => void load())}
      />
      <ConfirmDialog
        open={typeof pending === "object" && pending !== null} onClose={() => setPending(null)} busy={busy} danger
        title="Remove this claim from the run?" confirmLabel="Remove claim"
        description={typeof pending === "object" && pending !== null ? <>Claim <Ref>{pending.claim}</Ref> goes back to the ready-to-pay list.</> : undefined}
        onConfirm={() => typeof pending === "object" && pending !== null && act(() => api.removeInstruction(run.id, pending.remove), () => "Claim removed from the run.", apply)}
      />
      <Dialog
        open={editingNote} onClose={() => setEditingNote(false)} title="Edit note"
        footer={<><Button onClick={() => setEditingNote(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => act(() => api.updateBatchNote(run.id, note), () => "Note saved.", (r) => { apply(r); setEditingNote(false); })}>Save note</Button></>}
      >
        <Field label="Note" hint="For example the payment date or the period this run covers.">
          <Textarea rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </Dialog>
    </div>
  );
}

/** Add claims to an open run: tick them in the ready-to-pay list, or capture another payment. */
function AddClaims({ run, onChange }: { run: BatchDict; onChange: (r: BatchDict) => void }) {
  const toast = useToast();
  const [queue, setQueue] = useState<QueueRow[] | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [other, setOther] = useState({ claim_id: "", source: "INTERIM" as PaymentSource, amount: "" });

  const loadQueue = useCallback(() => { api.paymentsQueue().then(setQueue).catch(() => setQueue([])); }, []);
  useEffect(() => { loadQueue(); }, [loadQueue, run.n_claims]);

  const rows = useMemo(() => (queue ?? []).filter((r) => selectable(r) && matches(r, q)), [queue, q]);
  const picked = rows.filter((r) => selected.has(r.claim_id));
  const pickedTotal = picked.reduce((s, r) => s + (r.amount ?? 0), 0);

  async function addSelected() {
    setBusy(true);
    let latest: BatchDict | null = null;
    const failed: string[] = [];
    for (const r of picked) {
      try {
        latest = await api.addInstruction(run.id, { claim_id: r.claim_id, source: r.source! });
      } catch (e) {
        failed.push(`${r.claim_id}: ${message(e, "could not be added")}`);
      }
    }
    const added = picked.length - failed.length;
    if (added) toast.success(`${added} claim${added === 1 ? "" : "s"} added.`);
    failed.forEach((m) => toast.error(m));
    setSelected(new Set());
    setBusy(false);
    if (latest) onChange(latest); else loadQueue();
  }

  const amount = Number(other.amount);
  const interim = other.source === "INTERIM";
  const otherValid = other.claim_id.trim() !== "" && (interim ? amount > 0 : other.amount === "" || amount > 0);
  async function addOther() {
    setBusy(true);
    try {
      const res = await api.addInstruction(run.id, { claim_id: other.claim_id.trim(), source: other.source, ...(other.amount !== "" ? { amount } : {}) });
      toast.success(`Claim ${other.claim_id.trim()} added.`);
      setOther({ claim_id: "", source: other.source, amount: "" });
      onChange(res);
    } catch (e) {
      toast.error(message(e, "The payment could not be added."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Panel
        title="Ready to pay" flush description="Claims cleared for payment that are not in a run."
        actions={
          <div className="flex items-center gap-3">
            {picked.length > 0 && <span className="tnum text-[13px] text-ink-700">{picked.length} selected, {rand(pickedTotal)}</span>}
            <Button variant="primary" size="sm" disabled={picked.length === 0} loading={busy} onClick={addSelected}>Add selected</Button>
          </div>
        }
      >
        <div className="border-b border-line px-4 py-3"><div className="sm:w-72"><Input placeholder="Claim reference or practice number" aria-label="Search claims ready to pay" value={q} onChange={(e) => setQ(e.target.value)} /></div></div>
        {queue === null ? <LoadingBlock /> : <ReadyToPayTable rows={rows} selected={selected} onChange={setSelected} emptyBody={q ? "No claim matches the search." : "Every claim that is cleared for payment is already in a run."} />}
      </Panel>

      <Panel title="Another payment" description="An interim payment, or a settlement or court order captured by reference. The Fund checks the claim and the amount before it is added.">
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="Claim reference" required>
            <Input className="font-mono" value={other.claim_id} onChange={(e) => setOther({ ...other, claim_id: e.target.value })} />
          </Field>
          <Field label="Paid as" required>
            <Select value={other.source} onChange={(e) => setOther({ ...other, source: e.target.value as PaymentSource })}>
              {OTHER_SOURCES.map((s) => <option key={s} value={s}>{PAYMENT_SOURCES[s]}</option>)}
            </Select>
          </Field>
          <Field label="Amount (R)" required={interim} hint={interim ? "Up to the claim's payable amount." : "Leave blank to use the amount on record."}>
            <Input type="number" min={0} step="0.01" value={other.amount} onChange={(e) => setOther({ ...other, amount: e.target.value })} />
          </Field>
          <div className="flex items-start pt-[22px]"><Button disabled={!otherValid} loading={busy} onClick={addOther}>Add payment</Button></div>
        </div>
      </Panel>
    </div>
  );
}
