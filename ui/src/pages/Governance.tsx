import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Card,
  Stat,
  Loading,
  ErrorBox,
  Empty,
  ModeChip,
  MaturityChip,
  CodePill,
  Bar,
  Pagination,
  SearchInput,
  matchQ,
  usePaged,
} from "../components/ui";
import { num } from "../format";
import type { PrecisionRow, RecallEstimate, LabelRow } from "../types";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";

const th =
  "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";

function ActionPill({ action }: { action?: "PROMOTE" | "DEMOTE" }) {
  const tone =
    action === "PROMOTE"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
      : action === "DEMOTE"
        ? "bg-amber-50 text-amber-700 ring-amber-600/20"
        : "bg-slate-50 text-slate-600 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${tone}`}
    >
      {action ?? "—"}
    </span>
  );
}

function LabelPill({ label }: { label: string }) {
  const up = label.toUpperCase();
  const tone =
    up === "ADVERSE"
      ? "bg-rose-50 text-rose-700 ring-rose-600/20"
      : up === "BENIGN"
        ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
        : "bg-slate-50 text-slate-600 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${tone}`}
    >
      {label}
    </span>
  );
}

export default function GovernancePage() {
  useAuth();
  const [precision, setPrecision] = useState<PrecisionRow[] | null>(null);
  const [promotions, setPromotions] = useState<PrecisionRow[] | null>(null);
  const [recall, setRecall] = useState<RecallEstimate | null>(null);
  const [labels, setLabels] = useState<LabelRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, pr, rc, lb] = await Promise.all([
        api.precision(),
        api.promotions(),
        api.recall(),
        api.labels(),
      ]);
      setPrecision(p);
      setPromotions(pr);
      setRecall(rc);
      setLabels(lb);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const [precQ, setPrecQ] = useState("");
  const [labelQ, setLabelQ] = useState("");
  const precisionSorted = useMemo(
    () =>
      [...(precision ?? [])]
        .sort((a, b) => b.labeled - a.labeled)
        .filter((r) =>
          matchQ(precQ, r.signal, r.maturity, r.current_mode, r.recommended_mode),
        ),
    [precision, precQ],
  );
  const labelsFiltered = useMemo(
    () =>
      (labels ?? []).filter((r) =>
        matchQ(labelQ, r.claim_id, r.verdict, r.label, r.lane),
      ),
    [labels, labelQ],
  );
  const precPg = usePaged(precisionSorted, 20);
  const labelsPg = usePaged(labelsFiltered, 25);

  if (loadError) return <ErrorBox message={loadError} />;
  if (
    precision === null ||
    promotions === null ||
    recall === null ||
    labels === null
  )
    return <Loading />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Governance</h1>
        <span className="text-xs text-slate-400">
          precision / recall · signal promotion lifecycle
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Reviewed" value={num(recall.reviewed)} />
        <Stat label="Misses" value={num(recall.misses)} />
        <Stat
          label="Miss rate"
          value={`${((recall.miss_rate ?? 0) * 100).toFixed(1)}%`}
        />
        <Stat
          label="Recall floor"
          value={`${((recall.recall_floor ?? 0) * 100).toFixed(1)}%`}
          accent="text-emerald-600"
          sub="1 − Wilson-upper of the miss rate"
        />
      </div>

      <Card title="Promotion action list">
        {promotions.length === 0 ? (
          <Empty label="No signal-mode changes recommended." />
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr>
                    <th className={th}>Signal</th>
                    <th className={th}>Action</th>
                    <th className={th}>Mode</th>
                    <th className={`${th} text-right`}>Substantiation</th>
                    <th className={`${th} text-right`}>Wilson-lower</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {promotions.map((r) => (
                    <tr key={r.signal}>
                      <td className="px-3 py-2">
                        <CodePill>{r.signal}</CodePill>
                      </td>
                      <td className="px-3 py-2">
                        <ActionPill action={r.action} />
                      </td>
                      <td className="px-3 py-2">
                        <span className="inline-flex items-center gap-1">
                          <ModeChip mode={r.current_mode} />
                          <span className="text-slate-400">→</span>
                          <ModeChip mode={r.recommended_mode} />
                        </span>
                      </td>
                      <td className="tnum px-3 py-2 text-right">
                        {`${((r.substantiation ?? 0) * 100).toFixed(0)}%`}
                      </td>
                      <td className="tnum px-3 py-2 text-right">
                        {`${((r.wilson_lower ?? 0) * 100).toFixed(1)}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        <p className="mt-2 text-xs text-slate-400">
          Act on these in Admin → Signal modes (an override is an audit-logged
          reference-data edit).
        </p>
      </Card>

      <Card title="Precision by signal">
        <div className="mb-2">
          <SearchInput
            value={precQ}
            onChange={setPrecQ}
            placeholder="Search signal…"
          />
        </div>
        {precPg.total === 0 ? (
          <Empty label={precQ ? "No signals match your search." : "No signals labeled yet."} />
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr>
                    <th className={th}>Signal</th>
                    <th className={th}>Maturity</th>
                    <th className={th}>Current</th>
                    <th className={th}>Recommended</th>
                    <th className={`${th} text-right`}>Fired</th>
                    <th className={`${th} text-right`}>Labeled</th>
                    <th className={th}>Substantiation</th>
                    <th className={`${th} text-right`}>Wilson [lo, hi]</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {precPg.slice.map((r) => (
                    <tr key={r.signal}>
                      <td className="px-3 py-2">
                        <CodePill>{r.signal}</CodePill>
                      </td>
                      <td className="px-3 py-2">
                        <MaturityChip maturity={r.maturity ?? ""} />
                      </td>
                      <td className="px-3 py-2">
                        <ModeChip mode={r.current_mode} />
                      </td>
                      <td className="px-3 py-2">
                        <ModeChip mode={r.recommended_mode} />
                      </td>
                      <td className="tnum px-3 py-2 text-right">
                        {num(r.fired)}
                      </td>
                      <td className="tnum px-3 py-2 text-right">
                        {num(r.labeled)}
                      </td>
                      <td className="px-3 py-2">
                        {r.labeled === 0 ? (
                          <span className="text-slate-400">—</span>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className="tnum w-10 text-right">
                              {`${((r.substantiation ?? 0) * 100).toFixed(0)}%`}
                            </span>
                            <Bar
                              value={(r.substantiation ?? 0) * 100}
                              tone="score"
                            />
                          </div>
                        )}
                      </td>
                      <td className="tnum px-3 py-2 text-right">
                        {`[${((r.wilson_lower ?? 0) * 100).toFixed(0)}, ${((r.wilson_upper ?? 0) * 100).toFixed(0)}]`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={precPg.page}
              pageCount={precPg.pageCount}
              total={precPg.total}
              onPage={precPg.setPage}
              unit="signals"
            />
          </div>
        )}
      </Card>

      <Card title="Recent labels (ground truth)">
        <div className="mb-2">
          <SearchInput
            value={labelQ}
            onChange={setLabelQ}
            placeholder="Search claim, verdict, label, lane…"
          />
        </div>
        {labelsPg.total === 0 ? (
          <Empty label={labelQ ? "No labels match your search." : "No closed-case labels yet."} />
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr>
                    <th className={th}>Claim</th>
                    <th className={th}>Verdict</th>
                    <th className={th}>Label</th>
                    <th className={th}>Lane</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {labelsPg.slice.map((r) => (
                    <tr key={`${r.case_id}-${r.claim_id}`}>
                      <td className="px-3 py-2">
                        <Link
                          to={`/claims/${encodeURIComponent(r.claim_id)}`}
                          className="font-mono text-[13px] text-slate-900 hover:text-blue-600 hover:underline"
                        >
                          {r.claim_id}
                        </Link>
                      </td>
                      <td className="px-3 py-2 text-slate-700">{r.verdict}</td>
                      <td className="px-3 py-2">
                        <LabelPill label={r.label} />
                      </td>
                      <td className="px-3 py-2 text-slate-700">{r.lane}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={labelsPg.page}
              pageCount={labelsPg.pageCount}
              total={labelsPg.total}
              onPage={labelsPg.setPage}
              unit="labels"
            />
          </div>
        )}
      </Card>
    </div>
  );
}
