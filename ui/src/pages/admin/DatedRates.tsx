// Dated rates. Reference tariff, negotiated and medicine prices kept as dated versions. A line is
// priced at the rate in force on its service date, so a new rate never changes an old claim.
// Rates are never deleted: a rate is replaced from a date, corrected, or ended.

import { Download, Percent, Plus, Upload, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../../api";
import { DataTable, Pager, type Column } from "../../ds/DataTable";
import { dateTime, shortDate } from "../../ds/labels";
import { Dialog, useToast } from "../../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, LoadingBlock, Ref, Select, Stat, Tabs, Textarea, cx } from "../../ds/primitives";
import { rand } from "../../format";
import type { RateImportResult, RateLogRow, RateRow, RateSource, RateSummary, RateVersion } from "../../types";
import { SectionHeader, errorText } from "./shared";

const SOURCES: Record<RateSource, { label: string; help: string; kinds: string[] }> = {
  RPL: { label: "Reference tariff", help: "The gazetted tariff, per code and discipline.", kinds: ["TARIFF"] },
  NEGOTIATED: { label: "Negotiated", help: "Prices the Fund has agreed for a code.", kinds: ["TARIFF", "NAPPI"] },
  SEP: { label: "Medicine exit price", help: "The single exit price of a medicine or material.", kinds: ["NAPPI"] },
};
const KINDS: Record<string, string> = { TARIFF: "Tariff code", NAPPI: "Medicine or material" };
const LOG_ACTIONS: Record<string, string> = { CREATE: "First dated rate", SUPERSEDE: "New rate from a date", ADJUST: "Amount corrected", RETIRE: "Rate ended" };
const ORIGINS: Record<string, string> = { manual: "Captured", import: "Imported", increase: "Percentage increase", undated: "Loaded without a date", baseline: "Loaded without a date" };
const today = () => new Date().toISOString().slice(0, 10);
const money = (v: number | null | undefined) => (v == null ? "—" : rand(v));
const alertBox = (m: string | null) => m && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{m}</p>;
type Key = Pick<RateRow, "source" | "kind" | "code" | "discipline">;

/** The server's refusals on a rate change, in plain words. */
function refusal(e: unknown, fallback: string): string {
  const m = errorText(e, fallback);
  const starts = m.match(/already (?:starts|has a rate starting) (\d{4}-\d{2}-\d{2})/);
  if (starts) return `This code already has a rate starting ${shortDate(starts[1])}. Use a later date.`;
  if (m.includes("same as the current value")) return "The amount is the same as it is now.";
  if (m.includes("overlap the next version")) return "That end date runs into the next version. Choose an earlier date.";
  if (m.includes("before the version's effective-from")) return "The end date cannot be before the date this rate started.";
  if (m.includes("no rates match")) return "No rate matches that filter.";
  if (m.startsWith("nothing increased")) return "Nothing was increased: every matching code already has a rate on or after that date.";
  return m;
}

export default function DatedRatesAdmin() {
  const [params, setParams] = useSearchParams();
  const [summary, setSummary] = useState<RateSummary | null>(null);
  const [disciplines, setDisciplines] = useState<string[]>([]);
  const [rows, setRows] = useState<RateRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [openKey, setOpenKey] = useState<Key | null>(null);
  const [dialog, setDialog] = useState<"add" | "bulk" | "import" | null>(null);

  const tab = params.get("tab") === "log" ? "log" : "rates";
  const source = (["RPL", "NEGOTIATED", "SEP"].includes(params.get("source") ?? "") ? params.get("source") : "RPL") as RateSource;
  const q = params.get("q") ?? "";
  const discipline = params.get("discipline") ?? "";
  const on = params.get("on") ?? "";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const pageSize = [25, 50, 100].includes(Number(params.get("size"))) ? Number(params.get("size")) : 25;
  const query = params.toString();
  const set = (changes: Record<string, string | null>, keepPage = false) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v) next.set(k, v); else next.delete(k);
    }
    if (!keepPage) next.delete("page");
    setParams(next, { replace: true });
  };
  const changed = () => setVersion((v) => v + 1);

  useEffect(() => { api.disciplines().then(setDisciplines).catch(() => setDisciplines([])); }, []);
  useEffect(() => { api.rateSummary().then(setSummary).catch(() => setSummary(null)); }, [version]);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.rates({ source, q, discipline: source === "RPL" ? discipline : "", on: on || undefined, limit: pageSize, offset: (page - 1) * pageSize });
      setRows(res.items);
      setTotal(res.total);
    } catch (e) {
      setError(errorText(e, "The rates could not be loaded."));
    } finally {
      setLoading(false);
    }
    // `query` is the whole source, filter and page state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);
  useEffect(() => { if (tab === "rates") void load(); }, [load, version, tab]);

  const columns: Column<RateRow>[] = [
    { key: "code", header: "Code", render: (r) => <div><Ref className="font-medium text-brand-700">{r.code}</Ref><div className="text-xs text-ink-500">{KINDS[r.kind] ?? r.kind}</div></div> },
    ...(source === "RPL" ? [{ key: "discipline", header: "Discipline", render: (r: RateRow) => <span className="text-ink-700">{r.discipline || "—"}</span> }] : []),
    { key: "rate", header: on ? `Rate on ${shortDate(on)}` : "Rate today", align: "right", render: (r) => r.rate == null ? <Badge tone="warn">No rate in force</Badge> : <span className="tnum font-medium text-ink-900">{rand(r.rate)}</span> },
    { key: "force", header: "In force", render: (r) => !r.dated ? <span className="text-[13px] text-ink-500">No start date recorded</span> : r.effective_from ? (
      <span className="text-ink-700">From {shortDate(r.effective_from)}{r.effective_to ? ` to ${shortDate(r.effective_to)}` : ""}</span>
    ) : <span className="text-ink-400">—</span> },
    { key: "versions", header: "Versions", align: "right", render: (r) => <span className="tnum text-ink-700">{r.versions || "—"}</span> },
  ];

  return (
    <div>
      <SectionHeader
        title="Dated rates" description="Reference tariff, negotiated and medicine prices with a start date. A line is priced at the rate in force on its service date, so a new rate never changes an old claim. A rate is never deleted: it is replaced from a date, corrected, or ended."
        actions={
          <>
            <a href={api.rateExportUrl(source, on || undefined)} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-line-strong bg-white px-3 text-sm font-medium text-ink-800 transition hover:bg-ink-50"><Download size={15} aria-hidden /> Export</a>
            <Button icon={Upload} onClick={() => setDialog("import")}>Import</Button>
            <Button icon={Percent} onClick={() => setDialog("bulk")}>Increase</Button>
            <Button variant="primary" icon={Plus} onClick={() => setDialog("add")}>Add rate</Button>
          </>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Stat label="Dated versions" value={summary ? summary.versions.toLocaleString("en-ZA") : "…"} />
        <Stat label="Codes with a dated rate" value={summary ? summary.dated_keys.toLocaleString("en-ZA") : "…"} />
        <Stat label="Changes logged" value={summary ? summary.changes.toLocaleString("en-ZA") : "…"} />
        <Stat label="Last change" value={summary?.last_change ? shortDate(summary.last_change) : "None"} />
      </div>

      <Tabs tabs={[{ key: "rates", label: "Rates" }, { key: "log", label: "Change log", count: summary?.changes }]} value={tab} onChange={(k) => set({ tab: k === "log" ? "log" : null })} />

      {tab === "log" ? <div className="mt-4"><ChangeLog version={version} /></div> : (
        <div className="mt-4">
          <div className="mb-3 flex flex-wrap gap-1.5" role="tablist" aria-label="Price list">
            {(Object.keys(SOURCES) as RateSource[]).map((k) => (
              <button
                key={k} role="tab" aria-selected={source === k} title={SOURCES[k].help} onClick={() => setParams(k === "RPL" ? {} : { source: k }, { replace: true })}
                className={cx("rounded-full border px-3 py-1.5 text-[13px] font-medium transition", source === k ? "border-ink-900 bg-ink-900 text-white" : "border-line-strong bg-white text-ink-600 hover:border-ink-400 hover:text-ink-900")}
              >
                {SOURCES[k].label}
              </button>
            ))}
          </div>
          <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-2 xl:grid-cols-4">
            <Input placeholder="Code starts with" aria-label="Code" className="font-mono" value={q} onChange={(e) => set({ q: e.target.value })} />
            {source === "RPL" ? (
              <Select aria-label="Discipline" value={discipline} onChange={(e) => set({ discipline: e.target.value })}>
                <option value="">Any discipline</option>
                {disciplines.map((d) => <option key={d} value={d}>{d}</option>)}
              </Select>
            ) : <div className="hidden xl:block" />}
            <label className="flex items-center gap-2 text-[13px] text-ink-500 sm:col-span-2 xl:col-span-1">
              <span className="shrink-0">Rates as at</span>
              <Input type="date" value={on} onChange={(e) => set({ on: e.target.value })} />
            </label>
            {(q || discipline || on) && <div className="flex items-center"><Button size="sm" variant="ghost" icon={X} onClick={() => set({ q: null, discipline: null, on: null })}>Clear filters</Button></div>}
          </div>
          {error ? <ErrorBlock message={error} onRetry={load} /> : (
            <DataTable
              columns={columns} rows={rows} rowKey={(r) => `${r.kind}:${r.code}:${r.discipline}`} loading={loading} onRowClick={(r) => setOpenKey(r)}
              empty={<EmptyState title={q || discipline ? "No rate matches" : "No rates in this list"} body={q || discipline ? "Change or clear the filters." : "Add a rate, or import the price list from a file."} />}
              footer={<Pager page={page} pageSize={pageSize} total={total} unit="rates" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
            />
          )}
        </div>
      )}

      {openKey && <RateHistory rateKey={openKey} onClose={() => setOpenKey(null)} onChanged={changed} />}
      <AddRate open={dialog === "add"} source={source} disciplines={disciplines} onClose={() => setDialog(null)} onSaved={(k) => { setDialog(null); changed(); setOpenKey(k); }} />
      <BulkIncrease open={dialog === "bulk"} source={source === "SEP" ? "RPL" : source} q={q} discipline={discipline} disciplines={disciplines} onClose={() => setDialog(null)} onDone={changed} />
      <ImportRates open={dialog === "import"} source={source} onClose={() => setDialog(null)} onDone={changed} />
    </div>
  );
}

// ── One code's versions, and what can be done to them ────────────────────────
type Act = { kind: "new" | "increase" } | { kind: "correct" | "end"; version: RateVersion } | null;

function RateHistory({ rateKey, onClose, onChanged }: { rateKey: Key; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const [versions, setVersions] = useState<RateVersion[] | null>(null);
  const [act, setAct] = useState<Act>(null);
  const [form, setForm] = useState({ rate: "", pct: "", date: "", note: "" });
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.rateVersions(rateKey).then(setVersions).catch((e) => { setVersions([]); setError(errorText(e, "The versions could not be loaded.")); });
  }, [rateKey]);
  useEffect(() => { load(); }, [load]);

  const start = (a: Act) => {
    setForm({ rate: a && "version" in a ? String(a.version.rate) : "", pct: "", date: a?.kind === "end" ? today() : "", note: "" });
    setAttempted(false);
    setError(null);
    setAct(a);
  };
  const rateError = !(Number(form.rate) >= 0) || form.rate === "" ? "Enter the rate in rand." : null;
  const pctError = form.pct === "" || !(Number(form.pct) > -100 && Number(form.pct) <= 1000) ? "Enter a percentage, for example 5.2." : null;
  const dateError = !form.date ? "Enter the date." : null;
  const noteError = !form.note.trim() ? "Say why." : null;
  const invalid = !act ? true : act.kind === "new" ? rateError || dateError : act.kind === "increase" ? pctError || dateError : act.kind === "correct" ? rateError || noteError : dateError || noteError;

  async function save() {
    setAttempted(true);
    if (!act || invalid) return;
    setBusy(true);
    setError(null);
    try {
      if (act.kind === "new") await api.addRate({ ...rateKey, rate: Number(form.rate), effective_from: form.date, note: form.note.trim() });
      else if (act.kind === "increase") await api.increaseRate({ ...rateKey, pct: Number(form.pct), effective_from: form.date });
      else if (act.kind === "correct") await api.adjustRate(act.version.id!, Number(form.rate), form.note.trim());
      else if (act.kind === "end") await api.retireRate(act.version.id!, form.date, form.note.trim());
      toast.success({ new: "New rate saved.", increase: "Rate increased.", correct: "Amount corrected.", end: "Rate ended." }[act.kind]);
      setAct(null);
      load();
      onChanged();
    } catch (e) {
      setError(refusal(e, "The change could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  const title = `${rateKey.code}${rateKey.discipline ? `, ${rateKey.discipline}` : ""}`;
  const ACT_TITLE = { new: "Set a new rate from a date", increase: "Increase by a percentage from a date", correct: "Correct the amount of this version", end: "End this rate" };
  return (
    <Dialog
      open onClose={onClose} wide title={`Rate history: ${title}`}
      description={`${SOURCES[rateKey.source].label}, ${(KINDS[rateKey.kind] ?? rateKey.kind).toLowerCase()}. Newest first.`}
      footer={act ? <><Button onClick={() => setAct(null)}>Back</Button><Button variant="primary" loading={busy} onClick={save}>Save</Button></> : (
        <><Button onClick={onClose}>Close</Button><Button icon={Percent} onClick={() => start({ kind: "increase" })}>Increase</Button><Button variant="primary" icon={Plus} onClick={() => start({ kind: "new" })}>New rate</Button></>
      )}
    >
      {act ? (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-ink-900">{ACT_TITLE[act.kind]}</h3>
          {"version" in act && <p className="text-[13px] text-ink-600">Version from {shortDate(act.version.effective_from)}{act.version.effective_to ? ` to ${shortDate(act.version.effective_to)}` : ""}, {rand(act.version.rate)}.</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            {(act.kind === "new" || act.kind === "correct") && (
              <Field label={act.kind === "correct" ? "Correct amount (R)" : "New rate (R)"} required error={attempted ? rateError : null} hint={act.kind === "correct" ? "For a capture error only. The dates stay the same." : undefined}>
                <Input type="number" min={0} step="0.01" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} />
              </Field>
            )}
            {act.kind === "increase" && (
              <Field label="Increase (%)" required error={attempted ? pctError : null} hint="A negative number lowers the rate.">
                <Input type="number" step="0.01" value={form.pct} onChange={(e) => setForm({ ...form, pct: e.target.value })} />
              </Field>
            )}
            {act.kind !== "correct" && (
              <Field label={act.kind === "end" ? "Last day in force" : "Takes effect on"} required error={attempted ? dateError : null} hint={act.kind === "end" ? "From the next day the code has no rate until a later version starts." : "The current rate ends the day before. The date must be later than every existing version."}>
                <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
              </Field>
            )}
            {act.kind !== "increase" && (
              <Field label="Note" required={act.kind !== "new"} error={attempted && act.kind !== "new" ? noteError : null} className="sm:col-span-2">
                <Textarea rows={2} maxLength={500} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder={act.kind === "new" ? "For example the gazette reference" : "Why this change is being made"} />
              </Field>
            )}
          </div>
          {alertBox(error)}
        </div>
      ) : versions === null ? <LoadingBlock /> : versions.length === 0 ? (error ? alertBox(error) : <EmptyState title="No rate recorded" body="This code has no rate in this price list." />) : (
        <div className="-mx-5 -my-4 overflow-x-auto">
          <table className="min-w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-line bg-ink-50/70 text-left text-xs text-ink-500">
                <th className="px-5 py-2 font-medium">In force</th><th className="px-3 py-2 text-right font-medium">Rate</th><th className="px-3 py-2 font-medium">Source</th><th className="px-3 py-2 font-medium">Note</th><th className="px-5 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {versions.map((v, i) => (
                <tr key={v.id ?? `undated-${i}`} className="align-top">
                  <td className="px-5 py-2.5 text-ink-800">{v.effective_from ? <>From {shortDate(v.effective_from)}{v.effective_to ? <><br /><span className="text-ink-500">to {shortDate(v.effective_to)}</span></> : <> <Badge tone="ok">Open-ended</Badge></>}</> : "No start date recorded"}</td>
                  <td className="tnum px-3 py-2.5 text-right font-medium text-ink-900">{rand(v.rate)}</td>
                  <td className="px-3 py-2.5 text-[13px] text-ink-600">{ORIGINS[v.origin] ?? v.origin}{v.created_by ? <><br />by {v.created_by}</> : null}</td>
                  <td className="max-w-[24ch] px-3 py-2.5 text-[13px] text-ink-600">{v.note || "—"}</td>
                  <td className="whitespace-nowrap px-5 py-2.5 text-right">
                    {v.id != null && <><Button size="sm" variant="ghost" onClick={() => start({ kind: "correct", version: v })}>Correct</Button>{!v.effective_to && <Button size="sm" variant="ghost" onClick={() => start({ kind: "end", version: v })}>End</Button>}</>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Dialog>
  );
}

// ── Add one rate ─────────────────────────────────────────────────────────────
function AddRate({ open, source, disciplines, onClose, onSaved }: { open: boolean; source: RateSource; disciplines: string[]; onClose: () => void; onSaved: (k: Key) => void }) {
  const toast = useToast();
  const [form, setForm] = useState({ source, kind: SOURCES[source].kinds[0], code: "", discipline: "", rate: "", date: "", note: "" });
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (open) { setForm({ source, kind: SOURCES[source].kinds[0], code: "", discipline: "", rate: "", date: "", note: "" }); setAttempted(false); setError(null); } }, [open, source]);

  const src = SOURCES[form.source];
  const errors = {
    code: !form.code.trim() ? "Enter the code." : null,
    discipline: form.source === "RPL" && !form.discipline ? "Choose the discipline." : null,
    rate: form.rate === "" || !(Number(form.rate) >= 0) ? "Enter the rate in rand." : null,
    date: !form.date ? "Enter the date it takes effect." : null,
  };
  async function save() {
    setAttempted(true);
    if (Object.values(errors).some(Boolean)) return;
    setBusy(true);
    setError(null);
    try {
      const v = await api.addRate({ source: form.source, kind: form.kind, code: form.code.trim(), discipline: form.source === "RPL" ? form.discipline : "", rate: Number(form.rate), effective_from: form.date, note: form.note.trim() });
      toast.success(v.action === "SUPERSEDE" ? `New rate for ${v.code} saved. The earlier rate ends the day before.` : `Rate for ${v.code} saved.`);
      onSaved({ source: v.source, kind: v.kind, code: v.code, discipline: v.discipline });
    } catch (e) {
      setError(refusal(e, "The rate could not be saved."));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={open} onClose={onClose} wide title="Add a rate" description="If the code already has a rate, the new one replaces it from the date you give and the earlier rate ends the day before."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Save rate</Button></>}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Price list" required hint={src.help}>
          <Select value={form.source} onChange={(e) => { const s = e.target.value as RateSource; setForm({ ...form, source: s, kind: SOURCES[s].kinds[0] }); }}>
            {(Object.keys(SOURCES) as RateSource[]).map((k) => <option key={k} value={k}>{SOURCES[k].label}</option>)}
          </Select>
        </Field>
        <Field label="Kind" required>
          <Select value={form.kind} disabled={src.kinds.length === 1} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
            {src.kinds.map((k) => <option key={k} value={k}>{KINDS[k]}</option>)}
          </Select>
        </Field>
        <Field label="Code" required error={attempted ? errors.code : null}>
          <Input className="font-mono" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
        </Field>
        {form.source === "RPL" && (
          <Field label="Discipline" required error={attempted ? errors.discipline : null}>
            <Select value={form.discipline} onChange={(e) => setForm({ ...form, discipline: e.target.value })}>
              <option value="">Choose</option>
              {disciplines.map((d) => <option key={d} value={d}>{d}</option>)}
            </Select>
          </Field>
        )}
        <Field label="Rate (R)" required error={attempted ? errors.rate : null}>
          <Input type="number" min={0} step="0.01" value={form.rate} onChange={(e) => setForm({ ...form, rate: e.target.value })} />
        </Field>
        <Field label="Takes effect on" required error={attempted ? errors.date : null}>
          <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
        </Field>
        <Field label="Note" className="sm:col-span-2">
          <Textarea rows={2} maxLength={500} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="For example the gazette reference" />
        </Field>
        {error && <div className="sm:col-span-2">{alertBox(error)}</div>}
      </div>
    </Dialog>
  );
}

// ── Increase many rates at once ──────────────────────────────────────────────
function BulkIncrease({ open, source, q, discipline, disciplines, onClose, onDone }: { open: boolean; source: "RPL" | "NEGOTIATED"; q: string; discipline: string; disciplines: string[]; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({ source, pct: "", date: "", q, discipline });
  const [attempted, setAttempted] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ increased: number; skipped: number; skipped_detail: string[] } | null>(null);
  useEffect(() => { if (open) { setForm({ source, pct: "", date: "", q, discipline }); setAttempted(false); setConfirming(false); setError(null); setResult(null); } }, [open, source, q, discipline]);

  const pctError = form.pct === "" || !(Number(form.pct) > -100 && Number(form.pct) <= 1000) || Number(form.pct) === 0 ? "Enter a percentage, for example 5.2." : null;
  const dateError = !form.date ? "Enter the date the new rates take effect." : null;
  const scope = `${form.q ? `codes starting with ${form.q}` : "every code"}${form.source === "RPL" && form.discipline ? ` for ${form.discipline}` : ""} in the ${SOURCES[form.source].label.toLowerCase()} list`;
  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.bulkIncreaseRates({ source: form.source, pct: Number(form.pct), effective_from: form.date, q: form.q.trim(), discipline: form.source === "RPL" ? form.discipline : "" });
      setResult(res);
      toast.success(`${res.increased} rate${res.increased === 1 ? "" : "s"} increased.`);
      onDone();
    } catch (e) {
      setError(refusal(e, "The increase could not be applied."));
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={open} onClose={onClose} wide title="Increase rates by a percentage" description="Each matching rate gets a new version from the date you give. The current rates stay in force for earlier service dates."
      footer={result ? <Button onClick={onClose}>Close</Button> : confirming ? (
        <><Button onClick={() => setConfirming(false)}>Back</Button><Button variant="primary" loading={busy} onClick={run}>Apply the increase</Button></>
      ) : <><Button onClick={onClose}>Cancel</Button><Button variant="primary" onClick={() => { setAttempted(true); if (!pctError && !dateError) setConfirming(true); }}>Review</Button></>}
    >
      {result ? (
        <div className="rounded-md border border-line bg-ink-50 px-3 py-2.5 text-[13px] text-ink-700">
          <div className="font-medium text-ink-900">{result.increased} increased, {result.skipped} skipped</div>
          {result.skipped_detail.length > 0 && <ul className="mt-1.5 max-h-40 space-y-0.5 overflow-y-auto">{result.skipped_detail.map((m) => <li key={m}>{m}</li>)}</ul>}
        </div>
      ) : confirming ? (
        <div className="space-y-3 text-sm text-ink-800">
          <p>You are about to change <span className="font-medium">{scope}</span> by <span className="tnum font-medium">{Number(form.pct)}%</span> from <span className="font-medium">{shortDate(form.date)}</span>.</p>
          <p className="text-[13px] text-ink-600">A code that already has a version on or after that date is skipped and listed. This cannot be undone in one step: each new rate would have to be corrected or ended.</p>
          {alertBox(error)}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Price list" required hint="Medicine exit prices cannot be increased in bulk.">
            <Select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value as "RPL" | "NEGOTIATED" })}>
              <option value="RPL">{SOURCES.RPL.label}</option><option value="NEGOTIATED">{SOURCES.NEGOTIATED.label}</option>
            </Select>
          </Field>
          <Field label="Increase (%)" required error={attempted ? pctError : null} hint="A negative number lowers the rates.">
            <Input type="number" step="0.01" value={form.pct} onChange={(e) => setForm({ ...form, pct: e.target.value })} />
          </Field>
          <Field label="Takes effect on" required error={attempted ? dateError : null}>
            <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </Field>
          <Field label="Only codes starting with" hint="Leave blank for every code.">
            <Input className="font-mono" value={form.q} onChange={(e) => setForm({ ...form, q: e.target.value })} />
          </Field>
          {form.source === "RPL" && (
            <Field label="Only this discipline" className="sm:col-span-2">
              <Select value={form.discipline} onChange={(e) => setForm({ ...form, discipline: e.target.value })}>
                <option value="">Every discipline</option>
                {disciplines.map((d) => <option key={d} value={d}>{d}</option>)}
              </Select>
            </Field>
          )}
          {error && <div className="sm:col-span-2">{alertBox(error)}</div>}
        </div>
      )}
    </Dialog>
  );
}

// ── Import a price list ──────────────────────────────────────────────────────
function ImportRates({ open, source, onClose, onDone }: { open: boolean; source: RateSource; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [src, setSrc] = useState<RateSource>(source);
  const [csv, setCsv] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RateImportResult | null>(null);
  useEffect(() => { if (open) { setSrc(source); setCsv(""); setError(null); setResult(null); } }, [open, source]);

  const dataRows = csv.trim() ? Math.max(0, csv.trim().split(/\r?\n/).length - 1) : 0;
  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.importRates(src, csv);
      setResult(res);
      if (res.added + res.superseded > 0) { toast.success(`${res.added + res.superseded} rate${res.added + res.superseded === 1 ? "" : "s"} loaded.`); onDone(); }
    } catch (e) {
      setError(errorText(e, "The import failed."));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={open} onClose={onClose} wide title="Import rates"
      description="A CSV file with a header row: code, rate, effective_from, and optionally discipline, kind, source, note. A row that repeats an existing rate and date is skipped. A bad row is reported and does not stop the rest."
      footer={<><Button onClick={onClose}>{result ? "Close" : "Cancel"}</Button><Button variant="primary" loading={busy} disabled={!csv.trim()} onClick={run}>Import{dataRows ? ` ${dataRows} row${dataRows === 1 ? "" : "s"}` : ""}</Button></>}
    >
      <div className="space-y-3">
        <Field label="Price list for rows that do not name one">
          <Select value={src} onChange={(e) => setSrc(e.target.value as RateSource)}>
            {(Object.keys(SOURCES) as RateSource[]).map((k) => <option key={k} value={k}>{SOURCES[k].label}</option>)}
          </Select>
        </Field>
        <div className="flex items-center gap-3">
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="hidden" onChange={async (e) => { const f = e.target.files?.[0]; if (f) { setCsv(await f.text()); setResult(null); } }} />
          <Button icon={Upload} onClick={() => fileRef.current?.click()}>Choose a file</Button>
          <span className="text-[13px] text-ink-500">or paste the rows below</span>
        </div>
        <Field label="Rows">
          <Textarea rows={7} className="font-mono text-xs" placeholder={"code,rate,effective_from,discipline\n0190,415.20,2027-04-01,GP"} value={csv} onChange={(e) => { setCsv(e.target.value); setResult(null); }} />
        </Field>
        {alertBox(error)}
        {result && (
          <div className="rounded-md border border-line bg-ink-50 px-3 py-2.5 text-[13px] text-ink-700">
            <div className="font-medium text-ink-900">{result.added} added, {result.superseded} replaced an earlier rate, {result.skipped} skipped, {result.errors.length} not loaded</div>
            {result.errors.length > 0 && <ul className="mt-1.5 max-h-40 space-y-0.5 overflow-y-auto">{result.errors.map((m) => <li key={m}>{m}</li>)}</ul>}
          </div>
        )}
      </div>
    </Dialog>
  );
}

// ── Every change to a rate ───────────────────────────────────────────────────
function ChangeLog({ version }: { version: number }) {
  const [rows, setRows] = useState<RateLogRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => {
    api.rateLog(200).then(setRows).catch((e) => { setRows([]); setError(errorText(e, "The change log could not be loaded.")); });
  }, [version]);
  const shown = (rows ?? []).filter((r) => !q.trim() || r.code.toLowerCase().includes(q.trim().toLowerCase()) || r.changed_by.toLowerCase().includes(q.trim().toLowerCase()));
  const columns: Column<RateLogRow>[] = [
    { key: "when", header: "When", render: (r) => <span className="tnum whitespace-nowrap text-ink-700">{dateTime(r.changed_at)}</span> },
    { key: "who", header: "Who", render: (r) => <span className="font-medium text-ink-900">{r.changed_by}</span> },
    { key: "code", header: "Code", render: (r) => <div><Ref className="text-ink-900">{r.code}</Ref><div className="text-xs text-ink-500">{SOURCES[r.source]?.label ?? r.source}{r.discipline ? `, ${r.discipline}` : ""}</div></div> },
    { key: "change", header: "Change", render: (r) => <div><div className="text-ink-900">{LOG_ACTIONS[r.action] ?? r.action}</div>{r.note && <div className="max-w-[40ch] text-[13px] text-ink-500">{r.note}</div>}</div> },
    { key: "amount", header: "Rate", align: "right", render: (r) => <span className="tnum whitespace-nowrap">{r.old_rate != null && r.old_rate !== r.new_rate ? <span className="text-ink-500">{money(r.old_rate)} → </span> : null}<span className="font-medium text-ink-900">{money(r.new_rate)}</span></span> },
    { key: "from", header: "From", render: (r) => <span className="text-ink-700">{shortDate(r.new_effective_from ?? r.old_effective_from)}</span> },
  ];
  if (error) return <ErrorBlock message={error} />;
  return (
    <>
      <div className="mb-3 rounded-lg border border-line bg-white p-3 shadow-panel"><div className="sm:w-72"><Input placeholder="Code or person" aria-label="Search the change log" value={q} onChange={(e) => setQ(e.target.value)} /></div></div>
      <DataTable
        columns={columns} rows={shown} rowKey={(r) => String(r.id)} loading={rows === null}
        empty={<EmptyState title={q ? "No change matches" : "No rate has been changed yet"} body={q ? "Change the search." : "Every new, corrected or ended rate is listed here with who made the change."} />}
        footer={<span className="text-[13px] text-ink-500">{shown.length} of the latest {rows?.length ?? 0} changes</span>}
      />
    </>
  );
}
