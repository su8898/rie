// Entries of a draft price list: add or edit one, or load many from a file.

import { Upload } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { ApiError, api } from "../../api";
import { Dialog, useToast } from "../../ds/overlays";
import { Button, Field, Input, Textarea, cx } from "../../ds/primitives";
import type { PriceListDetail, PriceListEntry, PriceListImportResult } from "../../types";

interface EntryDraft {
  discipline: string; code: string; alt_code: string; price_column: string; description: string;
  units: string; units_suffix: string; value_rand: string; unit_of_issue: string; source_page: string; note: string;
}

const blankEntry = (discipline = "", column = "standard"): EntryDraft => ({
  discipline, code: "", alt_code: "", price_column: column, description: "", units: "", units_suffix: "", value_rand: "",
  unit_of_issue: "", source_page: "", note: "",
});

/** "1 404,46" or "1404.46" as a number; null when blank; NaN when it cannot be read. */
function amount(text: string): number | null {
  const s = text.trim().replace(/\s/g, "");
  if (!s) return null;
  if (s.includes(",") && s.includes(".")) return NaN;
  const n = Number(s.replace(",", "."));
  return Number.isFinite(n) && n >= 0 ? n : NaN;
}

export function EntryFormDialog({
  open, list, entry, defaults, onClose, onSaved,
}: {
  open: boolean; list: PriceListDetail; entry: PriceListEntry | null; defaults?: { discipline?: string; column?: string };
  onClose: () => void; onSaved: () => void;
}) {
  const toast = useToast();
  const ids = useId();
  const [draft, setDraft] = useState<EntryDraft>(blankEntry());
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(entry ? {
      discipline: entry.discipline, code: entry.code, alt_code: entry.alt_code, price_column: entry.price_column, description: entry.description,
      units: entry.units == null ? "" : String(entry.units), units_suffix: entry.units_suffix,
      value_rand: entry.value_rand == null ? "" : String(entry.value_rand), unit_of_issue: entry.unit_of_issue,
      source_page: entry.source_page, note: entry.note,
    } : blankEntry(defaults?.discipline, defaults?.column || "standard"));
    setAttempted(false);
    setError(null);
    // `entry` and `defaults` are read once each time the dialog opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const set = <K extends keyof EntryDraft>(k: K, v: string) => setDraft((d) => ({ ...d, [k]: v }));
  const units = amount(draft.units);
  const value = amount(draft.value_rand);
  const idError = !draft.code.trim() && !draft.alt_code.trim() && !draft.description.trim() ? "Enter a code, or a description for a line printed without one." : null;
  const unitsError = Number.isNaN(units) ? "Enter a number of zero or more, without a thousands separator." : null;
  const valueError = Number.isNaN(value) ? "Enter an amount of zero or more, without a thousands separator." : null;

  async function save() {
    setAttempted(true);
    setError(null);
    if (idError || unitsError || valueError) return;
    setBusy(true);
    try {
      const body = {
        discipline: draft.discipline.trim(), code: draft.code.trim(), alt_code: draft.alt_code.trim(),
        price_column: draft.price_column.trim() || "standard", description: draft.description.trim(), units, units_suffix: draft.units_suffix.trim(),
        value_rand: value, unit_of_issue: draft.unit_of_issue.trim(), source_page: draft.source_page.trim(), note: draft.note.trim(),
      };
      if (entry) await api.updatePriceListEntry(list.id, entry.id, body);
      else await api.addPriceListEntry(list.id, body);
      toast.success(entry ? "Entry saved." : "Entry added.");
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The entry could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open} onClose={onClose} wide title={entry ? "Edit entry" : "Add an entry"}
      description="One figure in the list: a code, in a discipline, under one price column. Enter codes exactly as the list prints them."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>{entry ? "Save entry" : "Add entry"}</Button></>}
    >
      <div className="grid gap-4 sm:grid-cols-6">
        <Field label="Code" error={attempted ? idError : null} className="sm:col-span-2">
          <Input className="font-mono" value={draft.code} maxLength={40} invalid={attempted && Boolean(idError)} onChange={(e) => set("code", e.target.value)} />
        </Field>
        <Field label="Second code" hint="If the list prints two." className="sm:col-span-2">
          <Input className="font-mono" value={draft.alt_code} maxLength={40} onChange={(e) => set("alt_code", e.target.value)} />
        </Field>
        <Field label="Page" hint="In the source." className="sm:col-span-2">
          <Input value={draft.source_page} maxLength={20} onChange={(e) => set("source_page", e.target.value)} />
        </Field>
        <Field label="Discipline" hint="The section of the list it sits in." className="sm:col-span-3">
          <Input list={`${ids}-disc`} value={draft.discipline} maxLength={120} onChange={(e) => set("discipline", e.target.value)} />
          <datalist id={`${ids}-disc`}>{list.disciplines.map((d) => <option key={d.discipline} value={d.discipline} />)}</datalist>
        </Field>
        <Field label="Price column" hint="For example specialist. Use standard when there is only one." className="sm:col-span-3">
          <Input list={`${ids}-col`} value={draft.price_column} maxLength={80} onChange={(e) => set("price_column", e.target.value)} />
          <datalist id={`${ids}-col`}>{list.columns.map((c) => <option key={c} value={c} />)}</datalist>
        </Field>
        <Field label="Description" className="sm:col-span-6">
          <Textarea rows={2} maxLength={4000} value={draft.description} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <Field label="Units" error={attempted ? unitsError : null} hint="Leave empty if none is printed." className="sm:col-span-2">
          <Input className="tnum text-right" inputMode="decimal" value={draft.units} invalid={attempted && Boolean(unitsError)} onChange={(e) => set("units", e.target.value)} />
        </Field>
        <Field label="Units marker" hint="Letters printed after the units." className="sm:col-span-1">
          <Input value={draft.units_suffix} maxLength={8} onChange={(e) => set("units_suffix", e.target.value)} />
        </Field>
        <Field label="Rand value" error={attempted ? valueError : null} hint="Leave empty if none is printed." className="sm:col-span-2">
          <Input className="tnum text-right" inputMode="decimal" value={draft.value_rand} invalid={attempted && Boolean(valueError)} onChange={(e) => set("value_rand", e.target.value)} />
        </Field>
        <Field label="Unit of issue" hint="Each, pair." className="sm:col-span-1">
          <Input value={draft.unit_of_issue} maxLength={20} onChange={(e) => set("unit_of_issue", e.target.value)} />
        </Field>
        <Field label="Note" className="sm:col-span-6">
          <Input value={draft.note} maxLength={500} onChange={(e) => set("note", e.target.value)} />
        </Field>
      </div>
      {error && <p className="mt-3 rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{error}</p>}
    </Dialog>
  );
}

const LARGE = 200_000; // characters; above this the file is not echoed into the text box

/** Load entries from a CSV file. Rows that can be read are loaded; the others are reported. */
export function ImportEntriesDialog({ open, list, onClose, onLoaded }: { open: boolean; list: PriceListDetail; onClose: () => void; onLoaded: () => void }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [csv, setCsv] = useState("");
  const [fileName, setFileName] = useState("");
  const [mode, setMode] = useState<"append" | "replace">("append");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PriceListImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (open) { setCsv(""); setFileName(""); setMode("append"); setResult(null); setError(null); } }, [open]);

  const dataRows = csv.trim() ? Math.max(0, csv.trim().split(/\r?\n/).length - 1) : 0;
  const large = csv.length > LARGE;
  const has = list.counts.entries;

  async function readFile(file: File | undefined) {
    if (!file) return;
    setCsv(await file.text());
    setFileName(file.name);
    setResult(null);
    setError(null);
  }
  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.importPriceListEntries(list.id, csv, mode);
      setResult(res);
      if (res.added || res.removed) onLoaded();
      if (res.added) toast.success(`${res.added.toLocaleString("en-ZA")} entr${res.added === 1 ? "y" : "ies"} loaded.`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The file could not be loaded.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open} onClose={onClose} wide title="Load entries from a file"
      description="A CSV file with a header row. It needs a code column and at least one of value_rand, units or description. It may also have discipline, alt_code, price_column, units_suffix, unit_of_issue, source_page and note."
      footer={<><Button onClick={onClose}>{result ? "Close" : "Cancel"}</Button><Button variant={mode === "replace" && has > 0 ? "danger" : "primary"} loading={busy} disabled={!csv.trim() || Boolean(result)} onClick={run}>{mode === "replace" && has > 0 ? "Replace entries" : "Load"}{dataRows ? ` ${dataRows.toLocaleString("en-ZA")} row${dataRows === 1 ? "" : "s"}` : ""}</Button></>}
    >
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => { void readFile(e.target.files?.[0]); e.target.value = ""; }} />
          <Button icon={Upload} onClick={() => fileRef.current?.click()}>Choose a file</Button>
          <span className="text-[13px] text-ink-500">{fileName ? `${fileName}, ${dataRows.toLocaleString("en-ZA")} rows` : "or paste the rows below"}</span>
        </div>
        {large ? (
          <p className="rounded-md border border-line bg-ink-50 px-3 py-2 text-[13px] text-ink-600">The file is too large to show here. It will be loaded as it is.</p>
        ) : (
          <Field label="Rows">
            <Textarea rows={6} className="font-mono text-xs" placeholder={"discipline,code,price_column,description,units,value_rand\nPhysiotherapy,301,standard,Consultation 5 to 10 minutes,7.5,184.08"} value={csv} onChange={(e) => { setCsv(e.target.value); setFileName(""); setResult(null); }} />
          </Field>
        )}
        <fieldset>
          <legend className="mb-1.5 text-[13px] font-medium text-ink-700">Entries already in this draft{has ? ` (${has.toLocaleString("en-ZA")})` : ""}</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {([["append", "Keep them", "The file's rows are added after them."], ["replace", "Remove them first", "The draft will hold only what is in the file."]] as const).map(([key, label, help]) => (
              <label key={key} className={cx("flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-sm", mode === key ? "border-brand-600 bg-brand-50" : "border-line-strong bg-white")}>
                <input type="radio" name="import-mode" className="mt-1" checked={mode === key} onChange={() => { setMode(key); setResult(null); }} />
                <span><span className="font-medium text-ink-900">{label}</span><span className="block text-[13px] text-ink-500">{help}</span></span>
              </label>
            ))}
          </div>
        </fieldset>
        <p className="text-[13px] text-ink-500">Amounts are read with a point or a single comma as the decimal mark. An amount with both is refused, so write it without a thousands separator.</p>
        {error && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{error}</p>}
        {result && (
          <div className="rounded-md border border-line bg-ink-50 px-3 py-2.5 text-[13px] text-ink-700" role="status">
            <div className="font-medium text-ink-900">
              {result.added.toLocaleString("en-ZA")} loaded{result.removed ? `, ${result.removed.toLocaleString("en-ZA")} removed first` : ""}, {result.failed.toLocaleString("en-ZA")} could not be read
            </div>
            {result.duplicates > 0 && <div className="mt-1">{result.duplicates.toLocaleString("en-ZA")} row{result.duplicates === 1 ? " repeats" : "s repeat"} a code, discipline and column already in the list. They were loaded, because lists do print a code twice. Check them.</div>}
            {result.ignored_columns.length > 0 && <div className="mt-1">Columns not used: {result.ignored_columns.join(", ")}.</div>}
            {result.errors.length > 0 && (
              <ul className="mt-1.5 max-h-40 space-y-0.5 overflow-y-auto">
                {result.errors.map((e) => <li key={e}>{e}</li>)}
                {result.failed > result.errors.length && <li className="text-ink-500">and {(result.failed - result.errors.length).toLocaleString("en-ZA")} more.</li>}
              </ul>
            )}
          </div>
        )}
      </div>
    </Dialog>
  );
}
