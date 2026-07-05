// Coding intelligence: tariff/NAPPI code aggregation, negotiation targets, and
// per-condition medical cost bands with an on-demand estimate tool. Read-only
// (three GET aggregations + one GET estimate); no mutations.

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
import type { CodeAgg, ConditionRow, CostEstimate } from "../types";

type Tab = "codes" | "targets" | "conditions";
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
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Coding intelligence</h1>
        <span className="text-xs text-slate-400">
          tariff/NAPPI overage · condition cost bands · negotiation targets
        </span>
      </div>

      <div className="flex gap-2">
        {(
          [
            ["codes", "Codes"],
            ["targets", "Negotiation targets"],
            ["conditions", "Conditions"],
          ] as [Tab, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={
              tab === value
                ? "rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white"
                : "rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
            }
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
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs font-medium text-slate-500">Kind</label>
        <select
          value={kind}
          onChange={(e) => onKind(e.target.value as CodeKind)}
          className={INPUT}
        >
          <option value="">All</option>
          <option value="TARIFF">TARIFF</option>
          <option value="NAPPI">NAPPI</option>
        </select>
        <SearchInput value={q} onChange={setQ} placeholder="Search code…" />
      </div>

      {filtered.length === 0 ? (
        <Empty label={q ? "No codes match your search." : "No codes."} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={th}>Kind</th>
                  <th className={th}>Code</th>
                  <th className={`${th} text-right`}>Lines</th>
                  <th className={`${th} text-right`}>Claims</th>
                  <th className={`${th} text-right`}>Providers</th>
                  <th className={`${th} text-right`}>Billed</th>
                  <th className={`${th} text-right`}>Payable</th>
                  <th className={`${th} text-right`}>Repriced saving</th>
                  <th className={`${th} text-right`}>Over-ref signal</th>
                  <th className={`${th} text-right`}>Uncovered</th>
                  <th className={th}>Src</th>
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
    </div>
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
    <div className="space-y-3">
      <p className="text-sm text-slate-500">
        Codes where a negotiated ENFORCEABLE rate would control currently-uncaptured
        spend (over-reference signal + uncovered).
      </p>
      <SearchInput value={q} onChange={setQ} placeholder="Search code…" />
      {filtered.length === 0 ? (
        <Empty
          label={
            q
              ? "No targets match your search."
              : "No negotiation targets — everything is benchmarked or already negotiated."
          }
        />
      ) : (
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className={th}>Code</th>
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
    </div>
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
    <div className="space-y-3">
      <Card title="Estimate">
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

      <SearchInput value={q} onChange={setQ} placeholder="Search injury class…" />
      {filtered.length === 0 ? (
        <Empty label={q ? "No conditions match your search." : "No conditions."} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={th}>Injury class</th>
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

      <p className="text-xs text-slate-400">
        Per-claimant medical totals by ICD-10 3-char class; a band needs ≥20
        authorities (MIN_ROBUST).
      </p>
    </div>
  );
}
