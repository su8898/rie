// Intelligence — party fraud analytics (read-only, any logged-in user).
//
// Five section tabs over the /api/parties/* endpoints:
//   Providers  — sortable cohort table + per-row component breakdown expander.
//   Attorneys  — cohort table with claim-type mix + late-lodgement share.
//   Claimants  — recurrence (a token appearing across >= 2 accidents).
//   Fairness   — disparate-impact by cohort + the four-fifths ratio + pass/fail.
//   Risk sweep — threshold input -> flagged parties across providers/attorneys.
//
// Scores are cohort-relative and n-guarded: confidence "LOW_N" means too few
// claims to score (shown as a muted "low-n" tag, score suppressed). A mostly
// clean corpus scoring LOW everywhere is expected, not an error.

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../api";
import {
  Bar,
  Card,
  CodePill,
  Empty,
  ErrorBox,
  Loading,
  LowNTag,
  Pagination,
  RatingChip,
  SearchInput,
  matchQ,
  usePaged,
} from "../components/ui";
import { num, rand } from "../format";
import type {
  Attorney,
  Fairness,
  Claimant,
  Provider,
  RiskSweep,
} from "../types";

type Tab = "providers" | "attorneys" | "claimants" | "fairness" | "sweep";

const TABS: { key: Tab; label: string }[] = [
  { key: "providers", label: "Providers" },
  { key: "attorneys", label: "Attorneys" },
  { key: "claimants", label: "Claimants" },
  { key: "fairness", label: "Fairness" },
  { key: "sweep", label: "Risk sweep" },
];

export default function IntelligencePage() {
  const [tab, setTab] = useState<Tab>("providers");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Intelligence</h1>
        <span className="text-xs text-slate-400">
          party fraud analytics · cohort-relative, n-guarded
        </span>
      </div>

      {/* Section tabs */}
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${
              tab === t.key
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "providers" && <ProvidersTab />}
      {tab === "attorneys" && <AttorneysTab />}
      {tab === "claimants" && <ClaimantsTab />}
      {tab === "fairness" && <FairnessTab />}
      {tab === "sweep" && <SweepTab />}
    </div>
  );
}

// Generic fetch hook for a read-only endpoint.
function useFetch<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps);
  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    run()
      .then((d) => alive && setData(d))
      .catch((e) =>
        alive && setError(e instanceof ApiError ? e.message : "Failed to load"),
      );
    return () => {
      alive = false;
    };
  }, [run]);
  return { data, error };
}

const th =
  "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";

// ── Providers ────────────────────────────────────────────────────────────────
type ProvSort = "score" | "avg_value" | "n_claims" | "flag_rate";

function ProvidersTab() {
  const { data, error } = useFetch<Provider[]>(() => api.providers());
  const [sort, setSort] = useState<ProvSort>("score");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [q, setQ] = useState("");

  const rows = useMemo(() => {
    if (!data) return null;
    return [...data]
      .sort((a, b) => b[sort] - a[sort])
      .filter((p) => matchQ(q, p.provider_id, p.archetype, p.rating));
  }, [data, sort, q]);

  const { page, setPage, pageCount, total, slice } = usePaged(rows ?? [], 20);

  if (error) return <ErrorBox message={error} />;
  if (data === null) return <Loading label="Scoring providers…" />;
  if (data.length === 0)
    return <Empty label="No providers in the corpus yet." />;

  const SortHead = ({ k, label, align = "left" }: { k: ProvSort; label: string; align?: string }) => (
    <th className={`${th} ${align === "right" ? "text-right" : "text-left"}`}>
      <button
        onClick={() => setSort(k)}
        className={`transition hover:text-slate-800 ${sort === k ? "text-slate-900" : ""}`}
      >
        {label}
        {sort === k ? " ↓" : ""}
      </button>
    </th>
  );

  return (
    <div className="space-y-3">
      <SearchInput
        value={q}
        onChange={setQ}
        placeholder="Search provider, cohort, rating…"
      />
      {total === 0 ? (
        <Empty label="No providers match your search." />
      ) : (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className={th} />
              <th className={`${th} text-left`}>Provider</th>
              <th className={`${th} text-left`}>Cohort</th>
              <SortHead k="n_claims" label="Claims" align="right" />
              <SortHead k="avg_value" label="Avg value" align="right" />
              <th className={`${th} text-left`}>Value pct</th>
              <SortHead k="flag_rate" label="Flag %" align="right" />
              <SortHead k="score" label="Score" align="right" />
              <th className={`${th} text-left`}>Rating</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {slice.map((p) => {
              const open = expanded === p.provider_id;
              const lowN = p.confidence === "LOW_N";
              return (
                <Fragment key={p.provider_id}>
                  <tr
                    className="cursor-pointer hover:bg-slate-50"
                    onClick={() =>
                      setExpanded(open ? null : p.provider_id)
                    }
                  >
                    <td className="px-3 py-2 text-slate-400">
                      {open ? "▾" : "▸"}
                    </td>
                    <td className="px-3 py-2 font-mono text-[13px] text-slate-900">
                      {p.provider_id}
                    </td>
                    <td className="px-3 py-2">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                        {p.archetype}
                      </span>
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {num(p.n_claims)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {rand(p.avg_value)}
                    </td>
                    <td className="px-3 py-2">
                      <Bar value={p.value_percentile} />
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {p.flag_rate}%
                    </td>
                    <td className="tnum px-3 py-2 text-right font-semibold text-slate-900">
                      {lowN ? "—" : p.score}
                    </td>
                    <td className="px-3 py-2">
                      {lowN ? <LowNTag /> : <RatingChip rating={p.rating} />}
                    </td>
                  </tr>
                  {open && (
                    <tr className="bg-slate-50/60">
                      <td />
                      <td colSpan={8} className="px-3 py-3">
                        <ComponentBars components={p.components} />
                        <div className="mt-2 text-[11px] text-slate-400">
                          {num(p.n_lines)} lines · {rand(p.billed)} billed ·
                          red rate {p.red_rate}%
                          {lowN && " · below robust-n threshold (score suppressed)"}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pagination
        page={page}
        pageCount={pageCount}
        total={total}
        onPage={setPage}
        unit="providers"
      />
    </div>
      )}
    </div>
  );
}

function ComponentBars({
  components,
}: {
  components: Provider["components"];
}) {
  const entries: [string, number][] = [
    ["behavioural", components.behavioural],
    ["cohort_outlier", components.cohort_outlier],
    ["over_servicing", components.over_servicing],
    ["history", components.history],
  ];
  return (
    <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
      {entries.map(([k, v]) => (
        <div key={k} className="flex items-center gap-3">
          <span className="w-32 text-[11px] text-slate-500">
            {k.replace(/_/g, " ")}
          </span>
          <Bar value={v} tone="score" width="w-32" />
        </div>
      ))}
    </div>
  );
}

// ── Attorneys ────────────────────────────────────────────────────────────────
function AttorneysTab() {
  const { data, error } = useFetch<Attorney[]>(() => api.attorneys());
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () => (data ?? []).filter((a) => matchQ(q, a.attorney, a.cohort, a.rating)),
    [data, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 20);
  if (error) return <ErrorBox message={error} />;
  if (data === null) return <Loading label="Scoring attorneys…" />;
  if (data.length === 0)
    return (
      <Empty label="No attorney-attributed claims in the corpus yet." />
    );

  return (
    <div className="space-y-3">
      <SearchInput
        value={q}
        onChange={setQ}
        placeholder="Search attorney, cohort, rating…"
      />
      {total === 0 ? (
        <Empty label="No attorneys match your search." />
      ) : (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className={`${th} text-left`}>Attorney</th>
              <th className={`${th} text-left`}>Cohort</th>
              <th className={`${th} text-right`}>Claims</th>
              <th className={`${th} text-left`}>Claim-type mix</th>
              <th className={`${th} text-right`}>Late lodgement</th>
              <th className={`${th} text-right`}>Score</th>
              <th className={`${th} text-left`}>Rating</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {slice.map((a) => {
              const lowN = a.confidence === "LOW_N";
              return (
                <tr key={a.attorney} className="hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono text-[13px] text-slate-900">
                    {a.attorney}
                  </td>
                  <td className="px-3 py-2">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                      {a.cohort}
                    </span>
                  </td>
                  <td className="tnum px-3 py-2 text-right text-slate-700">
                    {num(a.n_claims)}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(a.claim_type_mix).map(([t, n]) => (
                        <span
                          key={t}
                          className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600"
                        >
                          {t} ·{" "}
                          <span className="tnum font-medium">{n}</span>
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="tnum px-3 py-2 text-right text-slate-700">
                    {a.late_lodgement_share}%
                  </td>
                  <td className="tnum px-3 py-2 text-right font-semibold text-slate-900">
                    {lowN ? "—" : a.score}
                  </td>
                  <td className="px-3 py-2">
                    {lowN ? <LowNTag /> : <RatingChip rating={a.rating} />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pagination
        page={page}
        pageCount={pageCount}
        total={total}
        onPage={setPage}
        unit="attorneys"
      />
    </div>
      )}
    </div>
  );
}

// ── Claimants (recurrence) ───────────────────────────────────────────────────
function ClaimantsTab() {
  const { data, error } = useFetch<Claimant[]>(() => api.claimants());
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () =>
      (data ?? []).filter((c) =>
        matchQ(q, c.party_token, c.accidents.join(" ")),
      ),
    [data, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 25);
  if (error) return <ErrorBox message={error} />;
  if (data === null) return <Loading label="Scanning recurrence…" />;
  if (data.length === 0)
    return (
      <Empty label="No recurring claimants (no token spans two or more accidents)." />
    );

  return (
    <div className="space-y-3">
      <SearchInput
        value={q}
        onChange={setQ}
        placeholder="Search party token or accident id…"
      />
      {total === 0 ? (
        <Empty label="No claimants match your search." />
      ) : (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            <th className={`${th} text-left`}>Party token</th>
            <th className={`${th} text-right`}>Accidents</th>
            <th className={`${th} text-left`}>Accident ids</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {slice.map((c) => (
            <tr key={c.party_token} className="hover:bg-slate-50">
              <td className="px-3 py-2 font-mono text-[13px] text-slate-900">
                {c.party_token}
              </td>
              <td className="tnum px-3 py-2 text-right font-semibold text-slate-800">
                {c.n_accidents}
              </td>
              <td className="px-3 py-2">
                <div className="flex flex-wrap gap-1">
                  {c.accidents.map((id) => (
                    <CodePill key={id}>{id}</CodePill>
                  ))}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <Pagination
        page={page}
        pageCount={pageCount}
        total={total}
        onPage={setPage}
        unit="claimants"
      />
    </div>
      )}
    </div>
  );
}

// ── Fairness ─────────────────────────────────────────────────────────────────
function FairnessTab() {
  const { data, error } = useFetch<Fairness>(() => api.fairness());
  if (error) return <ErrorBox message={error} />;
  if (data === null) return <Loading label="Computing disparate impact…" />;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <Card title="Flag rate by cohort">
          {data.by_cohort.length === 0 ? (
            <div className="text-sm text-slate-400">No cohorts yet.</div>
          ) : (
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead>
                <tr>
                  <th className={`${th} text-left`}>Cohort</th>
                  <th className={`${th} text-right`}>Claims</th>
                  <th className={`${th} text-left`}>Flag rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.by_cohort.map((c) => (
                  <tr key={c.cohort}>
                    <td className="px-3 py-2">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                        {c.cohort}
                      </span>
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {num(c.n_claims)}
                    </td>
                    <td className="px-3 py-2">
                      <Bar value={c.flag_rate} width="w-40" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <Card title="Four-fifths ratio">
        <div className="flex flex-col items-center py-4">
          <div className="tnum text-5xl font-bold text-slate-900">
            {data.four_fifths_ratio.toFixed(2)}
          </div>
          <div className="mt-3">
            {data.pass ? (
              <span className="inline-flex items-center rounded-md bg-emerald-100 px-3 py-1 text-sm font-semibold text-emerald-800 ring-1 ring-inset ring-emerald-600/20">
                PASS · ≥ 0.80
              </span>
            ) : (
              <span className="inline-flex items-center rounded-md bg-rose-100 px-3 py-1 text-sm font-semibold text-rose-800 ring-1 ring-inset ring-rose-600/20">
                FAIL · &lt; 0.80
              </span>
            )}
          </div>
          <p className="mt-3 text-center text-[11px] leading-relaxed text-slate-400">
            Min ÷ max cohort flag rate. The 4/5ths rule flags disparate impact
            below 0.80.
          </p>
        </div>
      </Card>
    </div>
  );
}

// ── Risk sweep ───────────────────────────────────────────────────────────────
function SweepTab() {
  const [threshold, setThreshold] = useState(55);
  const [result, setResult] = useState<RiskSweep | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { page, setPage, pageCount, total, slice } = usePaged(
    result?.flagged ?? [],
    25,
  );

  const runSweep = useCallback((t: number) => {
    setBusy(true);
    setError(null);
    api
      .riskSweep(t)
      .then((r) => setResult(r))
      .catch((e) =>
        setError(e instanceof ApiError ? e.message : "Sweep failed"),
      )
      .finally(() => setBusy(false));
  }, []);

  // Run once on mount at the default threshold.
  useEffect(() => {
    runSweep(55);
  }, [runSweep]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="w-32">
          <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Score threshold
          </label>
          <input
            type="number"
            min={0}
            max={100}
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
          />
        </div>
        <button
          onClick={() => runSweep(threshold)}
          disabled={busy}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40"
        >
          {busy ? "Sweeping…" : "Run sweep"}
        </button>
        {result && (
          <span className="text-sm text-slate-500">
            <span className="tnum font-semibold text-slate-800">
              {result.n}
            </span>{" "}
            part{result.n === 1 ? "y" : "ies"} at/above{" "}
            {result.threshold}
          </span>
        )}
      </div>

      {error ? (
        <ErrorBox message={error} />
      ) : !result ? (
        <Loading label="Running sweep…" />
      ) : result.flagged.length === 0 ? (
        <Empty label="No parties at or above the threshold — a clean sweep." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className={`${th} text-left`}>Type</th>
                <th className={`${th} text-left`}>Party</th>
                <th className={`${th} text-right`}>Claims</th>
                <th className={`${th} text-right`}>Score</th>
                <th className={`${th} text-left`}>Rating</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {slice.map((f) => (
                <tr key={`${f.type}:${f.id}`} className="hover:bg-slate-50">
                  <td className="px-3 py-2">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                      {f.type}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-[13px] text-slate-900">
                    {f.id}
                  </td>
                  <td className="tnum px-3 py-2 text-right text-slate-700">
                    {num(f.n_claims)}
                  </td>
                  <td className="tnum px-3 py-2 text-right font-semibold text-slate-900">
                    {f.score}
                  </td>
                  <td className="px-3 py-2">
                    <RatingChip rating={f.rating} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination
            page={page}
            pageCount={pageCount}
            total={total}
            onPage={setPage}
            unit="flagged"
          />
        </div>
      )}
    </div>
  );
}
