// Practices. The practice register: who each billing practice is, its discipline and setting,
// and whether it may bill the Fund. One more view lists practice numbers that are billing the
// Fund without a register entry, so they can be checked and added.

import { Download, Info, Plus, Upload, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, Pager, type Column, type Sort } from "../ds/DataTable";
import { PRACTICE_SETTINGS, PRACTICE_STATUS, PRACTICE_TYPES, shortDate } from "../ds/labels";
import { Dialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, PageHeader, Ref, Select, Stat, Textarea, cx } from "../ds/primitives";
import { rand } from "../format";
import type { Practice, PracticeSummary, UnregisteredPractice } from "../types";
import { PracticeFormDialog, blankPractice, type PracticeDraft } from "./practices/PracticeForm";

const FILTER_KEYS = ["q", "discipline", "setting", "practice_type", "verified"];
const VIEWS = [
  { key: "", label: "All" },
  { key: "ACTIVE", label: "Active" },
  { key: "SUSPENDED", label: "Suspended" },
  { key: "DEREGISTERED", label: "Deregistered" },
  { key: "unregistered", label: "Not in the register" },
];

function toCsv(rows: Practice[]): string {
  const cell = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const head = ["provider_id", "practice_name", "discipline", "practice_type", "setting", "professional_nr", "status", "status_reason", "verified", "notes"];
  return [head.join(","), ...rows.map((r) => head.map((k) => cell(r[k as keyof Practice])).join(","))].join("\n");
}

export default function PracticesPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const [params, setParams] = useSearchParams();
  const [summary, setSummary] = useState<PracticeSummary | null>(null);
  const [disciplines, setDisciplines] = useState<string[]>([]);
  const [rows, setRows] = useState<Practice[]>([]);
  const [unknown, setUnknown] = useState<UnregisteredPractice[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<PracticeDraft | null>(null);
  const [importing, setImporting] = useState(false);
  const [version, setVersion] = useState(0);

  const view = params.get("view") ?? "";
  const unregistered = view === "unregistered";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("size"))) ? Number(params.get("size")) : 25;
  const sort: Sort = { key: params.get("sort") ?? "number", direction: params.get("dir") === "desc" ? "desc" : "asc" };
  const value = (k: string) => params.get(k) ?? "";
  const filtered = FILTER_KEYS.some((k) => value(k));
  const query = params.toString();

  const set = (changes: Record<string, string | null>, keepPage = false) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v); else next.delete(k);
    }
    if (!keepPage) next.delete("page");
    setParams(next, { replace: true });
  };

  useEffect(() => {
    api.practiceSummary().then(setSummary).catch(() => setSummary(null));
    api.practiceDisciplines().then(setDisciplines).catch(() => setDisciplines([]));
  }, [version]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (unregistered) {
        const res = await api.practicesUnregistered({ q: value("q"), page, page_size: pageSize });
        setUnknown(res.items);
        setTotal(res.total);
      } else {
        const res = await api.practices({
          q: value("q"), status: view, discipline: value("discipline"), setting: value("setting"),
          practice_type: value("practice_type"), verified: value("verified"),
          sort: sort.key, direction: sort.direction, page, page_size: pageSize,
        });
        setRows(res.items);
        setTotal(res.total);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The practices could not be loaded.");
    } finally {
      setLoading(false);
    }
    // `query` is the whole view, filter, sort and page state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);
  useEffect(() => { void load(); }, [load, version]);

  async function exportCsv() {
    try {
      const res = await api.practices({ q: value("q"), status: view, discipline: value("discipline"), setting: value("setting"), practice_type: value("practice_type"), verified: value("verified"), sort: sort.key, direction: sort.direction, page: 1, page_size: 200 });
      const url = URL.createObjectURL(new Blob([toCsv(res.items)], { type: "text/csv" }));
      Object.assign(document.createElement("a"), { href: url, download: "practices.csv" }).click();
      URL.revokeObjectURL(url);
      toast.success(res.total > res.items.length ? `Exported the first ${res.items.length} of ${res.total} practices.` : `Exported ${res.items.length} practices.`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "The export failed.");
    }
  }

  const count = (key: string) => !summary ? undefined : key === "" ? summary.total : key === "unregistered" ? summary.unregistered : summary.by_status[key] ?? 0;
  const barred = summary ? (summary.by_status.SUSPENDED ?? 0) + (summary.by_status.DEREGISTERED ?? 0) : 0;
  const open = (id: string) => navigate(`/practices/${encodeURIComponent(id)}`);

  const columns: Column<Practice>[] = [
    { key: "name", header: "Practice", sortable: true, render: (r) => (
      <div><div className="font-medium text-ink-900">{r.practice_name || "No name recorded"}</div><Ref className="text-xs text-ink-500">{r.provider_id}</Ref></div>
    ) },
    { key: "discipline", header: "Discipline", sortable: true, render: (r) => r.discipline || <span className="text-ink-400">—</span> },
    { key: "setting", header: "Setting", render: (r) => PRACTICE_SETTINGS[r.setting] ?? <span className="text-ink-400">—</span> },
    { key: "type", header: "Type", render: (r) => PRACTICE_TYPES[r.practice_type] ?? <span className="text-ink-400">—</span> },
    { key: "status", header: "Status", render: (r) => (
      <div>
        <Badge tone={PRACTICE_STATUS[r.status].tone} dot>{PRACTICE_STATUS[r.status].label}</Badge>
        {r.status !== "ACTIVE" && r.status_reason && <div className="mt-1 max-w-[26ch] truncate text-xs text-ink-500" title={r.status_reason}>{r.status_reason}</div>}
      </div>
    ) },
    { key: "verified", header: "Verified", render: (r) => r.verified ? <span className="text-ink-700">Yes</span> : <Badge tone="warn">Not verified</Badge> },
    { key: "updated", header: "Updated", sortable: true, render: (r) => <div><div className="text-ink-700">{shortDate(r.updated_at)}</div><div className="text-xs text-ink-500">{r.updated_by ? `by ${r.updated_by}` : ""}</div></div> },
  ];
  const unknownColumns: Column<UnregisteredPractice>[] = [
    { key: "number", header: "Practice number", render: (r) => <Ref className="font-medium text-brand-700">{r.provider_id}</Ref> },
    { key: "claims", header: "Claims", align: "right", render: (r) => <span className="tnum">{r.n_claims}</span> },
    { key: "billed", header: "Billed", align: "right", render: (r) => <span className="tnum font-medium text-ink-900">{rand(r.billed)}</span> },
    { key: "last", header: "Last service", render: (r) => <span className="text-ink-700">{shortDate(r.last_service)}</span> },
    ...(isAdmin ? [{ key: "add", header: "", align: "right" as const, render: (r: UnregisteredPractice) => (
      <Button size="sm" icon={Plus} onClick={(e) => { e.stopPropagation(); setForm(blankPractice(r.provider_id)); }}>Add to register</Button>
    ) }] : []),
  ];
  const pager = <Pager page={page} pageSize={pageSize} total={total} unit="practices" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />;

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Providers" }, { label: "Practices" }]}
        title="Practices"
        subtitle="The practice register: who each billing practice is, and whether it may bill the Fund."
        actions={
          <>
            {!unregistered && <Button icon={Download} onClick={exportCsv}>Export</Button>}
            {isAdmin && <Button icon={Upload} onClick={() => setImporting(true)}>Import</Button>}
            {isAdmin && <Button variant="primary" icon={Plus} onClick={() => setForm(blankPractice())}>Add practice</Button>}
          </>
        }
      />

      {summary && (
        <div className={cx("mb-4 flex items-start gap-2 rounded-lg border px-4 py-3 text-sm", summary.enforced ? "border-ok-line bg-ok-bg text-ok-fg" : "border-info-line bg-info-bg text-info-fg")}>
          <Info size={16} className="mt-0.5 shrink-0" aria-hidden />
          <span>{summary.enforced
            ? "Enforcement is on. A practice that is not in the register cannot bill the Fund."
            : "Enforcement is off. A practice that is not in the register is accepted as submitted. Suspended and deregistered practices are always refused."}</span>
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="In the register" value={summary ? summary.total : "…"} />
        <Stat label="Active" value={summary ? summary.by_status.ACTIVE ?? 0 : "…"} hint="May bill the Fund" tone="ok" />
        <Stat label="Suspended or deregistered" value={summary ? barred : "…"} hint="Cannot bill the Fund" tone={barred ? "bad" : undefined} />
        <Stat label="Not in the register" value={summary ? summary.unregistered : "…"} hint="Billing without an entry" tone={summary?.unregistered ? "warn" : undefined} />
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Views">
        {VIEWS.map((v) => (
          <button
            key={v.key || "all"} role="tab" aria-selected={view === v.key}
            onClick={() => setParams(v.key ? { view: v.key } : {}, { replace: true })}
            className={cx("rounded-full border px-3 py-1.5 text-[13px] font-medium transition", view === v.key ? "border-ink-900 bg-ink-900 text-white" : "border-line-strong bg-white text-ink-600 hover:border-ink-400 hover:text-ink-900")}
          >
            {v.label}{count(v.key) != null && <span className="tnum ml-1.5 opacity-70">{count(v.key)}</span>}
          </button>
        ))}
      </div>

      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-2 lg:grid-cols-6">
        <Input className="lg:col-span-2" placeholder={unregistered ? "Practice number" : "Practice number, name, discipline or council number"} aria-label="Search practices" value={value("q")} onChange={(e) => set({ q: e.target.value })} />
        {!unregistered && (
          <>
            <Select aria-label="Discipline" value={value("discipline")} onChange={(e) => set({ discipline: e.target.value })}>
              <option value="">Any discipline</option>
              {disciplines.map((d) => <option key={d} value={d}>{d}</option>)}
            </Select>
            <Select aria-label="Setting" value={value("setting")} onChange={(e) => set({ setting: e.target.value })}>
              <option value="">Any setting</option>
              {Object.entries(PRACTICE_SETTINGS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </Select>
            <Select aria-label="Type" value={value("practice_type")} onChange={(e) => set({ practice_type: e.target.value })}>
              <option value="">Any type</option>
              {Object.entries(PRACTICE_TYPES).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </Select>
            <Select aria-label="Verified" value={value("verified")} onChange={(e) => set({ verified: e.target.value })}>
              <option value="">Verified or not</option>
              <option value="true">Verified</option>
              <option value="false">Not verified</option>
            </Select>
          </>
        )}
        {filtered && (
          <div className="flex items-center lg:col-span-6">
            <Button size="sm" variant="ghost" icon={X} onClick={() => set(Object.fromEntries(FILTER_KEYS.map((k) => [k, null])))}>Clear filters</Button>
          </div>
        )}
      </div>

      {error ? <ErrorBlock message={error} onRetry={load} /> : unregistered ? (
        <DataTable
          columns={unknownColumns} rows={unknown} rowKey={(r) => r.provider_id} loading={loading} onRowClick={(r) => open(r.provider_id)}
          empty={<EmptyState title="Every billing practice is in the register" body="A practice number appears here when it bills the Fund without a register entry." />}
          footer={pager}
        />
      ) : (
        <DataTable
          columns={columns} rows={rows} rowKey={(r) => r.provider_id} loading={loading} onRowClick={(r) => open(r.provider_id)}
          sort={sort} onSort={(s) => set({ sort: s.key === "number" ? null : s.key, dir: s.direction === "desc" ? "desc" : null }, true)}
          empty={<EmptyState title={filtered || view ? "No practice matches" : "The register is empty"} body={filtered || view ? "Change or clear the filters." : isAdmin ? "Add a practice, or import the register from a file." : "An administrator adds practices to the register."} />}
          footer={pager}
        />
      )}

      {form && (
        <PracticeFormDialog
          open mode="add" initial={form} onClose={() => setForm(null)}
          onSaved={(p) => { setForm(null); setVersion((v) => v + 1); open(p.provider_id); }}
        />
      )}
      <ImportDialog open={importing} onClose={() => setImporting(false)} onLoaded={() => setVersion((v) => v + 1)} />
    </div>
  );
}

/** Load the register from a CSV file. Good rows are loaded; bad rows are reported by line. */
function ImportDialog({ open, onClose, onLoaded }: { open: boolean; onClose: () => void; onLoaded: () => void }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [csv, setCsv] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ loaded: number; errors: { line: number; error: string }[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (open) { setCsv(""); setResult(null); setError(null); } }, [open]);

  const dataRows = csv.trim() ? Math.max(0, csv.trim().split(/\r?\n/).length - 1) : 0;
  async function readFile(file: File | undefined) {
    if (!file) return;
    setCsv(await file.text());
    setResult(null);
  }
  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.importPractices(csv);
      setResult(res);
      if (res.loaded) { toast.success(`${res.loaded} practice${res.loaded === 1 ? "" : "s"} loaded.`); onLoaded(); }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The import failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open} onClose={onClose} wide title="Import practices"
      description="A CSV file with a provider_id column and any of practice_name, discipline, practice_type, setting, professional_nr, notes. Existing practices are updated. An import never changes a practice's status."
      footer={<><Button onClick={onClose}>{result ? "Close" : "Cancel"}</Button><Button variant="primary" loading={busy} disabled={!csv.trim()} onClick={run}>Import{dataRows ? ` ${dataRows} row${dataRows === 1 ? "" : "s"}` : ""}</Button></>}
    >
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => readFile(e.target.files?.[0])} />
          <Button icon={Upload} onClick={() => fileRef.current?.click()}>Choose a file</Button>
          <span className="text-[13px] text-ink-500">or paste the rows below</span>
        </div>
        <Field label="Rows">
          <Textarea rows={7} className="font-mono text-xs" placeholder={"provider_id,practice_name,discipline,setting\n0123456,Dr A Example,GP,ROOMS"} value={csv} onChange={(e) => { setCsv(e.target.value); setResult(null); }} />
        </Field>
        {error && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{error}</p>}
        {result && (
          <div className="rounded-md border border-line bg-ink-50 px-3 py-2.5 text-[13px] text-ink-700">
            <div className="font-medium text-ink-900">{result.loaded} loaded, {result.errors.length} skipped</div>
            {result.errors.length > 0 && (
              <ul className="mt-1.5 max-h-40 space-y-0.5 overflow-y-auto">
                {result.errors.map((e) => <li key={e.line}><span className="tnum text-ink-500">Line {e.line}:</span> {e.error}</li>)}
              </ul>
            )}
          </div>
        )}
      </div>
    </Dialog>
  );
}
