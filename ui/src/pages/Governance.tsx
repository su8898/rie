// Signal governance. How reliable each finding has proved on closed cases, which findings should
// carry more or less weight as a result, how much the engine misses, and the case outcomes all of
// this is measured from. Administrators apply a suggested change; everyone else can read.

import { Download, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, type Column } from "../ds/DataTable";
import { CASE_LANES, CASE_VERDICTS, MATURITY, SIGNAL_MODES, reasonLabel } from "../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, PageHeader, Panel, Ref, Select, Stat, Tabs } from "../ds/primitives";
import type { LabelRow, PrecisionRow, RecallEstimate, RecallSample } from "../types";
import { useListParams } from "./work/shared";

type Tab = "findings" | "changes" | "missed" | "outcomes";
const MIN_CHECKED = 5;
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);
const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const OUTCOME: Record<string, { label: string; tone: "bad" | "ok" | "neutral" }> = {
  ADVERSE: { label: "The finding was right", tone: "bad" }, BENIGN: { label: "False alarm", tone: "ok" }, OTHER: { label: "Not counted", tone: "neutral" },
};

export default function GovernancePage() {
  const toast = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const { value, reset, set } = useListParams();
  const t = value("tab");
  const tab: Tab = t === "changes" || t === "missed" || t === "outcomes" ? t : "findings";
  const [rows, setRows] = useState<PrecisionRow[] | null>(null);
  const [changes, setChanges] = useState<PrecisionRow[]>([]);
  const [recall, setRecall] = useState<RecallEstimate | null>(null);
  const [sample, setSample] = useState<RecallSample | null>(null);
  const [labels, setLabels] = useState<LabelRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applying, setApplying] = useState<PrecisionRow | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [drawN, setDrawN] = useState("30");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [p, c, r, s, l] = await Promise.all([api.precision(), api.promotions(), api.recall(), api.recallSample(30), api.labels()]);
      setRows(p); setChanges(c); setRecall(r); setSample(s); setLabels(l);
    } catch (e) {
      setError(message(e, "The governance figures could not be loaded."));
    }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const all = rows ?? [];
  const shown = useMemo(() => {
    const needle = value("q").trim().toLowerCase();
    return all.filter((r) => (!needle || r.signal.toLowerCase().includes(needle) || reasonLabel(r.signal).toLowerCase().includes(needle))
      && (value("show") === "" || (value("show") === "checked" ? r.labeled >= MIN_CHECKED : value("show") === "fired" ? r.fired > 0 : r.recommended_mode !== r.current_mode)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, value("q"), value("show")]);

  async function apply(reason: string) {
    if (!applying) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.setSignalMode({ code: applying.signal, mode: applying.recommended_mode, note: reason });
      toast.success(`${reasonLabel(applying.signal)} is now ${SIGNAL_MODES[applying.recommended_mode]?.label.toLowerCase() ?? applying.recommended_mode}.`);
      setApplying(null);
      await load();
    } catch (e) {
      setFormError(message(e, "The change could not be applied."));
    } finally {
      setBusy(false);
    }
  }
  async function draw() {
    const n = Number(drawN);
    if (!(n >= 1 && n <= 200)) { setFormError("Enter a number from 1 to 200."); return; }
    setBusy(true);
    setFormError(null);
    try {
      const res = await api.drawQaReviews(n);
      toast.success(res.drawn ? `${res.drawn} quality-check case${res.drawn === 1 ? "" : "s"} opened.${res.skipped ? ` ${res.skipped} already had one.` : ""}` : "No new cases: every sampled claim already has an open review.");
      setDrawing(false);
      await load();
    } catch (e) {
      setFormError(message(e, "The quality checks could not be opened."));
    } finally {
      setBusy(false);
    }
  }

  const finding = (r: PrecisionRow) => <div><div className="font-medium text-ink-900">{reasonLabel(r.signal)}</div><Ref className="text-xs text-ink-400">{r.signal}</Ref></div>;
  const mode = (m: string) => <Badge tone={SIGNAL_MODES[m]?.tone ?? "neutral"} dot>{SIGNAL_MODES[m]?.label ?? m}</Badge>;
  const borneOut = (r: PrecisionRow) => r.labeled === 0 ? <span className="text-ink-400">Not checked yet</span> : (
    <div>
      <div className="tnum text-ink-900">{r.substantiated} of {r.labeled} <span className="text-ink-500">({pct(r.substantiation)})</span></div>
      <div className="tnum text-xs text-ink-500">{r.labeled < MIN_CHECKED ? `Too few to judge; ${MIN_CHECKED} are needed` : `Likely between ${pct(r.wilson_lower)} and ${pct(r.wilson_upper)}`}</div>
    </div>
  );
  const columns: Column<PrecisionRow>[] = [
    { key: "finding", header: "Finding", render: finding },
    { key: "evidence", header: "Basis", render: (r) => <span className="text-ink-700">{MATURITY[r.maturity ?? ""] ?? r.maturity ?? "—"}</span> },
    { key: "fired", header: "Times raised", align: "right", render: (r) => <span className="tnum">{r.fired}</span> },
    { key: "borne", header: "Borne out on closed cases", render: borneOut },
    { key: "mode", header: "Mode now", render: (r) => mode(r.current_mode) },
    { key: "suggested", header: "Suggested", render: (r) => r.recommended_mode === r.current_mode ? <span className="text-[13px] text-ink-500">No change</span> : <Badge tone="warn">Move to {SIGNAL_MODES[r.recommended_mode]?.label.toLowerCase() ?? r.recommended_mode}</Badge> },
  ];
  const changeColumns: Column<PrecisionRow>[] = [
    { key: "finding", header: "Finding", render: finding },
    { key: "borne", header: "Borne out on closed cases", render: borneOut },
    { key: "move", header: "Change", render: (r) => <div className="flex flex-wrap items-center gap-1.5">{mode(r.current_mode)}<span className="text-ink-400">to</span>{mode(r.recommended_mode)}</div> },
    { key: "why", header: "Why", render: (r) => <span className="block max-w-[38ch] text-[13px] text-ink-600">{r.action === "PROMOTE" ? "It has proved reliable enough to carry more weight." : "It has not proved reliable enough for the weight it carries."}</span> },
    { key: "apply", header: "", align: "right", render: (r) => <Button size="sm" variant="primary" disabled={!isAdmin} title={isAdmin ? undefined : "Only an administrator can change a signal's mode."} onClick={() => { setFormError(null); setApplying(r); }}>Apply</Button> },
  ];
  const labelColumns: Column<LabelRow>[] = [
    { key: "claim", header: "Claim", render: (l) => <Link to={`/claims/${encodeURIComponent(l.claim_id)}`} className="font-medium text-brand-700 hover:underline"><Ref>{l.claim_id}</Ref></Link> },
    { key: "case", header: "Case", render: (l) => <Link to={`/cases/${l.case_id}`} className="text-brand-700 hover:underline">Case {l.case_id}</Link> },
    { key: "kind", header: "Kind", render: (l) => <span className="text-ink-700">{CASE_LANES[l.lane]?.label ?? l.lane}</span> },
    { key: "verdict", header: "Outcome of the case", render: (l) => <span className="text-ink-800">{CASE_VERDICTS[l.verdict] ?? l.verdict}</span> },
    { key: "label", header: "Counts as", render: (l) => <Badge tone={OUTCOME[l.label]?.tone ?? "neutral"}>{OUTCOME[l.label]?.label ?? l.label}</Badge> },
  ];

  if (error) return <div><PageHeader crumbs={[{ label: "Integrity" }, { label: "Signal governance" }]} title="Signal governance" /><ErrorBlock message={error} onRetry={load} /></div>;
  const checked = all.filter((r) => r.labeled >= MIN_CHECKED).length;
  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Integrity" }, { label: "Signal governance" }]}
        title="Signal governance"
        subtitle="How reliable each finding has proved on closed cases, and what should change as a result. A finding earns its weight: it is scored only once enough closed cases bear it out."
      />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Closed cases with an outcome" value={labels ? labels.length : "…"} hint="What everything here is measured from" />
        <Stat label="Findings with enough evidence" value={rows ? `${checked} of ${all.length}` : "…"} hint={`Checked on ${MIN_CHECKED} or more closed cases`} />
        <Stat label="Suggested changes" value={rows ? changes.length : "…"} tone={changes.length ? "warn" : undefined} />
        <Stat label="Risky claims the engine catches" value={recall?.recall_floor != null ? `At least ${pct(recall.recall_floor)}` : "Not measured"} hint={recall ? `${recall.reviewed} cleared claims re-checked` : undefined} />
      </div>
      <Tabs<Tab>
        tabs={[{ key: "findings", label: "Findings", count: rows ? all.length : undefined }, { key: "changes", label: "Suggested changes", count: rows ? changes.length : undefined }, { key: "missed", label: "What the engine misses" }, { key: "outcomes", label: "Case outcomes", count: labels?.length }]}
        value={tab} onChange={(k) => reset(k === "findings" ? {} : { tab: k })}
      />

      <div className="mt-4">
        {tab === "findings" && (
          <>
            <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-4">
              <Input className="sm:col-span-2" placeholder="Finding or code" aria-label="Search findings" value={value("q")} onChange={(e) => set({ q: e.target.value })} />
              <Select aria-label="Show" value={value("show")} onChange={(e) => set({ show: e.target.value })}>
                <option value="">All findings</option><option value="fired">Raised at least once</option><option value="checked">With enough evidence</option><option value="change">With a suggested change</option>
              </Select>
              {(value("q") || value("show")) && <div className="flex items-center"><Button size="sm" variant="ghost" icon={X} onClick={() => set({ q: null, show: null })}>Clear filters</Button></div>}
            </div>
            <DataTable
              columns={columns} rows={shown} rowKey={(r) => r.signal} loading={rows === null}
              empty={<EmptyState title="No finding matches" body="Change or clear the filters." />}
              footer={<span className="text-[13px] text-ink-500">{shown.length} of {all.length} findings. "Borne out" counts closed cases where the outcome was fraud confirmed, payment adjusted or referred to legal.</span>}
            />
          </>
        )}

        {tab === "changes" && (
          <>
            <div className="mb-3 rounded-lg border border-info-line bg-info-bg px-4 py-3 text-sm text-info-fg">
              A finding is suggested for scoring once we can be confident that at least 60% of the cases it was raised on bore it out. One that falls short is suggested for advisory. Findings set by law are always scored and never appear here.
              {!isAdmin && " An administrator applies a change."}
            </div>
            <DataTable columns={changeColumns} rows={changes} rowKey={(r) => r.signal} loading={rows === null} empty={<EmptyState title="Nothing to change" body="Every finding is in the mode its record supports." />} />
          </>
        )}

        {tab === "missed" && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Cleared claims re-checked" value={recall ? recall.reviewed : "…"} hint="Reviewed blind and closed" />
              <Stat label="Found to be wrong" value={recall ? recall.misses : "…"} tone={recall?.misses ? "bad" : undefined} hint="Cleared by the engine, but a problem was found" />
              <Stat label="Miss rate" value={recall ? pct(recall.miss_rate) : "…"} hint={recall?.miss_rate_wilson_upper != null ? `Could be as high as ${pct(recall.miss_rate_wilson_upper)}` : "Needs re-checked claims"} />
              <Stat label="Caught, at least" value={recall?.recall_floor != null ? pct(recall.recall_floor) : "Not measured"} tone={recall?.recall_floor != null ? "ok" : undefined} />
            </div>
            <Panel
              title="Quality checks" description="To learn what the engine misses, a spread of claims it cleared automatically is reviewed blind by a claims handler. The reviewer's outcome is the measure."
              actions={<Button variant="primary" onClick={() => { setFormError(null); setDrawing(true); }}>Open quality checks</Button>}
            >
              <p className="text-sm text-ink-700">{sample ? `${sample.population} claims are cleared automatically at present. A draw spreads evenly across them and skips any claim that already has an open review.` : "Loading"}</p>
              <p className="mt-2 text-[13px] text-ink-500">Each check opens as a billing-review case in <Link to="/cases?view=unassigned" className="text-brand-700 hover:underline">Cases</Link>. Close it with an honest outcome: that outcome is what these figures are built from.</p>
            </Panel>
          </div>
        )}

        {tab === "outcomes" && (
          <DataTable
            columns={labelColumns} rows={labels ?? []} rowKey={(l) => String(l.case_id)} loading={labels === null}
            empty={<EmptyState title="No closed case has an outcome yet" body="Outcomes appear as cases linked to a claim are closed." />}
            footer={<div className="flex flex-wrap items-center justify-between gap-3"><span className="text-[13px] text-ink-500">{labels?.length ?? 0} closed cases. Fraud confirmed, payment adjusted and referred to legal count as the finding being right; cleared and no action count as a false alarm.</span><a href="/api/governance/labels.csv" className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong bg-white px-2.5 text-[13px] font-medium text-ink-800 hover:bg-ink-50"><Download size={14} aria-hidden /> Download</a></div>}
          />
        )}
      </div>

      <ConfirmDialog
        open={applying !== null} onClose={() => setApplying(null)} busy={busy}
        title={applying ? `Move ${reasonLabel(applying.signal)} to ${SIGNAL_MODES[applying.recommended_mode]?.label.toLowerCase() ?? applying.recommended_mode}?` : ""}
        description={formError ?? (applying ? `${SIGNAL_MODES[applying.recommended_mode]?.help ?? ""} Applies to claims assessed from now on.` : undefined)}
        confirmLabel="Apply change" reason={{ label: "Reason", required: true, placeholder: "For example: borne out on 12 of 14 closed cases" }}
        onConfirm={apply}
      />
      <Dialog
        open={drawing} onClose={() => setDrawing(false)} title="Open quality checks" description="Opens a billing-review case for each sampled claim, at low priority."
        footer={<><Button onClick={() => setDrawing(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={draw}>Open cases</Button></>}
      >
        <div className="space-y-3">
          <Field label="How many claims" required hint="1 to 200."><Input type="number" min={1} max={200} value={drawN} onChange={(e) => setDrawN(e.target.value)} /></Field>
          {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
        </div>
      </Dialog>
    </div>
  );
}
