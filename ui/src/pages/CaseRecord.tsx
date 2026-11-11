// One case. What it is about and how urgent, who has it, the notes made on it, its outcome once
// closed, and every step taken. Actions are offered only to the role that owns the case.

import { ArrowUpRight, CheckCircle2, Hand, Pencil, Send } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { CASE_LANES, CASE_PRIORITIES, CASE_STATUS, CASE_VERDICTS, ROLES, dateTime, dueText, shortDate, workError } from "../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Facts, Field, Input, LoadingBlock, PageHeader, Panel, Ref, Select, Stat, Tabs, Textarea } from "../ds/primitives";
import { rand } from "../format";
import type { CaseItem, CaseNote, HistoryEntry } from "../types";
import { HistoryPanel } from "./work/shared";

type Tab = "overview" | "notes" | "history";
type Open = "edit" | "close" | "escalate" | null;
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? workError(e.message) : fallback);

function describe(h: HistoryEntry): { title: string; note?: string } {
  if (h.action === "assign") return { title: "Taken on" };
  if (h.action === "escalate") return { title: "Escalated to the investigators" };
  if (h.action === "close") {
    const v = h.detail.verdict ? CASE_VERDICTS[String(h.detail.verdict)] ?? String(h.detail.verdict) : null;
    return { title: v ? `Closed: ${v}` : "Closed", note: h.detail.root_cause ? String(h.detail.root_cause) : undefined };
  }
  if (h.action === "edit") {
    const ch = (h.detail.changes ?? {}) as Record<string, { from: unknown; to: unknown }>;
    const parts = Object.entries(ch).map(([k, v]) => k === "priority" ? `priority from ${CASE_PRIORITIES[Number(v.from)]?.label ?? v.from} to ${CASE_PRIORITIES[Number(v.to)]?.label ?? v.to}`
      : k === "rand_at_stake" ? `amount at stake from ${rand(Number(v.from))} to ${rand(Number(v.to))}` : "the reason");
    return { title: "Details changed", note: parts.length ? `Changed ${parts.join(", ")}.` : undefined };
  }
  return { title: h.action };
}

export default function CaseRecordPage() {
  const { id = "" } = useParams();
  const caseId = Number(id);
  const toast = useToast();
  const { user } = useAuth();
  const [item, setItem] = useState<CaseItem | null>(null);
  const [notes, setNotes] = useState<CaseNote[]>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [open, setOpen] = useState<Open>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [edit, setEdit] = useState({ priority: "3", reason: "", stake: "" });
  const [close, setClose] = useState({ verdict: "", root_cause: "", recovered: "", prevented: "" });
  const [attempted, setAttempted] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [c, n, h] = await Promise.all([api.caseGet(caseId), api.caseNotes(caseId), api.caseHistory(caseId)]);
      setItem(c); setNotes(n); setHistory(h);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "There is no case with that number." : message(e, "The case could not be loaded."));
    }
  }, [caseId]);
  useEffect(() => { setItem(null); setTab("overview"); void load(); }, [load]);

  const crumbs = [{ label: "Work" }, { label: "Cases", to: "/cases" }, { label: `Case ${id}` }];
  if (!Number.isInteger(caseId) || error) return <div><PageHeader crumbs={crumbs} title={`Case ${id}`} /><ErrorBlock message={error ?? "There is no case with that number."} onRetry={error ? load : undefined} /></div>;
  if (!item) return <div><PageHeader crumbs={crumbs} title={`Case ${id}`} /><LoadingBlock /></div>;

  const status = CASE_STATUS[item.status];
  const closed = item.status === "CLOSED";
  const ownerRole = item.status === "ESCALATED" ? "INVESTIGATOR" : item.owner_role ?? "";
  const canAct = user?.role === "ADMIN" || user?.role === ownerRole;
  const blocked = canAct ? null : `Only ${ROLES[ownerRole]?.label.toLowerCase() ?? ownerRole} users can act on this case.`;
  const can = (a: string) => item.actions.includes(a);

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
  const openEdit = () => { setEdit({ priority: String(item.priority), reason: item.reason, stake: String(item.rand_at_stake || "") }); setAttempted(false); setFormError(null); setOpen("edit"); };
  const openClose = () => { setClose({ verdict: "", root_cause: "", recovered: "", prevented: "" }); setAttempted(false); setFormError(null); setOpen("close"); };
  const editErrors = { reason: !edit.reason.trim() ? "A case needs a reason." : null, stake: edit.stake !== "" && !(Number(edit.stake) >= 0) ? "Enter an amount in rand." : null };
  const closeErrors = {
    verdict: !close.verdict ? "Choose the outcome." : null,
    root_cause: !close.root_cause.trim() ? "Say what was found." : null,
    money: [close.recovered, close.prevented].some((v) => v !== "" && !(Number(v) >= 0)) ? "Enter amounts in rand, or leave them blank." : null,
  };
  async function addNote() {
    if (!note.trim()) return;
    setBusy(true);
    try {
      await api.addCaseNote(caseId, note.trim());
      setNote("");
      setNotes(await api.caseNotes(caseId));
      toast.success("Note added.");
    } catch (e) {
      toast.error(message(e, "The note could not be added."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        crumbs={crumbs} title={`Case ${item.id}`}
        meta={<><Badge tone={status?.tone ?? "neutral"} dot>{status?.label ?? item.status}</Badge><Badge>{CASE_LANES[item.lane]?.label ?? item.lane}</Badge></>}
        subtitle={item.reason}
        actions={!closed && (
          <>
            <Button icon={Pencil} disabled={!canAct} title={blocked ?? undefined} onClick={openEdit}>Edit</Button>
            {can("escalate") && <Button icon={ArrowUpRight} disabled={!canAct} title={blocked ?? undefined} onClick={() => { setFormError(null); setOpen("escalate"); }}>Escalate</Button>}
            {can("close") && <Button icon={CheckCircle2} disabled={!canAct} title={blocked ?? undefined} onClick={openClose}>Close case</Button>}
            {can("assign") && <Button variant="primary" icon={Hand} disabled={!canAct} title={blocked ?? undefined} loading={busy && !open} onClick={() => run(() => api.caseAction(caseId, "assign"), "The case is now yours.")}>Take this case</Button>}
          </>
        )}
      />
      {!closed && blocked && <p className="-mt-2 mb-4 text-[13px] text-ink-500">{blocked}</p>}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Priority" value={CASE_PRIORITIES[item.priority]?.label ?? item.priority} hint={item.sla_days ? `To be resolved within ${item.sla_days} day${item.sla_days === 1 ? "" : "s"}` : undefined} />
        <Stat label={closed ? "Closed" : "Due"} value={closed ? shortDate(item.closed_at) : dueText(item.days_to_sla, item.overdue)} tone={!closed && item.overdue ? "bad" : undefined} hint={closed ? undefined : `Due ${shortDate(item.due_at)}`} />
        <Stat label="At stake" value={item.rand_at_stake > 0 ? rand(item.rand_at_stake) : "Not recorded"} />
        <Stat label="With" value={item.assigned_to ?? (closed ? "Nobody" : "Unassigned")} hint={!item.assigned_to && !closed ? `In the ${ROLES[ownerRole]?.label.toLowerCase() ?? ownerRole} queue` : undefined} />
      </div>

      <Tabs<Tab> tabs={[{ key: "overview", label: "Overview" }, { key: "notes", label: "Notes", count: notes.length }, { key: "history", label: "History", count: history.length }]} value={tab} onChange={setTab} />

      <div className="mt-4">
        {tab === "overview" && (
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              {closed && (
                <Panel title="Outcome">
                  <Facts items={[
                    { label: "Outcome", value: CASE_VERDICTS[item.verdict ?? ""] ?? "Not recorded" },
                    { label: "Closed", value: dateTime(item.closed_at) },
                    { label: "Recovered", value: <span className="tnum">{rand(item.rand_recovered)}</span> },
                    { label: "Prevented", value: <span className="tnum">{rand(item.rand_prevented)}</span> },
                  ]} />
                  <div className="mt-3 border-t border-line pt-3 text-sm text-ink-800"><span className="text-ink-500">What was found: </span>{item.root_cause || "Not recorded"}</div>
                </Panel>
              )}
              <Panel title="About this case">
                <p className="mb-4 whitespace-pre-wrap text-sm text-ink-800">{item.reason}</p>
                <Facts items={[
                  { label: "Kind", value: CASE_LANES[item.lane]?.label ?? item.lane },
                  { label: "Claim", value: item.claim_id ? <Link className="text-brand-700 hover:underline" to={`/claims/${encodeURIComponent(item.claim_id)}`}><Ref>{item.claim_id}</Ref></Link> : "Not linked to a claim" },
                  { label: "Opened", value: `${dateTime(item.opened_at)} by ${item.opened_by}` },
                  { label: "Owned by", value: ROLES[ownerRole]?.label ?? ownerRole },
                ]} />
              </Panel>
            </div>
            <Panel title="Latest notes" actions={<button className="text-[13px] text-brand-700 hover:underline" onClick={() => setTab("notes")}>All notes</button>}>
              {notes.length === 0 ? <p className="text-sm text-ink-500">No notes yet.</p> : (
                <ul className="space-y-3">{notes.slice(-3).reverse().map((n) => <li key={n.id}><div className="whitespace-pre-wrap text-sm text-ink-800">{n.body}</div><div className="mt-0.5 text-xs text-ink-500">{n.author} · {dateTime(n.created_at)}</div></li>)}</ul>
              )}
            </Panel>
          </div>
        )}

        {tab === "notes" && (
          <Panel title="Notes" description="Working notes on the case. A note cannot be changed or removed once added." flush>
            <div className="border-b border-line px-4 py-3">
              <Textarea rows={3} maxLength={2000} placeholder="Add a note" aria-label="New note" value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="mt-2 flex justify-end"><Button variant="primary" size="sm" icon={Send} disabled={!note.trim()} loading={busy} onClick={addNote}>Add note</Button></div>
            </div>
            {notes.length === 0 ? <EmptyState title="No notes yet" body="Record what you checked and what you found." /> : (
              <ul className="divide-y divide-line">{[...notes].reverse().map((n) => <li key={n.id} className="px-4 py-3"><div className="whitespace-pre-wrap text-sm text-ink-800">{n.body}</div><div className="mt-1 text-xs text-ink-500">{n.author} · {dateTime(n.created_at)}</div></li>)}</ul>
            )}
          </Panel>
        )}

        {tab === "history" && <HistoryPanel entries={history} describe={describe} />}
      </div>

      <Dialog
        open={open === "edit"} onClose={() => setOpen(null)} wide title="Edit case" description="Changing the priority resets the due date, counted from the day the case was opened."
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (!editErrors.reason && !editErrors.stake) void run(() => api.updateCase(caseId, { priority: Number(edit.priority), reason: edit.reason.trim(), rand_at_stake: Number(edit.stake) || 0 }), "Case updated."); }}>Save changes</Button></>}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Priority" required hint={`Due within ${CASE_PRIORITIES[Number(edit.priority)].days} day${CASE_PRIORITIES[Number(edit.priority)].days === 1 ? "" : "s"} of opening.`}>
            <Select value={edit.priority} onChange={(e) => setEdit({ ...edit, priority: e.target.value })}>
              {Object.entries(CASE_PRIORITIES).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
            </Select>
          </Field>
          <Field label="Amount at stake (R)" error={attempted ? editErrors.stake : null}>
            <Input type="number" min={0} step="0.01" value={edit.stake} onChange={(e) => setEdit({ ...edit, stake: e.target.value })} />
          </Field>
          <Field label="Reason" required error={attempted ? editErrors.reason : null} className="sm:col-span-2">
            <Textarea rows={3} maxLength={500} value={edit.reason} onChange={(e) => setEdit({ ...edit, reason: e.target.value })} />
          </Field>
          {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg sm:col-span-2" role="alert">{formError}</p>}
        </div>
      </Dialog>

      <Dialog
        open={open === "close"} onClose={() => setOpen(null)} wide title={`Close case ${item.id}`} description="The outcome is used to measure how reliable each finding is, so record it honestly. A closed case cannot be reopened or changed."
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (!closeErrors.verdict && !closeErrors.root_cause && !closeErrors.money) void run(() => api.caseAction(caseId, "close", { verdict: close.verdict, root_cause: close.root_cause.trim(), recovered: Number(close.recovered) || 0, prevented: Number(close.prevented) || 0 }), "Case closed."); }}>Close case</Button></>}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Outcome" required error={attempted ? closeErrors.verdict : null} className="sm:col-span-2">
            <Select value={close.verdict} onChange={(e) => setClose({ ...close, verdict: e.target.value })}>
              <option value="">Choose</option>
              {Object.entries(CASE_VERDICTS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </Select>
          </Field>
          <Field label="What was found" required error={attempted ? closeErrors.root_cause : null} className="sm:col-span-2">
            <Textarea rows={3} maxLength={500} value={close.root_cause} onChange={(e) => setClose({ ...close, root_cause: e.target.value })} placeholder="The cause, in a sentence or two" />
          </Field>
          <Field label="Recovered (R)" hint="Money paid out and got back." error={attempted ? closeErrors.money : null}>
            <Input type="number" min={0} step="0.01" value={close.recovered} onChange={(e) => setClose({ ...close, recovered: e.target.value })} />
          </Field>
          <Field label="Prevented (R)" hint="Money that would have been paid.">
            <Input type="number" min={0} step="0.01" value={close.prevented} onChange={(e) => setClose({ ...close, prevented: e.target.value })} />
          </Field>
          {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg sm:col-span-2" role="alert">{formError}</p>}
        </div>
      </Dialog>

      <ConfirmDialog
        open={open === "escalate"} onClose={() => setOpen(null)} busy={busy} title={`Escalate case ${item.id}?`} confirmLabel="Escalate"
        description={formError ?? "The case goes to the investigators' queue and is no longer assigned to anyone. Only an investigator can close an escalated case."}
        onConfirm={() => run(() => api.caseAction(caseId, "escalate"), "Case escalated to the investigators.")}
      />
    </div>
  );
}
