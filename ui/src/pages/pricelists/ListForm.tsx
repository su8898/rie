// The dialogs that act on a price list as a whole: its details, its legal standing, its
// conversion factors, a new edition from it, and retiring it.

import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ApiError, api } from "../../api";
import { LEGAL_STANDING } from "../../ds/labels";
import { Dialog, useToast } from "../../ds/overlays";
import { Button, Field, Input, Select, Textarea } from "../../ds/primitives";
import type { LegalStanding, PriceListDetail, PriceListFactor, PriceListHeaderInput } from "../../types";

const blank: PriceListHeaderInput = {
  name: "", edition: "", source: "", legal_status: "ACCEPTED", status_note: "", effective_from: null, effective_to: null, notes: "",
};

const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);
const ErrorNote = ({ text }: { text: string | null }) =>
  text ? <p className="mt-3 rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{text}</p> : null;

/** Create a price list, or edit the details of one. A published list only lets its notes change. */
export function ListFormDialog({
  open, mode, list, onClose, onSaved,
}: {
  open: boolean; mode: "create" | "edit"; list?: PriceListDetail; onClose: () => void; onSaved: (pl: PriceListDetail) => void;
}) {
  const toast = useToast();
  const [draft, setDraft] = useState<PriceListHeaderInput>(blank);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fixed = mode === "edit" && list?.state === "PUBLISHED";

  useEffect(() => {
    if (!open) return;
    setDraft(list ? {
      name: list.name, edition: list.edition, source: list.source, legal_status: list.legal_status, status_note: list.status_note,
      effective_from: list.effective_from, effective_to: list.effective_to, notes: list.notes,
    } : blank);
    setAttempted(false);
    setError(null);
    // `list` is read once each time the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const set = <K extends keyof PriceListHeaderInput>(k: K, v: PriceListHeaderInput[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const nameError = !draft.name.trim() ? "Give the price list a name." : null;
  const dateError = draft.effective_from && draft.effective_to && draft.effective_to < draft.effective_from ? "The end date is before the start date." : null;

  async function save() {
    setAttempted(true);
    setError(null);
    if (!fixed && (nameError || dateError)) return;
    setBusy(true);
    try {
      const body = { ...draft, name: draft.name.trim() };
      const saved = mode === "create" ? await api.createPriceList(body) : await api.updatePriceList(list!.id, fixed ? { notes: draft.notes } : body);
      toast.success(mode === "create" ? "Price list created as a draft." : "Details saved.");
      onSaved(saved);
    } catch (e) {
      setError(message(e, "The price list could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open} onClose={onClose} wide
      title={mode === "create" ? "New price list" : fixed ? "Edit notes" : "Edit details"}
      description={mode === "create"
        ? "It starts as a draft. Add its entries, then publish it when it is complete."
        : fixed ? "This list is published, so only its notes can change. Use New edition to change anything else." : "A draft can be changed freely until it is published."}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>{mode === "create" ? "Create draft" : "Save changes"}</Button></>}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        {!fixed && (
          <>
            <Field label="Name" required error={attempted ? nameError : null} hint="For example: RAF Tariff 2021/2022." className="sm:col-span-2">
              <Input value={draft.name} maxLength={160} invalid={attempted && Boolean(nameError)} onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field label="Edition" hint="The year or version the publisher gives it.">
              <Input value={draft.edition} maxLength={160} onChange={(e) => set("edition", e.target.value)} />
            </Field>
            <Field label="In effect from" hint="Needed before the list can be published." error={attempted ? dateError : null}>
              <Input type="date" value={draft.effective_from ?? ""} onChange={(e) => set("effective_from", e.target.value || null)} />
            </Field>
            <Field label="Published in" hint="The gazette, circular or agreement it comes from. Needed before publishing." className="sm:col-span-2">
              <Input value={draft.source} maxLength={500} placeholder="For example: Government Gazette No. 46747, 19 August 2022" onChange={(e) => set("source", e.target.value)} />
            </Field>
            <Field label="Legal standing" hint={LEGAL_STANDING[draft.legal_status].help}>
              <Select value={draft.legal_status} onChange={(e) => set("legal_status", e.target.value as LegalStanding)}>
                {Object.entries(LEGAL_STANDING).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </Select>
            </Field>
            <Field label="Reason for the standing" hint="For example the court order or the agreement.">
              <Input value={draft.status_note} maxLength={500} onChange={(e) => set("status_note", e.target.value)} />
            </Field>
          </>
        )}
        <Field label="Notes" className="sm:col-span-2">
          <Textarea rows={3} maxLength={4000} value={draft.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>
      </div>
      <ErrorNote text={error} />
    </Dialog>
  );
}

/** Change the legal standing of a list. Allowed after publication, with a reason. */
export function StandingDialog({ open, list, onClose, onSaved }: { open: boolean; list: PriceListDetail; onClose: () => void; onSaved: (pl: PriceListDetail) => void }) {
  const toast = useToast();
  const others = Object.keys(LEGAL_STANDING).filter((k) => k !== list.legal_status);
  const [standing, setStanding] = useState(others[0]);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (open) { setStanding(others[0]); setReason(""); setError(null); } // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.setPriceListStanding(list.id, standing, reason.trim());
      toast.success(`Legal standing changed to ${LEGAL_STANDING[standing].label.toLowerCase()}.`);
      onSaved(saved);
    } catch (e) {
      setError(message(e, "The legal standing could not be changed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open} onClose={onClose} title="Change legal standing"
      description={`This list is ${LEGAL_STANDING[list.legal_status].label.toLowerCase()} now. The change and your reason are recorded in its history.`}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!reason.trim()} onClick={save}>Change standing</Button></>}
    >
      <div className="space-y-4">
        <Field label="New standing" hint={LEGAL_STANDING[standing].help}>
          <Select value={standing} onChange={(e) => setStanding(e.target.value)}>
            {others.map((k) => <option key={k} value={k}>{LEGAL_STANDING[k].label}</option>)}
          </Select>
        </Field>
        <Field label="Reason" required hint="The court order, judgment or agreement that changes it.">
          <Textarea rows={3} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
      </div>
      <ErrorNote text={error} />
    </Dialog>
  );
}

/** The conversion factors a list prints for turning units into rand. */
export function FactorsDialog({ open, list, onClose, onSaved }: { open: boolean; list: PriceListDetail; onClose: () => void; onSaved: (pl: PriceListDetail) => void }) {
  const toast = useToast();
  const [rows, setRows] = useState<{ name: string; value: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (open) { setRows(list.factors.map((f) => ({ name: f.name, value: String(f.value) }))); setError(null); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const edit = (i: number, k: "name" | "value", v: string) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const filled = rows.filter((r) => r.name.trim() || r.value.trim());
  const bad = filled.some((r) => !r.name.trim() || r.value.trim() === "" || !Number.isFinite(Number(r.value)) || Number(r.value) < 0);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const factors: PriceListFactor[] = filled.map((r) => ({ name: r.name.trim(), value: Number(r.value) }));
      const saved = await api.setPriceListFactors(list.id, factors);
      toast.success("Conversion factors saved.");
      onSaved(saved);
    } catch (e) {
      setError(message(e, "The conversion factors could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open} onClose={onClose} title="Conversion factors"
      description="A list that prints units gives a rand amount per unit. Record each factor as the list states it. Recording a factor does not apply it to any entry."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={bad} onClick={save}>Save factors</Button></>}
    >
      <div className="space-y-2">
        {rows.length === 0 && <p className="text-sm text-ink-500">No factors recorded.</p>}
        {rows.map((r, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input aria-label="Factor name" placeholder="Name, for example consultation" value={r.name} maxLength={80} onChange={(e) => edit(i, "name", e.target.value)} />
            <Input aria-label="Rand per unit" className="tnum w-36 text-right" inputMode="decimal" placeholder="Rand per unit" value={r.value} onChange={(e) => edit(i, "value", e.target.value)} />
            <Button size="sm" variant="ghost" icon={Trash2} aria-label="Remove factor" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))} />
          </div>
        ))}
        <Button size="sm" icon={Plus} onClick={() => setRows((rs) => [...rs, { name: "", value: "" }])}>Add a factor</Button>
        {bad && <p className="text-[13px] text-bad-fg">Each factor needs a name and a value of zero or more.</p>}
      </div>
      <ErrorNote text={error} />
    </Dialog>
  );
}

/** Start a new edition: a draft with the same entries, to change and publish in its turn. */
export function CopyDialog({ open, list, onClose, onSaved }: { open: boolean; list: PriceListDetail; onClose: () => void; onSaved: (pl: PriceListDetail) => void }) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [edition, setEdition] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (open) { setName(""); setEdition(""); setError(null); } }, [open]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.copyPriceList(list.id, name.trim(), edition.trim());
      toast.success("New edition started as a draft.");
      onSaved(saved);
    } catch (e) {
      setError(message(e, "The new edition could not be started."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open} onClose={onClose} title="New edition"
      description={`A draft is created with the ${list.counts.entries.toLocaleString("en-ZA")} entries of this list. Change what differs, then publish it. This list stays as it is.`}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!name.trim()} onClick={save}>Start new edition</Button></>}
    >
      <div className="space-y-4">
        <Field label="Name of the new edition" required hint="It must differ from every other price list.">
          <Input value={name} maxLength={160} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Edition" hint={list.edition ? `This list is edition ${list.edition}.` : undefined}>
          <Input value={edition} maxLength={160} onChange={(e) => setEdition(e.target.value)} />
        </Field>
      </div>
      <ErrorNote text={error} />
    </Dialog>
  );
}

/** Retire a published list from a date. */
export function RetireDialog({ open, list, onClose, onSaved }: { open: boolean; list: PriceListDetail; onClose: () => void; onSaved: (pl: PriceListDetail) => void }) {
  const toast = useToast();
  const [end, setEnd] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (open) { setEnd(""); setNote(""); setError(null); } }, [open]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const saved = await api.retirePriceList(list.id, end || null, note.trim());
      toast.success("Price list retired.");
      onSaved(saved);
    } catch (e) {
      setError(message(e, "The price list could not be retired."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open} onClose={onClose} title="Retire this price list?"
      description="A retired list is kept for the record and can no longer be changed. This cannot be undone."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="danger" loading={busy} onClick={save}>Retire price list</Button></>}
    >
      <div className="space-y-4">
        <Field label="Last day in effect" hint="Leave empty to use today.">
          <Input type="date" value={end} min={list.effective_from ?? undefined} onChange={(e) => setEnd(e.target.value)} />
        </Field>
        <Field label="Note" hint="For example the edition that replaces it.">
          <Input value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
        </Field>
      </div>
      <ErrorNote text={error} />
    </Dialog>
  );
}
