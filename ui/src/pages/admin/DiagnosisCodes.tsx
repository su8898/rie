// Diagnosis codes: the ICD-10 codes a claim may carry. Add a code, correct its wording, change
// how it may be used, or load a new edition from a file. The list is large, so it is searched
// and paged on the server.

import { FileUp, Pencil, Plus, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { DataTable, Pager, type Column } from "../../ds/DataTable";
import { DIAGNOSIS_USE, diagnosisUse } from "../../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, Ref, Select, Stat, Textarea } from "../../ds/primitives";
import type { DiagnosisCode, DiagnosisImportResult, DiagnosisSummary } from "../../types";
import { RecentChanges, SectionHeader, errorText } from "./shared";

const PAGE_SIZE = 50;
const CODE_SHAPE = /^[A-Z][0-9]{2}[0-9A-Z./+*-]{0,6}$/;
const count = (n: number) => n.toLocaleString("en-ZA");

interface Draft { code: string; description: string; code3_desc: string; chapter_desc: string; use: string; existing: boolean }

export default function DiagnosisCodesAdmin() {
  const toast = useToast();
  const [summary, setSummary] = useState<DiagnosisSummary | null>(null);
  const [rows, setRows] = useState<DiagnosisCode[]>([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [use, setUse] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Draft | null>(null);
  const [removing, setRemoving] = useState<DiagnosisCode | null>(null);
  const [importing, setImporting] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.adminDiagnosisCodes({ q: q.trim(), use, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE });
      setRows(res.rows);
      setTotal(res.total);
    } catch (e) {
      setError(errorText(e, "The diagnosis codes could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [q, use, page]);
  useEffect(() => {
    const timer = setTimeout(() => { void load(); }, 200); // wait for typing to pause
    return () => clearTimeout(timer);
  }, [load, version]);
  useEffect(() => { api.adminDiagnosisSummary().then(setSummary).catch(() => setSummary(null)); }, [version]);

  const open = (c?: DiagnosisCode) => {
    setAttempted(false);
    setFormError(null);
    setEditing(c ? { code: c.code, description: c.description, code3_desc: c.code3_desc, chapter_desc: c.chapter_desc, use: diagnosisUse(c), existing: true }
      : { code: "", description: "", code3_desc: "", chapter_desc: "", use: "primary", existing: false });
  };
  const changed = (message: string) => { toast.success(message); setEditing(null); setRemoving(null); setVersion((v) => v + 1); };

  const code = editing?.code.trim().toUpperCase() ?? "";
  const codeError = !code ? "Enter the diagnosis code." : !CODE_SHAPE.test(code) ? "A letter, two digits and an optional subdivision, for example S72.00." : null;
  const descriptionError = !editing?.description.trim() ? "Enter the description." : null;

  async function save() {
    setAttempted(true);
    if (!editing || codeError || descriptionError) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.saveDiagnosisCode({
        code, description: editing.description.trim(), code3_desc: editing.code3_desc.trim(), chapter_desc: editing.chapter_desc.trim(),
        valid_primary: editing.use === "primary", valid_clinical: editing.use !== "heading",
      });
      changed(editing.existing ? `Diagnosis code ${code} saved.` : `Diagnosis code ${code} added.`);
    } catch (e) {
      setFormError(errorText(e, "The code could not be saved."));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api.removeDiagnosisCode(removing.code);
      changed(`Diagnosis code ${removing.code} removed.`);
    } catch (e) {
      toast.error(errorText(e, "The code could not be removed."));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<DiagnosisCode>[] = [
    { key: "code", header: "Code", render: (r) => <Ref className="font-medium text-ink-900">{r.code}</Ref> },
    { key: "description", header: "Description", render: (r) => (
      <div className="max-w-[64ch]">
        <div className="text-ink-800">{r.description}</div>
        {r.chapter_desc && <div className="truncate text-xs text-ink-500" title={r.chapter_desc}>{r.chapter_desc}</div>}
      </div>
    ) },
    { key: "use", header: "Use on a claim", render: (r) => { const u = DIAGNOSIS_USE[diagnosisUse(r)]; return <span title={u.help}><Badge tone={u.tone}>{u.label}</Badge></span>; } },
    { key: "actions", header: "", align: "right", render: (r) => (
      <div className="flex justify-end gap-1">
        <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Edit ${r.code}`} onClick={() => open(r)} />
        <Button size="sm" variant="ghost" icon={Trash2} aria-label={`Remove ${r.code}`} onClick={() => setRemoving(r)} />
      </div>
    ) },
  ];

  return (
    <div>
      <SectionHeader
        title="Diagnosis codes"
        description="The ICD-10 codes a claim may carry. Add a code, correct its wording, change how it may be used, or load a new edition from a file. A change here alters no claim already decided."
        actions={<><Button icon={FileUp} onClick={() => setImporting(true)}>Load from a file</Button><Button variant="primary" icon={Plus} onClick={() => open()}>Add code</Button></>}
      />

      <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Codes held" value={summary ? count(summary.total) : "…"} hint={!summary ? undefined : summary.edition && !/[|=]/.test(summary.edition) ? `Edition: ${summary.edition}` : summary.edition ? "Installed with the reference data" : "No edition recorded"} />
        <Stat label="Primary diagnosis" value={summary ? count(summary.valid_primary) : "…"} hint="May be the main diagnosis" />
        <Stat label="May be coded" value={summary ? count(summary.valid_clinical) : "…"} hint="Primary or secondary" />
        <Stat label="Not coded" value={summary ? count(summary.headings) : "…"} hint="Headings and withdrawn codes" />
      </div>

      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-3">
        <Input className="sm:col-span-2" placeholder="Start of a code, or words in the description" aria-label="Search diagnosis codes" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <Select aria-label="Use on a claim" value={use} onChange={(e) => { setUse(e.target.value); setPage(1); }}>
          <option value="">Any use</option>
          <option value="primary">May be a primary diagnosis</option>
          <option value="clinical">May be coded</option>
          <option value="heading">Not coded</option>
        </Select>
      </div>

      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={columns} rows={rows} rowKey={(r) => r.code} loading={loading}
          empty={<EmptyState title={q || use ? "No code matches" : "No diagnosis codes are loaded"} body={q || use ? "Change the search or the filter." : "Add codes one by one, or load an edition from a file."} />}
          footer={<Pager page={page} pageSize={PAGE_SIZE} total={total} unit="codes" onPage={setPage} />}
        />
      )}
      <RecentChanges area="icd10" version={version} />

      <Dialog
        open={editing !== null} onClose={() => setEditing(null)} wide
        title={editing?.existing ? `Edit diagnosis code ${editing.code}` : "Add a diagnosis code"}
        description="Used when a claim is captured and when a code is looked up. Claims already decided do not change."
        footer={<><Button onClick={() => setEditing(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>{editing?.existing ? "Save changes" : "Add code"}</Button></>}
      >
        {editing && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Code" required error={attempted ? codeError : null} hint={editing.existing ? "The code cannot be changed. Remove it and add the right one." : "For example S72.00."}>
              <Input className="font-mono uppercase" value={editing.code} disabled={editing.existing} invalid={attempted && Boolean(codeError)} onChange={(e) => setEditing({ ...editing, code: e.target.value })} />
            </Field>
            <Field label="Use on a claim" hint={DIAGNOSIS_USE[editing.use].help}>
              <Select value={editing.use} onChange={(e) => setEditing({ ...editing, use: e.target.value })}>
                <option value="primary">May be a primary diagnosis</option>
                <option value="secondary">Secondary diagnosis only</option>
                <option value="heading">May not be coded</option>
              </Select>
            </Field>
            <Field label="Description" required error={attempted ? descriptionError : null} className="sm:col-span-2">
              <Textarea rows={2} maxLength={500} value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
            </Field>
            <Field label="Category" hint="The three-character heading it falls under.">
              <Input value={editing.code3_desc} maxLength={500} onChange={(e) => setEditing({ ...editing, code3_desc: e.target.value })} />
            </Field>
            <Field label="Chapter">
              <Input value={editing.chapter_desc} maxLength={500} onChange={(e) => setEditing({ ...editing, chapter_desc: e.target.value })} />
            </Field>
          </div>
        )}
        {formError && <p className="mt-3 rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
      </Dialog>

      <ConfirmDialog
        open={removing !== null} onClose={() => setRemoving(null)} busy={busy} danger onConfirm={remove}
        title={`Remove diagnosis code ${removing?.code ?? ""}?`} confirmLabel="Remove code"
        description="The code can no longer be looked up. Claims that already carry it keep it. To stop a code being used while keeping it on record, edit it and choose May not be coded."
      />
      <ImportDialog open={importing} onClose={() => setImporting(false)} onLoaded={() => setVersion((v) => v + 1)} />
    </div>
  );
}

/** Load an edition of diagnosis codes from a CSV file. */
function ImportDialog({ open, onClose, onLoaded }: { open: boolean; onClose: () => void; onLoaded: () => void }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [csv, setCsv] = useState("");
  const [fileName, setFileName] = useState("");
  const [edition, setEdition] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DiagnosisImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (open) { setCsv(""); setFileName(""); setEdition(""); setResult(null); setError(null); } }, [open]);

  const dataRows = csv.trim() ? Math.max(0, csv.trim().split(/\r?\n/).length - 1) : 0;
  const large = csv.length > 200_000;

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.importDiagnosisCodes(csv, edition.trim());
      setResult(res);
      if (res.added || res.updated) { onLoaded(); toast.success(`${count(res.added)} added, ${count(res.updated)} updated.`); }
    } catch (e) {
      setError(errorText(e, "The file could not be loaded."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open} onClose={onClose} wide title="Load diagnosis codes from a file"
      description="A CSV file with a header row. It needs code and description columns, and may have code3_desc, chapter_desc, valid_primary and valid_clinical (yes or no). A code already held is updated where the file differs. A code that is not in the file is left as it is."
      footer={<><Button onClick={onClose}>{result ? "Close" : "Cancel"}</Button><Button variant="primary" loading={busy} disabled={!csv.trim() || Boolean(result)} onClick={run}>Load{dataRows ? ` ${count(dataRows)} row${dataRows === 1 ? "" : "s"}` : ""}</Button></>}
    >
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) { setCsv(await f.text()); setFileName(f.name); setResult(null); setError(null); } }} />
          <Button icon={Upload} onClick={() => fileRef.current?.click()}>Choose a file</Button>
          <span className="text-[13px] text-ink-500">{fileName ? `${fileName}, ${count(dataRows)} rows` : "or paste the rows below"}</span>
        </div>
        {large ? <p className="rounded-md border border-line bg-ink-50 px-3 py-2 text-[13px] text-ink-600">The file is too large to show here. It will be loaded as it is.</p> : (
          <Field label="Rows">
            <Textarea rows={6} className="font-mono text-xs" placeholder={"code,description,valid_primary,valid_clinical\nS72.00,\"Fracture of neck of femur, closed\",yes,yes"} value={csv} onChange={(e) => { setCsv(e.target.value); setFileName(""); setResult(null); }} />
          </Field>
        )}
        <Field label="Edition" hint="What this file is, for example ICD-10 Master Industry Table 2026. Shown with the reference editions. Leave empty to keep the edition recorded now.">
          <Input value={edition} maxLength={120} onChange={(e) => setEdition(e.target.value)} />
        </Field>
        {error && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{error}</p>}
        {result && (
          <div className="rounded-md border border-line bg-ink-50 px-3 py-2.5 text-[13px] text-ink-700" role="status">
            <div className="font-medium text-ink-900">{count(result.added)} added, {count(result.updated)} updated, {count(result.unchanged)} already the same, {count(result.failed)} could not be read</div>
            {result.errors.length > 0 && (
              <ul className="mt-1.5 max-h-40 space-y-0.5 overflow-y-auto">
                {result.errors.map((e) => <li key={e}>{e}</li>)}
                {result.failed > result.errors.length && <li className="text-ink-500">and {count(result.failed - result.errors.length)} more.</li>}
              </ul>
            )}
          </div>
        )}
      </div>
    </Dialog>
  );
}
