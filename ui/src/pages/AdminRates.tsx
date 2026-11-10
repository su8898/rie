// Admin → Dated rates. The payment-rule reference rates as append-only VERSIONS:
// a new rate for a later date supersedes the prior one from that date, and the
// engine prices every line at the version in force on its SERVICE date — so a
// late claim pays at the tariff of its day and an increase never reprices history.
//
// Three tiers: RPL (tariff × discipline), NEGOTIATED (tariff / NAPPI), SEP
// (NAPPI single exit price). This tab browses the rate in force on a chosen date
// (server-paged — SEP is ~540k rows), shows a key's version history, and does the
// maintenance: add / supersede, % increase (one or every row in the filter),
// correct, retire, CSV import and export. Every change is logged.

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { Card, Empty, ErrorBox, Loading, Pagination, SearchInput, Toast } from "../components/ui";
import { rand } from "../format";
import type {
  RateImportResult,
  RateList,
  RateLogRow,
  RateRow,
  RateSource,
  RateSummary,
  RateVersion,
} from "../types";

const PAGE = 25;
const SOURCES: { key: RateSource; label: string; hint: string }[] = [
  { key: "RPL", label: "Tariff (RPL)", hint: "tariff code × provider discipline" },
  { key: "NEGOTIATED", label: "Negotiated", hint: "contract rate per tariff or NAPPI code" },
  { key: "SEP", label: "NAPPI exit price", hint: "single exit price, before the dispensing fee" },
];

const th = "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";
const inputCls =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const primaryBtn =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40";
const smallBtn =
  "rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40";
const dangerBtn =
  "rounded-md border border-rose-200 px-2.5 py-1 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-40";
const labelCls = "mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400";

// A materialised undated rate starts at the baseline sentinel; show it as "start".
const BASELINE = "1900-01-01";
const from = (d: string | null) => (d === null ? "undated" : d === BASELINE ? "start" : d);

const rowKey = (r: { source: string; kind: string; code: string; discipline: string }) =>
  `${r.source}:${r.kind}:${r.code}:${r.discipline}`;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className={labelCls}>{label}</label>
      {children}
    </div>
  );
}

export default function RatesTab() {
  const [source, setSource] = useState<RateSource>("RPL");
  const [q, setQ] = useState("");
  const [discipline, setDiscipline] = useState("");
  const [on, setOn] = useState("");
  const [page, setPage] = useState(0);

  const [list, setList] = useState<RateList | null>(null);
  const [summary, setSummary] = useState<RateSummary | null>(null);
  const [log, setLog] = useState<RateLogRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [open, setOpen] = useState<RateRow | null>(null);
  const [versions, setVersions] = useState<RateVersion[] | null>(null);

  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "error" | "success" } | null>(null);

  // add / supersede form
  const [fKind, setFKind] = useState<"TARIFF" | "NAPPI">("TARIFF");
  const [fCode, setFCode] = useState("");
  const [fDisc, setFDisc] = useState("");
  const [fRate, setFRate] = useState("");
  const [fFrom, setFFrom] = useState("");
  const [fNote, setFNote] = useState("");
  // bulk increase
  const [bPct, setBPct] = useState("");
  const [bFrom, setBFrom] = useState("");
  // import
  const [csv, setCsv] = useState("");
  const [imported, setImported] = useState<RateImportResult | null>(null);

  const kindFor = (s: RateSource) => (s === "RPL" ? "TARIFF" : s === "SEP" ? "NAPPI" : fKind);

  const load = useCallback(async () => {
    try {
      const [l, s, g] = await Promise.all([
        api.rates({
          source,
          q: q.trim(),
          discipline: source === "RPL" ? discipline.trim() : "",
          on: on || undefined,
          limit: PAGE,
          offset: page * PAGE,
        }),
        api.rateSummary(),
        api.rateLog(20),
      ]);
      setList(l);
      setSummary(s);
      setLog(g);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load rates.");
    }
  }, [source, q, discipline, on, page]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 200); // debounce typing in the filters
    return () => clearTimeout(t);
  }, [load]);

  const loadVersions = useCallback(async (r: RateRow) => {
    setVersions(null);
    try {
      setVersions(await api.rateVersions(r));
    } catch (e) {
      setToast({ message: e instanceof ApiError ? e.message : "Failed to load versions.", tone: "error" });
    }
  }, []);

  const run = (key: string, fn: () => Promise<unknown>, okMsg: string | ((r: unknown) => string)) => {
    if (busy !== null) return;
    setBusy(key);
    fn()
      .then(async (r) => {
        await load();
        if (open) await loadVersions(open);
        setToast({ message: typeof okMsg === "function" ? okMsg(r) : okMsg, tone: "success" });
      })
      .catch((e) =>
        setToast({ message: e instanceof ApiError ? e.message : "Request failed.", tone: "error" }),
      )
      .finally(() => setBusy(null));
  };

  const pickSource = (s: RateSource) => {
    setSource(s);
    setPage(0);
    setOpen(null);
    setVersions(null);
    setImported(null);
  };

  const toggle = (r: RateRow) => {
    if (open && rowKey(open) === rowKey(r)) {
      setOpen(null);
      setVersions(null);
    } else {
      setOpen(r);
      void loadVersions(r);
    }
  };

  const increaseOne = (r: RateRow) => {
    const pct = window.prompt(`Increase ${r.code}${r.discipline ? ` / ${r.discipline}` : ""} by what percentage?`, "5");
    if (pct === null || pct.trim() === "") return;
    const eff = window.prompt("Effective from (YYYY-MM-DD)?", "");
    if (eff === null || eff.trim() === "") return;
    run(
      `inc.${rowKey(r)}`,
      () =>
        api.increaseRate({
          source: r.source,
          kind: r.kind,
          code: r.code,
          discipline: r.discipline,
          pct: Number(pct),
          effective_from: eff.trim(),
        }),
      `New version for ${r.code} from ${eff.trim()}.`,
    );
  };

  const adjust = (v: RateVersion) => {
    if (v.id === null) return;
    const rate = window.prompt("Correct this version's amount to:", String(v.rate));
    if (rate === null || rate.trim() === "") return;
    const note = window.prompt("Reason for the correction?", "") ?? "";
    run(`adj.${v.id}`, () => api.adjustRate(v.id as number, Number(rate), note), "Version corrected.");
  };

  const retire = (v: RateVersion) => {
    if (v.id === null) return;
    const to = window.prompt("Last day this rate applies (YYYY-MM-DD)?", "");
    if (to === null || to.trim() === "") return;
    const note = window.prompt("Reason for retiring it?", "") ?? "";
    run(`ret.${v.id}`, () => api.retireRate(v.id as number, to.trim(), note), "Version retired.");
  };

  const canAdd =
    fCode.trim() !== "" && fRate !== "" && fFrom !== "" && (source !== "RPL" || fDisc.trim() !== "") && busy === null;
  const canBulk = source !== "SEP" && bPct !== "" && bFrom !== "" && busy === null;
  const pageCount = list ? Math.max(1, Math.ceil(list.total / PAGE)) : 1;
  const active = SOURCES.find((s) => s.key === source)!;

  return (
    <div className="space-y-4">
      {loadError && <ErrorBox message={loadError} />}

      <Card
        title="Rates in force"
        sub={
          <>
            The rate the engine pays against, per key, on the chosen date — {active.hint}. A dated key
            is priced from its versions on the line&apos;s service date; an undated key (the loaded
            snapshot) is in force on every date until its first dated change.
            {summary && (
              <>
                {" "}
                {summary.versions.toLocaleString("en-ZA")} versions across{" "}
                {summary.dated_keys.toLocaleString("en-ZA")} dated keys;{" "}
                {summary.changes.toLocaleString("en-ZA")} logged changes.
              </>
            )}
          </>
        }
        right={
          <a href={api.rateExportUrl(source, on || undefined)} className={smallBtn} download>
            Export CSV
          </a>
        }
      >
        <div className="mb-3 flex flex-wrap items-end gap-3">
          <div className="flex gap-1">
            {SOURCES.map((s) => (
              <button
                key={s.key}
                onClick={() => pickSource(s.key)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  source === s.key
                    ? "bg-slate-800 text-white"
                    : "border border-slate-300 text-slate-700 hover:bg-slate-100"
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
          <SearchInput
            value={q}
            onChange={(v) => {
              setQ(v);
              setPage(0);
            }}
            placeholder="Code starts with…"
            className="w-44"
          />
          {source === "RPL" && (
            <SearchInput
              value={discipline}
              onChange={(v) => {
                setDiscipline(v);
                setPage(0);
              }}
              placeholder="Discipline (exact)"
              className="w-44"
            />
          )}
          <Field label="As at">
            <input type="date" value={on} onChange={(e) => setOn(e.target.value)} className={inputCls} />
          </Field>
        </div>

        {list === null ? (
          <Loading label="Loading rates…" />
        ) : list.items.length === 0 ? (
          <Empty label="No rates match." />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className={`${th} text-left`}>Code</th>
                    {source === "RPL" && <th className={`${th} text-left`}>Discipline</th>}
                    {source === "NEGOTIATED" && <th className={`${th} text-left`}>Kind</th>}
                    <th className={`${th} text-right`}>Rate on {list.on}</th>
                    <th className={`${th} text-left`}>In force</th>
                    <th className={`${th} text-right`}>Versions</th>
                    <th className={`${th} text-right`}>Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {list.items.map((r) => {
                    const isOpen = open !== null && rowKey(open) === rowKey(r);
                    return (
                      <RateRows
                        key={rowKey(r)}
                        r={r}
                        source={source}
                        isOpen={isOpen}
                        versions={isOpen ? versions : null}
                        busy={busy}
                        onToggle={() => toggle(r)}
                        onIncrease={() => increaseOne(r)}
                        onAdjust={adjust}
                        onRetire={retire}
                      />
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pageCount={pageCount} total={list.total} onPage={setPage} unit="rates" />
          </div>
        )}
      </Card>

      <Card
        title="Add a dated version"
        sub="A new rate from an effective date. If the key already has a rate in force on that date it is superseded — closed the day before — and stays on the books for earlier service dates. Maintenance is forward-only: the date must be after every existing version of the key."
      >
        <div className="flex flex-wrap items-end gap-3">
          {source === "NEGOTIATED" && (
            <Field label="Kind">
              <select value={fKind} onChange={(e) => setFKind(e.target.value as "TARIFF" | "NAPPI")} className={inputCls}>
                <option value="TARIFF">TARIFF</option>
                <option value="NAPPI">NAPPI</option>
              </select>
            </Field>
          )}
          <Field label="Code">
            <input value={fCode} onChange={(e) => setFCode(e.target.value)} className={inputCls} placeholder="0190" />
          </Field>
          {source === "RPL" && (
            <Field label="Discipline">
              <input value={fDisc} onChange={(e) => setFDisc(e.target.value)} className={inputCls} placeholder="GP" />
            </Field>
          )}
          <Field label="Rate">
            <input type="number" min="0" step="0.01" value={fRate} onChange={(e) => setFRate(e.target.value)} className={`tnum ${inputCls}`} placeholder="0.00" />
          </Field>
          <Field label="Effective from">
            <input type="date" value={fFrom} onChange={(e) => setFFrom(e.target.value)} className={inputCls} />
          </Field>
          <Field label="Note">
            <input value={fNote} onChange={(e) => setFNote(e.target.value)} className={`w-56 ${inputCls}`} placeholder="e.g. 2027 gazette" />
          </Field>
          <button
            disabled={!canAdd}
            className={primaryBtn}
            onClick={() =>
              run(
                "add",
                () =>
                  api.addRate({
                    source,
                    kind: kindFor(source),
                    code: fCode.trim(),
                    discipline: source === "RPL" ? fDisc.trim() : "",
                    rate: Number(fRate),
                    effective_from: fFrom,
                    note: fNote.trim(),
                  }),
                (r) => `${(r as RateVersion).action === "SUPERSEDE" ? "Superseded" : "Created"} ${fCode.trim()} from ${fFrom}.`,
              )
            }
          >
            {busy === "add" ? "Saving…" : "Save version"}
          </button>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card
          title="Percentage increase — every rate in the filter"
          sub={
            source === "SEP"
              ? "Not available for the NAPPI exit-price register — load the new price file instead."
              : "Supersedes every rate matching the filter above with rate × (1 + %), from the effective date. One new version per key; a key that already has a version on or after the date is skipped and reported."
          }
        >
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Percent">
              <input type="number" step="0.1" value={bPct} onChange={(e) => setBPct(e.target.value)} className={`tnum w-24 ${inputCls}`} placeholder="5" disabled={source === "SEP"} />
            </Field>
            <Field label="Effective from">
              <input type="date" value={bFrom} onChange={(e) => setBFrom(e.target.value)} className={inputCls} disabled={source === "SEP"} />
            </Field>
            <button
              disabled={!canBulk}
              className={primaryBtn}
              onClick={() => {
                const scope = `${list?.total.toLocaleString("en-ZA") ?? "all"} ${source} rate(s)` + (q.trim() ? ` starting "${q.trim()}"` : "") + (source === "RPL" && discipline.trim() ? ` for ${discipline.trim()}` : "");
                if (!window.confirm(`Increase ${scope} by ${bPct}% from ${bFrom}?`)) return;
                run(
                  "bulk",
                  () =>
                    api.bulkIncreaseRates({
                      source,
                      pct: Number(bPct),
                      effective_from: bFrom,
                      q: q.trim(),
                      discipline: source === "RPL" ? discipline.trim() : "",
                    }),
                  (r) => {
                    const x = r as { increased: number; skipped: number };
                    return `${x.increased} rate(s) increased${x.skipped ? `, ${x.skipped} skipped` : ""}.`;
                  },
                );
              }}
            >
              {busy === "bulk" ? "Applying…" : "Apply increase"}
            </button>
          </div>
        </Card>

        <Card
          title="Import CSV"
          sub="Header: code, rate, effective_from — plus discipline (tariff), kind (negotiated), note. Each row adds or supersedes a version; an exact repeat is skipped; a bad row is reported and does not stop the rest."
        >
          <textarea
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
            rows={4}
            className={`w-full font-mono text-xs ${inputCls}`}
            placeholder={"code,discipline,rate,effective_from\n0190,GP,525.00,2027-04-01"}
          />
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <input
              type="file"
              accept=".csv,text/csv"
              className="text-xs text-slate-500"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void f.text().then(setCsv);
              }}
            />
            <button
              disabled={csv.trim() === "" || busy !== null}
              className={primaryBtn}
              onClick={() =>
                run(
                  "import",
                  async () => {
                    const r = await api.importRates(source, csv);
                    setImported(r);
                    return r;
                  },
                  (r) => {
                    const x = r as RateImportResult;
                    return `Imported: ${x.added} added, ${x.superseded} superseded, ${x.skipped} skipped, ${x.failed} failed.`;
                  },
                )
              }
            >
              {busy === "import" ? "Importing…" : `Import as ${source}`}
            </button>
          </div>
          {imported && imported.errors.length > 0 && (
            <ul className="mt-2 max-h-32 list-disc overflow-y-auto pl-5 text-xs text-rose-600">
              {imported.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Change log" sub="The latest rate changes, newest first — who changed which rate, from what to what, and why.">
        {log === null ? (
          <Loading label="Loading log…" />
        ) : log.length === 0 ? (
          <Empty label="No rate changes yet." />
        ) : (
          <div className="overflow-x-auto rounded-md border border-slate-100">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>When</th>
                  <th className={`${th} text-left`}>By</th>
                  <th className={`${th} text-left`}>Action</th>
                  <th className={`${th} text-left`}>Rate</th>
                  <th className={`${th} text-right`}>Old</th>
                  <th className={`${th} text-right`}>New</th>
                  <th className={`${th} text-left`}>From</th>
                  <th className={`${th} text-left`}>Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {log.map((r) => (
                  <tr key={r.id} className="align-middle">
                    <td className="tnum px-3 py-2 text-xs text-slate-500">{(r.changed_at ?? "").replace("T", " ").slice(0, 16)}</td>
                    <td className="px-3 py-2 text-slate-700">{r.changed_by}</td>
                    <td className="px-3 py-2 text-xs font-semibold text-slate-600">{r.action}</td>
                    <td className="px-3 py-2 font-mono text-[13px] text-slate-900">
                      {r.source} {r.code}
                      {r.discipline ? ` / ${r.discipline}` : ""}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-500">{r.old_rate === null ? "—" : rand(r.old_rate)}</td>
                    <td className="tnum px-3 py-2 text-right font-medium text-slate-800">{r.new_rate === null ? "—" : rand(r.new_rate)}</td>
                    <td className="tnum px-3 py-2 text-xs text-slate-600">{r.new_effective_from ?? "—"}</td>
                    <td className="px-3 py-2 text-xs text-slate-500">{r.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {toast && <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />}
    </div>
  );
}

// One key's row plus, when open, its version history with correct / retire.
function RateRows({
  r,
  source,
  isOpen,
  versions,
  busy,
  onToggle,
  onIncrease,
  onAdjust,
  onRetire,
}: {
  r: RateRow;
  source: RateSource;
  isOpen: boolean;
  versions: RateVersion[] | null;
  busy: string | null;
  onToggle: () => void;
  onIncrease: () => void;
  onAdjust: (v: RateVersion) => void;
  onRetire: (v: RateVersion) => void;
}) {
  const span = source === "SEP" ? 5 : 6;
  return (
    <>
      <tr className="align-middle hover:bg-slate-50">
        <td className="px-3 py-2 font-mono text-[13px] text-slate-900">{r.code}</td>
        {source === "RPL" && <td className="px-3 py-2 text-slate-700">{r.discipline}</td>}
        {source === "NEGOTIATED" && <td className="px-3 py-2 text-slate-700">{r.kind}</td>}
        <td className="tnum px-3 py-2 text-right font-medium text-slate-800">
          {r.rate === null ? <span className="font-normal text-rose-500">none in force</span> : rand(r.rate)}
        </td>
        <td className="tnum px-3 py-2 text-xs text-slate-600">
          {r.dated ? (r.effective_from ? `${from(r.effective_from)} → ${r.effective_to ?? "open"}` : "—") : "undated"}
        </td>
        <td className="tnum px-3 py-2 text-right text-slate-600">{r.versions || "—"}</td>
        <td className="space-x-1 px-3 py-2 text-right">
          <button onClick={onToggle} className={smallBtn}>
            {isOpen ? "hide" : "history"}
          </button>
          <button onClick={onIncrease} disabled={busy !== null || r.rate === null} className={smallBtn}>
            + %
          </button>
        </td>
      </tr>
      {isOpen && (
        <tr className="bg-slate-50/60">
          <td colSpan={span} className="px-3 py-2">
            {versions === null ? (
              <Loading label="Loading versions…" />
            ) : versions.length === 0 ? (
              <Empty label="No versions." />
            ) : (
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wide text-slate-400">
                    <th className="py-1 pr-3">From</th>
                    <th className="py-1 pr-3">To</th>
                    <th className="py-1 pr-3 text-right">Rate</th>
                    <th className="py-1 pr-3">Origin</th>
                    <th className="py-1 pr-3">By</th>
                    <th className="py-1 pr-3">Note</th>
                    <th className="py-1 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {versions.map((v) => (
                    <tr key={v.id ?? "undated"} className="border-t border-slate-100">
                      <td className="tnum py-1 pr-3">{from(v.effective_from)}</td>
                      <td className="tnum py-1 pr-3">{v.effective_from ? (v.effective_to ?? "open") : "—"}</td>
                      <td className="tnum py-1 pr-3 text-right font-medium text-slate-800">{rand(v.rate)}</td>
                      <td className="py-1 pr-3 text-slate-500">{v.origin}</td>
                      <td className="py-1 pr-3 text-slate-500">{v.created_by || "—"}</td>
                      <td className="py-1 pr-3 text-slate-500">{v.note}</td>
                      <td className="space-x-1 py-1 text-right">
                        {v.id !== null && (
                          <>
                            <button onClick={() => onAdjust(v)} disabled={busy !== null} className={smallBtn}>
                              correct
                            </button>
                            <button onClick={() => onRetire(v)} disabled={busy !== null} className={dangerBtn}>
                              retire
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
