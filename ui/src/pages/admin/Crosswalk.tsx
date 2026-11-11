// Code crosswalk: a code billed under another tariff is paid at the rate of a code in the loaded
// price list. Only a match that has been signed off changes what is paid, so signing off and
// withdrawing a sign-off are deliberate steps with a recorded reason.

import { BadgeCheck, Info, Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../api";
import { DataTable, type Column } from "../../ds/DataTable";
import { CROSSWALK_EFFECT, CROSSWALK_STATUS, shortDate } from "../../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, Ref, Select, Textarea, cx } from "../../ds/primitives";
import { rand } from "../../format";
import type { CrosswalkEntry, CrosswalkStatus } from "../../types";
import { RecentChanges, SectionHeader, errorText, useList } from "./shared";

const STATUS_ORDER: CrosswalkStatus[] = ["CONFIRMED", "PROPOSED", "NEEDS_SME", "NO_RAF_EQUIVALENT"];
const strip = (c: string) => c.replace(/^0+/, "") || "0";

function rates(e: CrosswalkEntry): string | null {
  if (e.target_rates.length === 0) return null;
  const values = e.target_rates.map((r) => r.rate);
  const [low, high] = [Math.min(...values), Math.max(...values)];
  return low === high ? rand(low) : `${rand(low)} to ${rand(high)}, by discipline`;
}

interface Draft { code: string; target_code: string; family: string; description: string; evidence: string; existing: CrosswalkEntry | null }

export default function CrosswalkAdmin() {
  const toast = useToast();
  const { rows, loading, error, reload } = useList(api.adminCrosswalk, "The crosswalk could not be loaded.");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<Draft | null>(null);
  const [changing, setChanging] = useState<CrosswalkEntry | null>(null);
  const [next, setNext] = useState<CrosswalkStatus>("CONFIRMED");
  const [reason, setReason] = useState("");
  const [removing, setRemoving] = useState<CrosswalkEntry | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const shown = useMemo(() => {
    const text = q.trim().toLowerCase();
    return rows.filter((r) => (!status || r.status === status)
      && (!text || [r.billed_as, r.code, r.target_code ?? "", r.description, r.family].some((v) => v.toLowerCase().includes(text))));
  }, [rows, q, status]);
  const counts = useMemo(() => Object.fromEntries(STATUS_ORDER.map((s) => [s, rows.filter((r) => r.status === s).length])), [rows]);
  const inUse = rows.filter((r) => r.effect === "IN_USE").length;
  const idle = rows.filter((r) => r.status === "CONFIRMED" && r.effect !== "IN_USE").length;
  const done = async (message: string) => { toast.success(message); setEditing(null); setChanging(null); setRemoving(null); setVersion((v) => v + 1); await reload(); };

  const open = (e?: CrosswalkEntry) => {
    setAttempted(false);
    setFormError(null);
    setEditing(e ? { code: e.billed_as, target_code: e.target_code ?? "", family: e.family, description: e.description, evidence: e.evidence, existing: e }
      : { code: "", target_code: "", family: "", description: "", evidence: "", existing: null });
  };
  const openStatus = (e: CrosswalkEntry) => {
    setChanging(e);
    setNext(e.status === "PROPOSED" ? "CONFIRMED" : e.status === "CONFIRMED" ? "PROPOSED" : e.target_code ? "PROPOSED" : e.status === "NEEDS_SME" ? "NO_RAF_EQUIVALENT" : "NEEDS_SME");
    setReason("");
    setFormError(null);
  };

  const code = editing?.code.trim() ?? "";
  const target = editing?.target_code.trim() ?? "";
  const codeError = !code ? "Enter the code as it is billed." : !editing?.existing && rows.some((r) => r.code === strip(code)) ? "That code already has an entry. Edit it instead." : null;
  const targetError = target && strip(target) === strip(code) ? "A code cannot be matched to itself." : null;
  const retarget = Boolean(editing?.existing && editing.existing.status === "CONFIRMED" && strip(target || "-") !== strip(editing.existing.target_code ?? "-"));

  async function save() {
    setAttempted(true);
    if (!editing || codeError || targetError) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.saveCrosswalkEntry({ code, target_code: target || null, family: editing.family.trim(), description: editing.description.trim(), evidence: editing.evidence.trim() });
      await done(retarget ? `Entry for ${code} saved. It needs a new sign-off before it is used.` : `Entry for ${code} saved.`);
    } catch (e) {
      setFormError(errorText(e, "The entry could not be saved."));
    } finally {
      setBusy(false);
    }
  }
  async function changeStatus() {
    if (!changing) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.setCrosswalkStatus(changing.code, next, reason.trim());
      await done(next === "CONFIRMED" ? `Match for ${changing.billed_as} signed off.` : changing.status === "CONFIRMED" ? `Sign-off for ${changing.billed_as} withdrawn.` : `Status of ${changing.billed_as} changed.`);
    } catch (e) {
      setFormError(errorText(e, "The status could not be changed."));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api.removeCrosswalkEntry(removing.code);
      await done(`Entry for ${removing.billed_as} removed.`);
    } catch (e) {
      toast.error(errorText(e, "The entry could not be removed."));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<CrosswalkEntry>[] = [
    { key: "billed", header: "Billed code", render: (r) => (
      <div className="max-w-[40ch]">
        <Ref className="font-medium text-ink-900">{r.billed_as}</Ref>
        <div className="truncate text-[13px] text-ink-600" title={r.description}>{r.description || "No description"}</div>
        {r.family && <div className="text-xs text-ink-500">{r.family}</div>}
      </div>
    ) },
    { key: "target", header: "Paid at", render: (r) => r.target_code ? (
      <div>
        <Ref className="font-medium text-ink-900">{r.target_code}</Ref>
        <div className="tnum text-[13px] text-ink-600">{rates(r) ?? "No rate loaded"}</div>
      </div>
    ) : <span className="text-ink-500">No code chosen</span> },
    { key: "status", header: "Status", render: (r) => (
      <div>
        <Badge tone={CROSSWALK_STATUS[r.status].tone} dot>{CROSSWALK_STATUS[r.status].label}</Badge>
        {r.status === "CONFIRMED" && r.confirmed_by && <div className="mt-1 text-xs text-ink-500">{r.confirmed_at ? `${shortDate(r.confirmed_at)} by ${r.confirmed_by}` : `From the ${r.confirmed_by}`}</div>}
      </div>
    ) },
    { key: "effect", header: "Effect on pricing", render: (r) => (
      <div className="max-w-[34ch]">
        <Badge tone={CROSSWALK_EFFECT[r.effect].tone}>{CROSSWALK_EFFECT[r.effect].label}</Badge>
        <div className="mt-1 text-xs text-ink-500">{CROSSWALK_EFFECT[r.effect].help}</div>
      </div>
    ) },
    { key: "actions", header: "", align: "right", render: (r) => (
      <div className="flex justify-end gap-1">
        <Button size="sm" variant={r.status === "PROPOSED" ? "primary" : "secondary"} icon={BadgeCheck} onClick={() => openStatus(r)}>{r.status === "PROPOSED" ? "Sign off" : "Status"}</Button>
        <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Edit entry ${r.billed_as}`} onClick={() => open(r)} />
        <Button size="sm" variant="ghost" icon={Trash2} aria-label={`Remove entry ${r.billed_as}`} onClick={() => setRemoving(r)} />
      </div>
    ) },
  ];

  const options = changing ? STATUS_ORDER.filter((s) => s !== changing.status) : [];
  const needsTarget = (next === "CONFIRMED" || next === "PROPOSED") && !changing?.target_code;
  const needsReason = next === "CONFIRMED" && !reason.trim();

  return (
    <div>
      <SectionHeader
        title="Code crosswalk"
        description="A code billed under another tariff can be paid at the rate of a code in the loaded price list. Each entry is a proposed match until it is signed off."
        actions={<Button variant="primary" icon={Plus} onClick={() => open()}>Add entry</Button>}
      />

      <div className="mb-3 flex items-start gap-2 rounded-lg border border-info-line bg-info-bg px-4 py-3 text-sm text-info-fg">
        <Info size={16} className="mt-0.5 shrink-0" aria-hidden />
        <span>
          Only a signed-off match changes what is paid. Signing off, withdrawing or removing one takes effect on the next claim assessed. Claims already decided do not change.
          {!loading && ` ${inUse} ${inUse === 1 ? "match is" : "matches are"} in use now.`}
          {idle > 0 && ` ${idle} signed-off ${idle === 1 ? "match does" : "matches do"} nothing: see the last column.`}
        </span>
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Status">
        {[{ key: "", label: "All", n: rows.length }, ...STATUS_ORDER.map((s) => ({ key: s as string, label: CROSSWALK_STATUS[s].label, n: counts[s] }))].map((v) => (
          <button
            key={v.key || "all"} role="tab" aria-selected={status === v.key} onClick={() => setStatus(v.key)}
            className={cx("rounded-full border px-3 py-1.5 text-[13px] font-medium transition", status === v.key ? "border-ink-900 bg-ink-900 text-white" : "border-line-strong bg-white text-ink-600 hover:border-ink-400 hover:text-ink-900")}
          >
            {v.label}<span className="tnum ml-1.5 opacity-70">{v.n}</span>
          </button>
        ))}
      </div>
      <div className="mb-3 rounded-lg border border-line bg-white p-3 shadow-panel"><div className="sm:w-96"><Input placeholder="Billed code, the code it is paid at, or words in the description" aria-label="Search the crosswalk" value={q} onChange={(e) => setQ(e.target.value)} /></div></div>

      {error ? <ErrorBlock message={error} onRetry={reload} /> : (
        <DataTable
          columns={columns} rows={shown} rowKey={(r) => r.code} loading={loading}
          empty={<EmptyState title={q || status ? "No entry matches" : "The crosswalk is empty"} body={q || status ? "Change the search or the status." : "Add an entry for a code that is billed but has no rate of its own."} />}
          footer={<span className="text-[13px] text-ink-500">{shown.length} of {rows.length} entries</span>}
        />
      )}
      <RecentChanges area="crosswalk" version={version} />

      <Dialog
        open={editing !== null} onClose={() => setEditing(null)} wide
        title={editing?.existing ? `Edit entry ${editing.existing.billed_as}` : "Add a crosswalk entry"}
        description={editing?.existing ? "Changing the code it is paid at needs a new sign-off. Changing the wording does not." : "A new entry is a proposal. It changes nothing until it is signed off."}
        footer={<><Button onClick={() => setEditing(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>{editing?.existing ? "Save changes" : "Add entry"}</Button></>}
      >
        {editing && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Billed code" required error={attempted ? codeError : null} hint={editing.existing ? "The billed code cannot be changed. Remove the entry and add the right one." : "The code as providers bill it."}>
              <Input className="font-mono" value={editing.code} maxLength={32} disabled={Boolean(editing.existing)} invalid={attempted && Boolean(codeError)} onChange={(e) => setEditing({ ...editing, code: e.target.value })} />
            </Field>
            <Field label="Code it is paid at" error={attempted ? targetError : null} hint="A code in the loaded price list. Leave empty if none has been chosen yet.">
              <Input className="font-mono" value={editing.target_code} maxLength={32} invalid={attempted && Boolean(targetError)} onChange={(e) => setEditing({ ...editing, target_code: e.target.value })} />
            </Field>
            <Field label="What is billed" className="sm:col-span-2">
              <Input value={editing.description} maxLength={300} placeholder="For example: follow-up visit" onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
            </Field>
            <Field label="Family" hint="A group to find it by, for example consultation.">
              <Input value={editing.family} maxLength={80} onChange={(e) => setEditing({ ...editing, family: e.target.value })} />
            </Field>
            <Field label="Evidence" hint="Why the two codes are equivalent, and who says so." className="sm:col-span-2">
              <Textarea rows={3} maxLength={1000} value={editing.evidence} onChange={(e) => setEditing({ ...editing, evidence: e.target.value })} />
            </Field>
          </div>
        )}
        {retarget && <p className="mt-3 rounded-md border border-warn-line bg-warn-bg px-3 py-2 text-[13px] text-warn-fg">This match is signed off. Saving a different code returns it to proposed, and it stops affecting pricing until it is signed off again.</p>}
        {formError && <p className="mt-3 rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
      </Dialog>

      <Dialog
        open={changing !== null} onClose={() => setChanging(null)}
        title={changing ? `Status of ${changing.billed_as}` : "Status"}
        description={changing ? `Now ${CROSSWALK_STATUS[changing.status].label.toLowerCase()}${changing.target_code ? `, matched to ${changing.target_code}${rates(changing) ? ` at ${rates(changing)}` : ""}` : ""}.` : undefined}
        footer={<><Button onClick={() => setChanging(null)}>Cancel</Button><Button variant={changing?.status === "CONFIRMED" ? "danger" : "primary"} loading={busy} disabled={needsTarget || needsReason} onClick={changeStatus}>{next === "CONFIRMED" ? "Sign off" : changing?.status === "CONFIRMED" ? "Withdraw sign-off" : "Change status"}</Button></>}
      >
        <div className="space-y-4">
          <Field label="New status" hint={CROSSWALK_STATUS[next].help}>
            <Select value={next} onChange={(e) => setNext(e.target.value as CrosswalkStatus)}>
              {options.map((s) => <option key={s} value={s}>{CROSSWALK_STATUS[s].label}</option>)}
            </Select>
          </Field>
          <Field label={next === "CONFIRMED" ? "Who signed it off, and on what basis" : "Reason"} required={next === "CONFIRMED"} hint={next === "CONFIRMED" ? "For example: Dr A Example, tariff committee, minute of 11 November 2026." : "Recorded with the entry."}>
            <Textarea rows={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          {needsTarget && <p className="rounded-md border border-warn-line bg-warn-bg px-3 py-2 text-[13px] text-warn-fg">This entry names no code to be paid at. Edit it and add one first.</p>}
          {next === "CONFIRMED" && changing && !needsTarget && (
            <p className="rounded-md border border-warn-line bg-warn-bg px-3 py-2 text-[13px] text-warn-fg">
              {changing.own_rate ? `Code ${changing.billed_as} has a rate of its own, so this match will be ignored.`
                : rates(changing) ? `From the next claim assessed, lines under ${changing.billed_as} are paid up to ${rates(changing)}.`
                  : `Code ${changing.target_code} has no rate loaded, so signing off changes nothing until it does.`}
            </p>
          )}
          {(next === "NEEDS_SME" || next === "NO_RAF_EQUIVALENT") && changing?.target_code && <p className="rounded-md border border-warn-line bg-warn-bg px-3 py-2 text-[13px] text-warn-fg">The code it is paid at ({changing.target_code}) will be cleared.</p>}
          {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
        </div>
      </Dialog>

      <ConfirmDialog
        open={removing !== null} onClose={() => setRemoving(null)} busy={busy} danger onConfirm={remove}
        title={`Remove the entry for ${removing?.billed_as ?? ""}?`} confirmLabel="Remove entry"
        description={removing?.effect === "IN_USE" ? "This match is in use. From the next claim assessed, lines under this code have no rate to be compared with." : "The entry is not in use, so pricing does not change."}
      />
    </div>
  );
}
