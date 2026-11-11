// Coding analysis. Where the money goes by billing code: what was reduced on assessment, what
// was paid above the reference price, and what has no reference price at all. Also the usual
// cost of treating each injury, and the practices whose prices are creeping up.

import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, Pager, type Column, type Sort } from "../ds/DataTable";
import { humanise } from "../ds/labels";
import { Dialog } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, PageHeader, Panel, Ref, Select, Stat, Tabs } from "../ds/primitives";
import type { Tone } from "../ds/labels";
import { rand } from "../format";
import type { CodeAgg, ConditionRow, CostEstimate, DriftReport, DriftRow } from "../types";
import { useListParams } from "./work/shared";

type Tab = "codes" | "targets" | "injuries" | "drift";
const KINDS: Record<string, string> = { TARIFF: "Tariff code", NAPPI: "Medicine or material" };
const VERDICTS: Record<string, { label: string; tone: Tone }> = {
  BELOW_TYPICAL: { label: "Below the usual range", tone: "info" }, TYPICAL: { label: "Within the usual range", tone: "ok" },
  HIGH: { label: "High", tone: "warn" }, OUTLIER: { label: "Far above the usual range", tone: "bad" },
  UNKNOWN: { label: "No comparison available", tone: "neutral" },
};
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);
const money = (v: number) => (v > 0 ? rand(v) : "—");

function useData<T>(loader: () => Promise<T>, fallback: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { loader().then(setData).catch((e) => setError(message(e, fallback))); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error };
}

export default function CodingPage() {
  const { value, reset } = useListParams();
  const t = value("tab");
  const tab: Tab = t === "targets" || t === "injuries" || t === "drift" ? t : "codes";
  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Integrity" }, { label: "Coding analysis" }]}
        title="Coding analysis"
        subtitle="Where the money goes by billing code, what treating each injury usually costs, and which practices' prices are creeping up. Read-only: nothing here changes a claim."
      />
      <Tabs<Tab>
        tabs={[{ key: "codes", label: "Codes" }, { key: "targets", label: "Rates worth negotiating" }, { key: "injuries", label: "Cost by injury" }, { key: "drift", label: "Rising prices" }]}
        value={tab} onChange={(k) => reset(k === "codes" ? {} : { tab: k })}
      />
      <div className="mt-4">
        {tab === "codes" && <Codes />}
        {tab === "targets" && <Targets />}
        {tab === "injuries" && <Injuries />}
        {tab === "drift" && <Drift />}
      </div>
    </div>
  );
}

function Codes() {
  const { value, page, pageSize, set } = useListParams();
  const { data, error } = useData<CodeAgg[]>(() => api.codingCodes(), "The codes could not be loaded.");
  const sort: Sort = { key: value("sort") || "billed", direction: value("dir") === "asc" ? "asc" : "desc" };
  const all = data ?? [];
  const shown = useMemo(() => {
    const needle = value("q").trim().toLowerCase();
    const list = all.filter((c) => (!value("kind") || c.kind === value("kind")) && c.code.toLowerCase().includes(needle));
    const key = (c: CodeAgg) => sort.key === "reduced" ? c.repricing_captured : sort.key === "above" ? c.over_reference_signal : sort.key === "none" ? c.uncovered_billed : sort.key === "lines" ? c.n_lines : c.billed;
    return [...list].sort((a, b) => (key(a) - key(b)) * (sort.direction === "asc" ? 1 : -1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, value("q"), value("kind"), sort.key, sort.direction]);
  const sum = (f: (c: CodeAgg) => number) => all.reduce((s, c) => s + f(c), 0);
  const columns: Column<CodeAgg>[] = [
    { key: "code", header: "Code", render: (c) => <div><Ref className="font-medium text-ink-900">{c.code}</Ref><div className="text-xs text-ink-500">{KINDS[c.kind] ?? c.kind}</div></div> },
    { key: "lines", header: "Lines", align: "right", sortable: true, render: (c) => <div><div className="tnum">{c.n_lines}</div><div className="tnum text-xs text-ink-500">{c.n_providers} practice{c.n_providers === 1 ? "" : "s"}</div></div> },
    { key: "billed", header: "Billed", align: "right", sortable: true, render: (c) => <span className="tnum text-ink-800">{rand(c.billed)}</span> },
    { key: "payable", header: "Payable", align: "right", render: (c) => <span className="tnum font-medium text-ink-900">{rand(c.payable)}</span> },
    { key: "reduced", header: "Reduced on assessment", align: "right", sortable: true, render: (c) => <span className="tnum text-ok-fg">{money(c.repricing_captured)}</span> },
    { key: "above", header: "Paid above reference", align: "right", sortable: true, render: (c) => <span className="tnum text-warn-fg">{money(c.over_reference_signal)}</span> },
    { key: "none", header: "No reference price", align: "right", sortable: true, render: (c) => <span className="tnum text-warn-fg">{money(c.uncovered_billed)}</span> },
  ];
  if (error) return <ErrorBlock message={error} />;
  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Billed" value={data ? rand(sum((c) => c.billed)) : "…"} hint={data ? `${all.length} codes` : undefined} />
        <Stat label="Reduced on assessment" value={data ? rand(sum((c) => c.repricing_captured)) : "…"} tone="ok" hint="Billed above an enforceable price and cut back" />
        <Stat label="Paid above reference" value={data ? rand(sum((c) => c.over_reference_signal)) : "…"} tone="warn" hint="The reference could not be enforced" />
        <Stat label="No reference price" value={data ? rand(sum((c) => c.uncovered_billed)) : "…"} tone="warn" hint="Paid as billed" />
      </div>
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-4">
        <Input className="sm:col-span-2 font-mono" placeholder="Code" aria-label="Search codes" value={value("q")} onChange={(e) => set({ q: e.target.value })} />
        <Select aria-label="Kind" value={value("kind")} onChange={(e) => set({ kind: e.target.value })}>
          <option value="">Any kind</option>
          {Object.entries(KINDS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </Select>
        {(value("q") || value("kind")) && <div className="flex items-center"><Button size="sm" variant="ghost" icon={X} onClick={() => set({ q: null, kind: null })}>Clear filters</Button></div>}
      </div>
      <DataTable
        columns={columns} rows={shown.slice((page - 1) * pageSize, page * pageSize)} rowKey={(c) => `${c.kind}:${c.code}`} loading={data === null}
        sort={sort} onSort={(s) => set({ sort: s.key === "billed" ? null : s.key, dir: s.direction === "asc" ? "asc" : null }, true)}
        empty={<EmptyState title={value("q") || value("kind") ? "No code matches" : "Nothing has been billed yet"} body={value("q") || value("kind") ? "Change or clear the filters." : "Codes appear here once claims are assessed."} />}
        footer={<Pager page={page} pageSize={pageSize} total={shown.length} unit="codes" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
      />
    </>
  );
}

function Targets() {
  const { user } = useAuth();
  const { data, error } = useData<CodeAgg[]>(api.negotiationTargets, "The list could not be loaded.");
  const all = data ?? [];
  const columns: Column<CodeAgg>[] = [
    { key: "code", header: "Code", render: (c) => <div><Ref className="font-medium text-ink-900">{c.code}</Ref><div className="text-xs text-ink-500">{KINDS[c.kind] ?? c.kind}</div></div> },
    { key: "lines", header: "Lines", align: "right", render: (c) => <div><div className="tnum">{c.n_lines}</div><div className="tnum text-xs text-ink-500">{c.n_providers} practice{c.n_providers === 1 ? "" : "s"}</div></div> },
    { key: "billed", header: "Billed", align: "right", render: (c) => <span className="tnum text-ink-800">{rand(c.billed)}</span> },
    { key: "above", header: "Paid above reference", align: "right", render: (c) => <span className="tnum">{money(c.over_reference_signal)}</span> },
    { key: "none", header: "No reference price", align: "right", render: (c) => <span className="tnum">{money(c.uncovered_billed)}</span> },
    { key: "saving", header: "Spend a rate would control", align: "right", render: (c) => <span className="tnum font-semibold text-ink-900">{rand(c.potential_saving ?? 0)}</span> },
  ];
  if (error) return <ErrorBlock message={error} />;
  return (
    <>
      <div className="mb-3 rounded-lg border border-info-line bg-info-bg px-4 py-3 text-sm text-info-fg">
        These codes are paid in full today, either because the reference price cannot be enforced or because there is none. Agreeing a rate for a code brings that spend under control. Codes that already have a negotiated rate are left out.
        {user?.role === "ADMIN" && <> Rates are added under <Link to="/admin/negotiated" className="font-medium underline">Negotiated rates</Link>.</>}
      </div>
      <DataTable
        columns={columns} rows={all} rowKey={(c) => `${c.kind}:${c.code}`} loading={data === null}
        empty={<EmptyState title="No code stands out" body="Every code with spend is already priced against an enforceable reference or a negotiated rate." />}
        footer={<span className="text-[13px] text-ink-500">{all.length} codes, largest first. {rand(all.reduce((s, c) => s + (c.potential_saving ?? 0), 0))} in total.</span>}
      />
    </>
  );
}

function Injuries() {
  const { data, error } = useData<ConditionRow[]>(api.conditions, "The cost ranges could not be loaded.");
  const [open, setOpen] = useState<ConditionRow | null>(null);
  const [check, setCheck] = useState({ injury: "", amount: "" });
  const [result, setResult] = useState<CostEstimate | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const all = data ?? [];

  async function run() {
    if (!check.injury.trim() || !(Number(check.amount) > 0)) { setCheckError("Enter the injury code and an amount."); return; }
    setBusy(true);
    setCheckError(null);
    try {
      setResult(await api.estimateCondition(check.injury.trim().toUpperCase(), Number(check.amount)));
    } catch (e) {
      setCheckError(message(e, "The amount could not be checked."));
    } finally {
      setBusy(false);
    }
  }
  const columns: Column<ConditionRow>[] = [
    { key: "injury", header: "Injury", render: (r) => <Ref className="font-medium text-ink-900">{r.injury_class}</Ref> },
    { key: "n", header: "Claims", align: "right", render: (r) => <span className="tnum">{r.n}</span> },
    { key: "usual", header: "Usual range", align: "right", render: (r) => r.bands ? <span className="tnum text-ink-900">{rand(r.bands.p25)} to {rand(r.bands.p75)}</span> : <span className="text-ink-400">—</span> },
    { key: "mid", header: "Middle", align: "right", render: (r) => r.bands ? <span className="tnum font-medium text-ink-900">{rand(r.bands.p50)}</span> : <span className="text-ink-400">—</span> },
    { key: "high", header: "High mark", align: "right", render: (r) => r.bands ? <span className="tnum text-ink-700">{rand(r.bands.p90)}</span> : <span className="text-ink-400">—</span> },
    { key: "robust", header: "", render: (r) => r.robust ? <Badge tone="ok">Reliable</Badge> : <Badge>Too few claims</Badge> },
  ];
  if (error) return <ErrorBlock message={error} />;
  return (
    <div className="space-y-4">
      <Panel title="Check an amount" description="Compare a claim's medical total with what treating that injury usually costs.">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Injury (first three characters of the ICD-10 code)"><Input className="w-40 font-mono" value={check.injury} onChange={(e) => setCheck({ ...check, injury: e.target.value })} placeholder="S72" /></Field>
          <Field label="Medical total (R)"><Input type="number" min={0} className="w-44" value={check.amount} onChange={(e) => setCheck({ ...check, amount: e.target.value })} onKeyDown={(e) => { if (e.key === "Enter") void run(); }} /></Field>
          <Button variant="primary" loading={busy} onClick={run}>Check</Button>
          {result && (
            <div className="flex items-center gap-2 text-sm">
              <Badge tone={VERDICTS[result.classification]?.tone ?? "neutral"} dot>{VERDICTS[result.classification]?.label ?? humanise(result.classification)}</Badge>
              <span className="text-ink-600">{result.bands ? `Usual range ${rand(result.bands.p25)} to ${rand(result.bands.p75)}, from ${result.n} claims${result.robust ? "" : " (too few to rely on)"}.` : `Only ${result.n} claim${result.n === 1 ? "" : "s"} for this injury.`}</span>
            </div>
          )}
        </div>
        {checkError && <p className="mt-2 text-[13px] text-bad-fg" role="alert">{checkError}</p>}
      </Panel>
      <DataTable
        columns={columns} rows={all} rowKey={(r) => r.injury_class} loading={data === null} onRowClick={setOpen}
        empty={<EmptyState title="No cost ranges yet" body="Ranges appear once enough claims for an injury have been assessed." />}
        footer={<span className="text-[13px] text-ink-500">The usual range is the middle half of claims. A range is reliable from 20 claims.</span>}
      />
      <Dialog open={open !== null} onClose={() => setOpen(null)} wide title={open ? `Cost of treating ${open.injury_class}` : ""} description="Split by whether a specialist was involved, since that changes what treatment costs.">
        {open && (
          <table className="min-w-full border-collapse text-sm">
            <thead><tr className="border-b border-line text-left text-xs text-ink-500"><th className="py-2 pr-3 font-medium">Treatment</th><th className="px-3 py-2 text-right font-medium">Claims</th><th className="px-3 py-2 text-right font-medium">Usual range</th><th className="px-3 py-2 text-right font-medium">Middle</th><th className="py-2 pl-3 text-right font-medium">Lowest to highest</th></tr></thead>
            <tbody className="divide-y divide-line">
              {[["All claims", open] as const, ...Object.entries(open.by_intensity).map(([k, v]) => [humanise(k), v] as const)].map(([label, v]) => (
                <tr key={label}>
                  <td className="py-2 pr-3 text-ink-900">{label}</td>
                  <td className="tnum px-3 py-2 text-right">{v.n}{!v.robust && <span className="text-ink-400"> (few)</span>}</td>
                  <td className="tnum px-3 py-2 text-right">{v.bands ? `${rand(v.bands.p25)} to ${rand(v.bands.p75)}` : "—"}</td>
                  <td className="tnum px-3 py-2 text-right font-medium">{v.bands ? rand(v.bands.p50) : "—"}</td>
                  <td className="tnum py-2 pl-3 text-right text-ink-600">{v.bands ? `${rand(v.bands.min)} to ${rand(v.bands.max)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Dialog>
    </div>
  );
}

function Drift() {
  const navigate = useNavigate();
  const { data, error } = useData<DriftReport>(api.priceDrift, "The trends could not be loaded.");
  const [open, setOpen] = useState<DriftRow | null>(null);
  const pct = (r: number) => `${Math.round(r * 100)}%`;
  const columns: Column<DriftRow>[] = [
    { key: "practice", header: "Practice", render: (r) => <Ref className="font-medium text-brand-700">{r.provider_id}</Ref> },
    { key: "period", header: "Period", render: (r) => <span className="text-ink-700">{r.first_month} to {r.last_month}</span> },
    { key: "months", header: "Months", align: "right", render: (r) => <span className="tnum">{r.n_months}</span> },
    { key: "from", header: "Billed against reference", align: "right", render: (r) => <span className="tnum text-ink-800">{pct(r.first_ratio)} → <span className="font-semibold text-ink-900">{pct(r.last_ratio)}</span></span> },
    { key: "slope", header: "Rise a month", align: "right", render: (r) => <span className="tnum text-warn-fg">+{(r.slope_per_month * 100).toFixed(1)} points</span> },
    { key: "more", header: "", align: "right", render: (r) => <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setOpen(r); }}>Month by month</Button> },
  ];
  if (error) return <ErrorBlock message={error} />;
  return (
    <>
      <div className="mb-3 rounded-lg border border-info-line bg-info-bg px-4 py-3 text-sm text-info-fg">
        Each practice's billing is compared with the reference price, month by month. 100% means it bills exactly at the reference. A practice is listed when that figure has risen steadily over at least {data?.min_months ?? 6} months{data ? `, counting only months with ${data.min_lines} or more lines` : ""}.
      </div>
      <DataTable
        columns={columns} rows={data?.rising ?? []} rowKey={(r) => r.provider_id} loading={data === null} onRowClick={(r) => navigate(`/practices/${encodeURIComponent(r.provider_id)}`)}
        empty={<EmptyState title="No practice's prices are rising" body={data ? `${data.n_providers} practice${data.n_providers === 1 ? " has" : "s have"} enough history to judge. None shows a steady rise.` : undefined} />}
        footer={data ? <span className="text-[13px] text-ink-500">{data.rising.length} of {data.n_providers} practices with enough history</span> : undefined}
      />
      <Dialog open={open !== null} onClose={() => setOpen(null)} title={open ? `Practice ${open.provider_id}, month by month` : ""} description="Billed as a share of the reference price.">
        {open && (
          <ul className="space-y-1.5">
            {open.series.map((m) => (
              <li key={m.month} className="grid grid-cols-[5.5rem_1fr_3.5rem] items-center gap-2 text-sm">
                <span className="tnum text-ink-600">{m.month}</span>
                <span className="h-1.5 overflow-hidden rounded-full bg-ink-100"><span className="block h-full rounded-full bg-ink-700" style={{ width: `${Math.min(100, (m.ratio / Math.max(...open.series.map((x) => x.ratio), 1)) * 100)}%` }} /></span>
                <span className="tnum text-right font-medium text-ink-900">{pct(m.ratio)}</span>
              </li>
            ))}
          </ul>
        )}
      </Dialog>
    </>
  );
}
