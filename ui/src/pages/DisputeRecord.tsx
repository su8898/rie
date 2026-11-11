// One dispute. What is objected to and on what grounds, where it stands, the outcome, and every
// step taken. The steps offered follow the dispute's status and the user's role.

import { ArrowUpRight, Check, Gavel, Pencil, Play, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DISPUTE_CHANNELS, DISPUTE_RAISERS, DISPUTE_STATUS, DISPUTE_SUBJECTS, dateTime, dueText, shortDate, workError } from "../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../ds/overlays";
import { Badge, Button, ErrorBlock, Facts, Field, Input, LoadingBlock, PageHeader, Panel, Ref, Select, Stat, Tabs, Textarea } from "../ds/primitives";
import type { DisputeItem, HistoryEntry } from "../types";
import { HistoryPanel } from "./work/shared";

type Tab = "overview" | "history";
type Open = "edit" | "uphold" | "reject" | "resolve" | "refer" | "withdraw" | null;
const DECIDERS = ["ADMIN", "HANDLER", "MEDICAL_OFFICER", "LEGAL"];
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? workError(e.message) : fallback);
const linked = (ref: string | null) => !ref ? null : ref.startsWith("litigation:") ? `Litigation matter ${ref.split(":")[1]}` : ref;
const OUTCOME_DIALOG = {
  uphold: { title: "Uphold the objection", body: "The objection succeeds and the Fund's decision is revised. This closes the dispute.", label: "How the decision is revised", confirm: "Uphold objection", done: "Objection upheld." },
  reject: { title: "Reject the objection", body: "The Fund's decision stands. Legal may still refer the dispute to a tribunal or to court.", label: "Reasons the decision stands", confirm: "Reject objection", done: "Objection rejected." },
  resolve: { title: "Record the outcome", body: "Record what the tribunal or the court decided. This closes the dispute.", label: "The outcome", confirm: "Record outcome", done: "Outcome recorded." },
};

function describe(h: HistoryEntry): { title: string; note?: string } {
  const outcome = h.detail.outcome ? String(h.detail.outcome) : undefined;
  switch (h.action) {
    case "reconsider": return { title: "Reconsideration started" };
    case "uphold": return { title: "Objection upheld", note: outcome };
    case "reject": return { title: "Objection rejected", note: outcome };
    case "refer": return { title: `Referred${h.detail.channel ? ` to ${(DISPUTE_CHANNELS[String(h.detail.channel)] ?? String(h.detail.channel)).toLowerCase()}` : ""}` };
    case "resolve": return { title: "Outcome recorded", note: outcome };
    case "withdraw": return { title: "Withdrawn" };
    case "edit": return { title: "Grounds corrected" };
    default: return { title: h.action };
  }
}

export default function DisputeRecordPage() {
  const { id = "" } = useParams();
  const disputeId = Number(id);
  const toast = useToast();
  const { user } = useAuth();
  const [item, setItem] = useState<DisputeItem | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [open, setOpen] = useState<Open>(null);
  const [text, setText] = useState("");
  const [refer, setRefer] = useState({ channel: "", linked_ref: "" });
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [d, h] = await Promise.all([api.disputeGet(disputeId), api.disputeHistory(disputeId)]);
      setItem(d); setHistory(h);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "There is no dispute with that number." : message(e, "The dispute could not be loaded."));
    }
  }, [disputeId]);
  useEffect(() => { setItem(null); setTab("overview"); void load(); }, [load]);

  const crumbs = [{ label: "Work" }, { label: "Disputes", to: "/disputes" }, { label: `Dispute ${id}` }];
  if (!Number.isInteger(disputeId) || error) return <div><PageHeader crumbs={crumbs} title={`Dispute ${id}`} /><ErrorBlock message={error ?? "There is no dispute with that number."} onRetry={error ? load : undefined} /></div>;
  if (!item) return <div><PageHeader crumbs={crumbs} title={`Dispute ${id}`} /><LoadingBlock /></div>;

  const status = DISPUTE_STATUS[item.status];
  const closed = ["UPHELD", "RESOLVED", "WITHDRAWN"].includes(item.status);
  const role = user?.role ?? "";
  const mayDecide = DECIDERS.includes(role);
  const mayRefer = role === "LEGAL" || role === "ADMIN";
  const can = (a: string) => item.actions.includes(a);
  const start = (o: Open) => {
    setText(o === "edit" ? item.grounds : "");
    setRefer({ channel: item.subject === "SERIOUS_INJURY" ? "HPCSA_TRIBUNAL" : "LITIGATION", linked_ref: "" });
    setAttempted(false);
    setFormError(null);
    setOpen(o);
  };
  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true);
    setFormError(null);
    try {
      await fn();
      toast.success(done);
      setOpen(null);
      await load();
    } catch (e) {
      const m = message(e, "The action could not be completed.");
      if (open) setFormError(m); else toast.error(m);
    } finally {
      setBusy(false);
    }
  }
  const alert = formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>;
  const outcomeOpen = open === "uphold" || open === "reject" || open === "resolve" ? open : null;
  const onlyLegal = "Only legal officers can refer a dispute or record a tribunal or court outcome.";
  const onlyDeciders = "Your role cannot decide a dispute.";

  return (
    <div>
      <PageHeader
        crumbs={crumbs} title={`Dispute ${item.id}`}
        meta={<Badge tone={status?.tone ?? "neutral"} dot>{status?.label ?? item.status}</Badge>}
        subtitle={<>{DISPUTE_SUBJECTS[item.subject] ?? item.subject}, raised by the {(DISPUTE_RAISERS[item.raised_by] ?? item.raised_by).toLowerCase()} on claim <Link className="text-brand-700 hover:underline" to={`/claims/${encodeURIComponent(item.claim_id)}`}><Ref>{item.claim_id}</Ref></Link>.</>}
        actions={!closed && (
          <>
            <Button icon={Pencil} disabled={!mayDecide} title={mayDecide ? undefined : onlyDeciders} onClick={() => start("edit")}>Edit grounds</Button>
            {can("withdraw") && <Button icon={Undo2} onClick={() => start("withdraw")}>Withdraw</Button>}
            {can("refer") && <Button icon={ArrowUpRight} disabled={!mayRefer} title={mayRefer ? undefined : onlyLegal} onClick={() => start("refer")}>Refer</Button>}
            {can("reject") && <Button icon={X} disabled={!mayDecide} title={mayDecide ? undefined : onlyDeciders} onClick={() => start("reject")}>Reject</Button>}
            {can("uphold") && <Button variant="primary" icon={Check} disabled={!mayDecide} title={mayDecide ? undefined : onlyDeciders} onClick={() => start("uphold")}>Uphold</Button>}
            {can("reconsider") && <Button variant="primary" icon={Play} disabled={!mayDecide} title={mayDecide ? undefined : onlyDeciders} loading={busy && !open} onClick={() => run(() => api.disputeAction(disputeId, "reconsider"), "Reconsideration started.")}>Start reconsideration</Button>}
            {can("resolve") && <Button variant="primary" icon={Gavel} disabled={!mayRefer} title={mayRefer ? undefined : onlyLegal} onClick={() => start("resolve")}>Record outcome</Button>}
          </>
        )}
      />
      <p className="-mt-2 mb-4 text-[13px] text-ink-600">{status?.help}</p>

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Lodged" value={shortDate(item.opened_at)} hint={`by ${item.opened_by}`} />
        <Stat label={closed ? "Closed" : "Deadline"} value={closed ? shortDate(item.closed_at) : dueText(item.days_to_deadline, item.overdue)} tone={!closed && item.overdue ? "bad" : undefined} hint={closed ? undefined : shortDate(item.deadline)} />
        <Stat label="Route" value={item.channel ? DISPUTE_CHANNELS[item.channel] ?? item.channel : "Not started"} hint={linked(item.linked_ref) ?? undefined} />
        <Stat label="Outcome" value={item.status === "UPHELD" ? "Upheld" : item.status === "REJECTED" ? "Rejected" : item.status === "WITHDRAWN" ? "Withdrawn" : item.status === "RESOLVED" ? "Resolved" : "Pending"} tone={item.status === "UPHELD" ? "ok" : undefined} />
      </div>

      <Tabs<Tab> tabs={[{ key: "overview", label: "Overview" }, { key: "history", label: "History", count: history.length }]} value={tab} onChange={setTab} />
      <div className="mt-4">
        {tab === "overview" && (
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <Panel title="Grounds of the objection"><p className="whitespace-pre-wrap text-sm text-ink-800">{item.grounds || "No grounds were recorded."}</p></Panel>
              {item.outcome && <Panel title={item.status === "REJECTED" ? "Why the decision stands" : "Outcome"}><p className="whitespace-pre-wrap text-sm text-ink-800">{item.outcome}</p></Panel>}
            </div>
            <Panel title="Details">
              <Facts items={[
                { label: "Claim", value: <Link className="text-brand-700 hover:underline" to={`/claims/${encodeURIComponent(item.claim_id)}`}><Ref>{item.claim_id}</Ref></Link> },
                { label: "About", value: DISPUTE_SUBJECTS[item.subject] ?? item.subject },
                { label: "Raised by", value: DISPUTE_RAISERS[item.raised_by] ?? item.raised_by },
                { label: "Lodged", value: dateTime(item.opened_at) },
                { label: "Deadline", value: shortDate(item.deadline) },
                { label: "Linked matter", value: linked(item.linked_ref) ?? "None" },
              ]} />
            </Panel>
          </div>
        )}
        {tab === "history" && <HistoryPanel entries={history} describe={describe} />}
      </div>

      <Dialog
        open={open === "edit"} onClose={() => setOpen(null)} wide title="Edit grounds" description="For correcting what was captured. The earlier wording stays in the history."
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (text.trim()) void run(() => api.updateDispute(disputeId, text.trim()), "Grounds saved."); }}>Save grounds</Button></>}
      >
        <div className="space-y-3">
          <Field label="Grounds" required error={attempted && !text.trim() ? "Record the grounds of the objection." : null}><Textarea rows={5} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} /></Field>
          {alert}
        </div>
      </Dialog>

      <Dialog
        open={outcomeOpen !== null} onClose={() => setOpen(null)} wide title={outcomeOpen ? OUTCOME_DIALOG[outcomeOpen].title : ""} description={outcomeOpen ? OUTCOME_DIALOG[outcomeOpen].body : undefined}
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (outcomeOpen && text.trim()) void run(() => api.disputeAction(disputeId, outcomeOpen, { outcome: text.trim() }), OUTCOME_DIALOG[outcomeOpen].done); }}>{outcomeOpen ? OUTCOME_DIALOG[outcomeOpen].confirm : ""}</Button></>}
      >
        <div className="space-y-3">
          <Field label={outcomeOpen ? OUTCOME_DIALOG[outcomeOpen].label : ""} required error={attempted && !text.trim() ? "This is shown to the objector, so it cannot be blank." : null}><Textarea rows={4} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} /></Field>
          {alert}
        </div>
      </Dialog>

      <Dialog
        open={open === "refer"} onClose={() => setOpen(null)} title="Refer the dispute" description="The dispute leaves internal reconsideration. Legal records the outcome when the tribunal or court has decided."
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => run(() => api.disputeAction(disputeId, "refer", { channel: refer.channel, ...(refer.linked_ref.trim() ? { linked_ref: refer.linked_ref.trim() } : {}) }), "Dispute referred.")}>Refer dispute</Button></>}
      >
        <div className="space-y-4">
          <Field label="Refer to" required hint={refer.channel === "LITIGATION" ? "A litigation matter is opened and linked, unless you give an existing reference below." : "Serious-injury disputes go to the HPCSA tribunal."}>
            <Select value={refer.channel} onChange={(e) => setRefer({ ...refer, channel: e.target.value })}>
              <option value="HPCSA_TRIBUNAL">{DISPUTE_CHANNELS.HPCSA_TRIBUNAL}</option><option value="LITIGATION">{DISPUTE_CHANNELS.LITIGATION}</option>
            </Select>
          </Field>
          <Field label="Existing reference" hint="Optional. A tribunal or case number that already exists."><Input className="font-mono" value={refer.linked_ref} onChange={(e) => setRefer({ ...refer, linked_ref: e.target.value })} /></Field>
          {alert}
        </div>
      </Dialog>

      <ConfirmDialog
        open={open === "withdraw"} onClose={() => setOpen(null)} busy={busy} danger title={`Withdraw dispute ${item.id}?`} confirmLabel="Withdraw dispute"
        description={formError ?? "Use this when the objector no longer pursues the objection. The dispute is closed and cannot be reopened."}
        onConfirm={() => run(() => api.disputeAction(disputeId, "withdraw"), "Dispute withdrawn.")}
      />
    </div>
  );
}
