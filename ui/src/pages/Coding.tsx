// Coding intelligence — billing behaviour read against the reference (domain-logic §11).
//
// The pricing rule is payable = min(billed, reference); this page aggregates that
// per code and per condition, then reads the gap:
//   • Codes       — the leakage map per tariff/NAPPI code: billed vs payable, the
//     repricing saving captured over an ENFORCEABLE/ACCEPTED reference, the
//     over-reference SIGNAL where billing sits above an INTERDICTED/ENDOGENOUS
//     source, and uncovered spend with no reference to price against (§11 decomposition).
//   • Negotiation targets — the codes where a negotiated ENFORCEABLE rate would
//     control currently-uncaptured spend; potential saving is the lever (§5).
//   • Conditions  — per-claimant medical totals by ICD-10 3-char injury class, the
//     p25–p90 band under the MIN_ROBUST small-n guard, plus an estimate tool that
//     classifies an amount against the band (§6).
//
// Read-only (three GET aggregations + one GET estimate); no mutations.

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import {
  Card,
  CodePill,
  Empty,
  ErrorBox,
  Loading,
  LowNTag,
  Pagination,
  SearchInput,
  Toast,
  matchQ,
  usePaged,
} from "../components/ui";
import { num, rand } from "../format";
import type { CodeAgg, ConditionRow, CostEstimate, DriftReport } from "../types";

type Tab = "codes" | "targets" | "conditions" | "drift";
type CodeKind = "" | "TARIFF" | "NAPPI";

const th =
  "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";

const INPUT =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const PRIMARY_BTN =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40";

// classification → chip palette for the estimate result.
const CLASS_STYLE: Record<string, string> = {
  BELOW_TYPICAL: "bg-slate-100 text-slate-700 ring-slate-500/20",
  TYPICAL: "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
  HIGH: "bg-amber-100 text-amber-800 ring-amber-600/20",
  OUTLIER: "bg-rose-100 text-rose-800 ring-rose-600/20",
  UNKNOWN: "bg-slate-100 text-slate-600 ring-slate-500/20",
};

export default function CodingPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("codes");

  const [codes, setCodes] = useState<CodeAgg[] | null>(null);
  const [targets, setTargets] = useState<CodeAgg[] | null>(null);
  const [conditions, setConditions] = useState<ConditionRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // CODES tab kind filter (re-loads codingCodes on change).
  const [kind, setKind] = useState<CodeKind>("");

  // Estimate tool (CONDITIONS tab).
  const [estClass, setEstClass] = useState("");
  const [estAmount, setEstAmount] = useState("");
  const [estimate, setEstimate] = useState<CostEstimate | null>(null);
  const [estimating, setEstimating] = useState(false);

  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const [c, t, cond] = await Promise.all([
        api.codingCodes(kind || undefined),
        api.negotiationTargets(),
        api.conditions(),
      ]);
      setCodes(c);
      setTargets(t);
      setConditions(cond);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load coding intelligence.");
    }
  }, [kind]);

  useEffect(() => {
    void load();
  }, [load]);

  async function runEstimate() {
    const amount = Number(estAmount);
    if (!estClass.trim() || !isFinite(amount)) {
      setToast("Enter an injury class and a numeric amount.");
      return;
    }
    setEstimating(true);
    try {
      const res = await api.estimateCondition(estClass.trim(), amount);
      setEstimate(res);
    } catch (e) {
      setToast(e instanceof ApiError ? e.message : "Estimate failed.");
    } finally {
      setEstimating(false);
    }
  }

  const loading = codes === null || targets === null || conditions === null;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Coding intelligence</h1>
        <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
          Where billing behaviour is read against the reference. Payable ={" "}
          min(billed, reference), so the gap between billed and reference is
          captured leakage and a negotiation lever: repricing saving over an
          enforceable rate, an over-reference{" "}
          <span className="font-medium text-slate-600">signal</span> where an
          interdicted source is billed above, and{" "}
          <span className="font-medium text-slate-600">uncovered</span> spend
          with no reference to price against. Condition cost bands benchmark
          per-injury spend (§11, §6).
        </p>
      </header>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {(
          [
            ["codes", "Codes"],
            ["targets", "Negotiation targets"],
            ["conditions", "Conditions"],
            ["drift", "Price drift"],
          ] as [Tab, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${
              tab === value
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {loadError ? (
        <ErrorBox message={loadError} />
      ) : loading ? (
        <Loading />
      ) : tab === "codes" ? (
        <CodesTab codes={codes} kind={kind} onKind={setKind} />
      ) : tab === "targets" ? (
        <TargetsTab targets={targets} />
      ) : tab === "drift" ? (
        <DriftTab />
      ) : (
        <ConditionsTab
          rows={conditions}
          estClass={estClass}
          estAmount={estAmount}
          estimate={estimate}
          estimating={estimating}
          onEstClass={setEstClass}
          onEstAmount={setEstAmount}
          onRun={runEstimate}
          note={user?.role === "ADMIN" ? "Admin view — bands are read-only here." : null}
        />
      )}

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}

// ── Codes ────────────────────────────────────────────────────────────────────
function CodesTab({
  codes,
  kind,
  onKind,
}: {
  codes: CodeAgg[];
  kind: CodeKind;
  onKind: (k: CodeKind) => void;
}) {
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () => codes.filter((r) => matchQ(q, r.code, r.kind)),
    [codes, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 25);
  return (
    <Card
      title="Codes — the leakage map"
      sub="One row per tariff/NAPPI code: how much it moves (lines / claims / providers), billed vs payable = min(billed, reference), and where the gap goes — repriced saving already captured over an enforceable reference, the over-reference signal (billed above an interdicted/endogenous source, amber when live), and uncovered spend with no reference to price against (§11 decomposition). Src is the reference source most lines priced against."
      right={
        <div className="flex items-end gap-2">
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Kind
            </label>
            <select
              value={kind}
              onChange={(e) => onKind(e.target.value as CodeKind)}
              className={INPUT}
              aria-label="Filter by code kind"
            >
              <option value="">All kinds</option>
              <option value="TARIFF">TARIFF</option>
              <option value="NAPPI">NAPPI</option>
            </select>
          </div>
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Search
            </label>
            <SearchInput
              value={q}
              onChange={setQ}
              placeholder="Search code…"
              className="w-44"
            />
          </div>
        </div>
      }
    >
      {filtered.length === 0 ? (
        <Empty label={q || kind ? "No codes match the current filter." : "No codes."} />
      ) : (
        <div className="overflow-hidden rounded-md border border-slate-100">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>Kind</th>
                  <th className={`${th} text-left`}>Code</th>
                  <th className={`${th} text-right`}>Lines</th>
                  <th className={`${th} text-right`}>Claims</th>
                  <th className={`${th} text-right`}>Providers</th>
                  <th className={`${th} text-right`}>Billed</th>
                  <th className={`${th} text-right`}>Payable</th>
                  <th className={`${th} text-right`}>Repriced saving</th>
                  <th className={`${th} text-right`}>Over-ref signal</th>
                  <th className={`${th} text-right`}>Uncovered</th>
                  <th className={`${th} text-left`}>Src</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((r) => (
                  <tr key={`${r.kind}:${r.code}`} className="hover:bg-slate-50">
                    <td className="px-3 py-2 text-slate-500">{r.kind}</td>
                    <td className="px-3 py-2">
                      <CodePill>{r.code}</CodePill>
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {num(r.n_lines)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {num(r.n_claims)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {num(r.n_providers)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {rand(r.billed)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {rand(r.payable)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {rand(r.repricing_captured)}
                    </td>
                    <td
                      className={`tnum px-3 py-2 text-right ${
                        r.over_reference_signal > 0 ? "text-amber-700" : "text-slate-700"
                      }`}
                    >
                      {rand(r.over_reference_signal)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-500">
                      {rand(r.uncovered_billed)}
                    </td>
                    <td className="px-3 py-2 text-slate-500">{r.top_src ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            pageCount={pageCount}
            total={total}
            onPage={setPage}
            unit="codes"
          />
        </div>
      )}
    </Card>
  );
}

// ── Negotiation targets ──────────────────────────────────────────────────────
function TargetsTab({ targets }: { targets: CodeAgg[] }) {
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () => targets.filter((r) => matchQ(q, r.code, r.kind)),
    [targets, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 25);
  return (
    <Card
      title="Negotiation targets — where a rate would bite"
      sub="Codes where today there is no enforceable reference to price against, so the spend can't be repriced at adjudication — the over-reference signal (billed above an interdicted/endogenous source) plus uncovered lines. A negotiated ENFORCEABLE rate would let the pay-min rule capture it; potential saving is that lever, ranked highest-first (§5)."
      right={
        <SearchInput
          value={q}
          onChange={setQ}
          placeholder="Search code…"
          className="w-44"
        />
      }
    >
      {filtered.length === 0 ? (
        <Empty
          label={
            q
              ? "No targets match your search."
              : "No negotiation targets — everything is benchmarked or already negotiated."
          }
        />
      ) : (
        <div className="overflow-hidden rounded-md border border-slate-100">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>Code</th>
                  <th className={`${th} text-right`}>Lines</th>
                  <th className={`${th} text-right`}>Providers</th>
                  <th className={`${th} text-right`}>Over-ref signal</th>
                  <th className={`${th} text-right`}>Uncovered</th>
                  <th className={`${th} text-right`}>Potential saving</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((r) => (
                  <tr key={`${r.kind}:${r.code}`} className="hover:bg-slate-50">
                    <td className="px-3 py-2">
                      <CodePill>{r.code}</CodePill>
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {num(r.n_lines)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {num(r.n_providers)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {rand(r.over_reference_signal)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {rand(r.uncovered_billed)}
                    </td>
                    <td className="tnum px-3 py-2 text-right font-semibold text-slate-900">
                      {rand(r.potential_saving ?? 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            pageCount={pageCount}
            total={total}
            onPage={setPage}
            unit="targets"
          />
        </div>
      )}
    </Card>
  );
}

// ── Conditions ───────────────────────────────────────────────────────────────
function ConditionsTab({
  rows,
  estClass,
  estAmount,
  estimate,
  estimating,
  onEstClass,
  onEstAmount,
  onRun,
  note,
}: {
  rows: ConditionRow[];
  estClass: string;
  estAmount: string;
  estimate: CostEstimate | null;
  estimating: boolean;
  onEstClass: (v: string) => void;
  onEstAmount: (v: string) => void;
  onRun: () => void;
  note: string | null;
}) {
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () => rows.filter((r) => matchQ(q, r.injury_class)),
    [rows, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 25);
  return (
    <div className="space-y-4">
      <Card
        title="Estimate against a band"
        sub="Enter an ICD-10 3-char injury class and a rand amount to classify it against that class's per-claimant medical band: BELOW_TYPICAL / TYPICAL / HIGH / OUTLIER, or UNKNOWN when the class is below MIN_ROBUST and has no published band. A quick check on whether a claimant's medical total sits inside the benchmark (§6)."
      >
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-slate-500">Injury class</label>
            <input
              value={estClass}
              onChange={(e) => onEstClass(e.target.value)}
              placeholder="e.g. S72"
              className={INPUT}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-slate-500">Amount (R)</label>
            <input
              type="number"
              value={estAmount}
              onChange={(e) => onEstAmount(e.target.value)}
              placeholder="0"
              className={`${INPUT} tnum w-40`}
            />
          </div>
          <button onClick={onRun} disabled={estimating} className={PRIMARY_BTN}>
            {estimating ? "Estimating…" : "Estimate"}
          </button>

          {estimate && (
            <div className="flex items-center gap-2 pb-0.5">
              <span
                className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${
                  CLASS_STYLE[estimate.classification] ??
                  "bg-slate-100 text-slate-600 ring-slate-500/20"
                }`}
              >
                {estimate.classification}
              </span>
              <span className="text-xs text-slate-500">
                {estimate.injury_class} · n={num(estimate.n)}
                {estimate.robust && estimate.bands
                  ? ` · ${rand(estimate.bands.p25)}–${rand(estimate.bands.p90)}`
                  : ""}
              </span>
            </div>
          )}
        </div>
        {note && <div className="mt-2 text-xs text-slate-400">{note}</div>}
      </Card>

      <Card
        title="Condition cost bands"
        sub="Per-claimant medical totals summed by ICD-10 3-char injury class, then reduced to percentiles: p25–p90 is the typical spread, with the full range beside it. A class needs ≥MIN_ROBUST (20) claimants before a band is published — below that it shows low-n and no percentiles, guarding against reading a benchmark off too few claims (§6)."
        right={
          <SearchInput
            value={q}
            onChange={setQ}
            placeholder="Search injury class…"
            className="w-52"
          />
        }
      >
        {filtered.length === 0 ? (
          <Empty label={q ? "No conditions match your search." : "No conditions."} />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className={`${th} text-left`}>Injury class</th>
                    <th className={`${th} text-right`}>n</th>
                    <th className={`${th} text-right`}>p25</th>
                    <th className={`${th} text-right`}>p50</th>
                    <th className={`${th} text-right`}>p75</th>
                    <th className={`${th} text-right`}>p90</th>
                    <th className={`${th} text-right`}>Range</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {slice.map((r) => (
                    <tr key={r.injury_class} className="hover:bg-slate-50">
                      <td className="px-3 py-2 font-medium text-slate-800">
                        {r.injury_class}
                      </td>
                      <td className="tnum px-3 py-2 text-right text-slate-700">
                        <span className="inline-flex items-center gap-1.5">
                          {num(r.n)}
                          {!r.robust && <LowNTag />}
                        </span>
                      </td>
                      <td className="tnum px-3 py-2 text-right text-slate-700">
                        {r.bands ? rand(r.bands.p25) : "—"}
                      </td>
                      <td className="tnum px-3 py-2 text-right text-slate-700">
                        {r.bands ? rand(r.bands.p50) : "—"}
                      </td>
                      <td className="tnum px-3 py-2 text-right text-slate-700">
                        {r.bands ? rand(r.bands.p75) : "—"}
                      </td>
                      <td className="tnum px-3 py-2 text-right text-slate-700">
                        {r.bands ? rand(r.bands.p90) : "—"}
                      </td>
                      <td className="tnum px-3 py-2 text-right text-slate-500">
                        {r.bands ? `${rand(r.bands.min)}–${rand(r.bands.max)}` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={page}
              pageCount={pageCount}
              total={total}
              onPage={setPage}
              unit="conditions"
            />
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Price drift ──────────────────────────────────────────────────────────────
// Per provider per service month: billed ÷ reference on the lines that have an
// enforceable or accepted reference, and the trend of that ratio. Each line's
// reference is the one in force on its service date, so a tariff increase does
// not read as drift. A worklist for a human look, never a verdict.
function DriftTab() {
  const [report, setReport] = useState<DriftReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .priceDrift()
      .then(setReport)
      .catch((e) => setError(e instanceof ApiError ? e.message : "Failed to load price drift."));
  }, []);

  if (error) return <ErrorBox message={error} />;
  if (report === null) return <Loading />;
  return (
    <Card
      title="Price drift — providers whose billing is ratcheting up"
      sub={`Providers with at least ${report.min_months} months of history (months with fewer than ${report.min_lines} priced lines are ignored), ranked by the monthly rise in billed ÷ reference. ${report.n_providers} provider${report.n_providers === 1 ? " has" : "s have"} enough history to judge.`}
    >
      {report.rising.length === 0 ? (
        <Empty label="No provider shows a rising trend on enough history." />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">Provider</th>
                <th className="px-3 py-2">Months</th>
                <th className="px-3 py-2">Period</th>
                <th className="px-3 py-2 text-right">First ratio</th>
                <th className="px-3 py-2 text-right">Last ratio</th>
                <th className="px-3 py-2 text-right">Rise per month</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {report.rising.map((r) => (
                <tr key={r.provider_id}>
                  <td className="px-3 py-2">
                    <CodePill>{r.provider_id}</CodePill>
                  </td>
                  <td className="px-3 py-2 tabular-nums text-slate-600">{r.n_months}</td>
                  <td className="px-3 py-2 text-slate-600">
                    {r.first_month} to {r.last_month}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">
                    {r.first_ratio.toFixed(2)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-800">
                    {r.last_ratio.toFixed(2)}
                  </td>
                  <td className="px-3 py-2 text-right font-medium tabular-nums text-rose-700">
                    +{r.slope_per_month.toFixed(3)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
