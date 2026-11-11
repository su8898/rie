// Add a practice to the register, or change what is recorded about one. The practice number is
// the key, so it cannot be changed after the entry exists. Status is changed on the record.

import { useEffect, useState } from "react";
import { ApiError, api } from "../../api";
import { PRACTICE_SETTINGS, PRACTICE_TYPES } from "../../ds/labels";
import { Dialog, useToast } from "../../ds/overlays";
import { Button, Checkbox, Field, Input, Select, Textarea } from "../../ds/primitives";
import type { Practice } from "../../types";

export interface PracticeDraft {
  provider_id: string; practice_name: string; discipline: string; practice_type: string;
  setting: string; professional_nr: string; verified: boolean; notes: string;
}

export const blankPractice = (provider_id = ""): PracticeDraft => ({
  provider_id, practice_name: "", discipline: "", practice_type: "", setting: "", professional_nr: "", verified: true, notes: "",
});

export const draftOf = (p: Partial<Practice> & { provider_id: string }): PracticeDraft => ({
  ...blankPractice(p.provider_id), practice_name: p.practice_name ?? "", discipline: p.discipline ?? "",
  practice_type: p.practice_type ?? "", setting: p.setting ?? "", professional_nr: p.professional_nr ?? "",
  verified: p.verified ?? true, notes: p.notes ?? "",
});

export function PracticeFormDialog({
  open, mode, initial, onClose, onSaved,
}: {
  open: boolean; mode: "add" | "edit"; initial: PracticeDraft; onClose: () => void; onSaved: (p: Practice) => void;
}) {
  const toast = useToast();
  const [draft, setDraft] = useState<PracticeDraft>(initial);
  const [disciplines, setDisciplines] = useState<string[]>([]);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(initial);
    setAttempted(false);
    setError(null);
    api.disciplines().then(setDisciplines).catch(() => setDisciplines([]));
    // `initial` is read once each time the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const set = <K extends keyof PracticeDraft>(k: K, v: PracticeDraft[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const number = draft.provider_id.trim();
  const numberError = !number ? "Enter the practice number." : number.length > 64 ? "At most 64 characters." : null;
  const nameError = !draft.practice_name.trim() ? "Enter the practice name." : null;
  const options = draft.discipline && !disciplines.includes(draft.discipline) ? [draft.discipline, ...disciplines] : disciplines;

  async function save() {
    setAttempted(true);
    setError(null);
    if (numberError || nameError) return;
    setBusy(true);
    try {
      const saved = await api.upsertPractice({ ...draft, provider_id: number, practice_name: draft.practice_name.trim() });
      toast.success(mode === "add" ? `Practice ${saved.provider_id} added to the register.` : "Practice details saved.");
      onSaved(saved);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The practice could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open} onClose={onClose} wide title={mode === "add" ? "Add a practice" : "Edit practice details"}
      description={mode === "add" ? "A new entry is active: the practice may bill the Fund from now on." : "Changes apply to claims received from now on. Claims already decided do not change."}
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>{mode === "add" ? "Add practice" : "Save changes"}</Button></>}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Practice number" required error={attempted ? numberError : null} hint={mode === "edit" ? "The practice number cannot be changed." : "The number the practice bills under."}>
          <Input className="font-mono" value={draft.provider_id} disabled={mode === "edit"} invalid={attempted && Boolean(numberError)} onChange={(e) => set("provider_id", e.target.value)} />
        </Field>
        <Field label="Practice name" required error={attempted ? nameError : null}>
          <Input value={draft.practice_name} invalid={attempted && Boolean(nameError)} onChange={(e) => set("practice_name", e.target.value)} />
        </Field>
        <Field label="Discipline" hint="Lines are priced under this discipline, whatever the claim says.">
          <Select value={draft.discipline} onChange={(e) => set("discipline", e.target.value)}>
            <option value="">Not recorded</option>
            {options.map((d) => <option key={d} value={d}>{d}</option>)}
          </Select>
        </Field>
        <Field label="Setting" hint="A hospital or emergency unit makes its claims hospital accounts.">
          <Select value={draft.setting} onChange={(e) => set("setting", e.target.value)}>
            <option value="">Not recorded</option>
            {Object.entries(PRACTICE_SETTINGS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </Select>
        </Field>
        <Field label="Type">
          <Select value={draft.practice_type} onChange={(e) => set("practice_type", e.target.value)}>
            <option value="">Not recorded</option>
            {Object.entries(PRACTICE_TYPES).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
          </Select>
        </Field>
        <Field label="Council registration number" hint="HPCSA or other statutory council.">
          <Input className="font-mono" value={draft.professional_nr} onChange={(e) => set("professional_nr", e.target.value)} />
        </Field>
        <Field label="Notes" className="sm:col-span-2">
          <Textarea rows={2} maxLength={300} value={draft.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>
        <div className="sm:col-span-2">
          <Checkbox label="Details verified" hint="Confirmed against the practice-number register or the council." checked={draft.verified} onChange={(e) => set("verified", e.target.checked)} />
        </div>
      </div>
      {error && <p className="mt-3 rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{error}</p>}
    </Dialog>
  );
}
