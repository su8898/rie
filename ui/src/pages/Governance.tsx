// Governance — prove the system is fair, measured, and defensible (domain-logic §11).
//
// Three tabs, each backed by a real workflow, not just a read-out:
//   • Signal health — precision by signal (does a signal earn its SCORED weight?),
//     recall (what the engine misses) with a "Draw QA reviews" action that opens
//     blind-review Cases, and a promotion action list an ADMIN can Apply in place.
//   • Fairness      — disparate impact by provider cohort: the impact ratio on
//     BOTH tails, review flags, and the four-fifths headline gauge.
//   • Ground truth  — the closed-case labels every number is measured against,
//     exportable as CSV, plus the measurement basis (the §11 constants).

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import {
  Bar,
  Card,
  CodePill,
  Empty,
  ErrorBox,
  Loading,
  MaturityChip,
  ModeChip,
  Pagination,
  SearchInput,
  Toast,
  matchQ,
  usePaged,
} from "../components/ui";
import { num } from "../format";
import type {
  Fairness,
  LabelRow,
  PrecisionRow,
  RecallEstimate,
  RecallSample,
} from "../types";

type Tab = "signals" | "fairness" | "labels";

const TABS: { key: Tab; label: string }[] = [
  { key: "signals", label: "Signal health" },
  { key: "fairness", label: "Fairness" },
  { key: "labels", label: "Ground truth" },
];

const th =
  "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";

// 0–1 proportion → "62%"; 0–100 rate → "6.2%".
const pctP = (x: number | null | undefined) =>
  x == null ? "—" : `${(x * 100).toFixed(0)}%`;
const pctR = (x: number | null | undefined) =>
  x == null ? "—" : `${x.toFixed(1)}%`;

interface ToastState {
  message: string;
  tone: "error" | "success";
}

export default function GovernancePage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";

  const [tab, setTab] = useState<Tab>("signals");
  const [precision, setPrecision] = useState<PrecisionRow[] | null>(null);
  const [promotions, setPromotions] = useState<PrecisionRow[] | null>(null);
  const [recall, setRecall] = useState<RecallEstimate | null>(null);
  const [sample, setSample] = useState<RecallSample | null>(null);
  const [labels, setLabels] = useState<LabelRow[] | null>(null);
  const [fairness, setFairness] = useState<Fairness | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [drawN, setDrawN] = useState(30);
  const [toast, setToast] = useState<ToastState | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, pr, rc, sm, lb, fa] = await Promise.all([
        api.precision(),
        api.promotions(),
        api.recall(),
        api.recallSample(30),
        api.labels(),
        api.fairness(),
      ]);
      setPrecision(p);
      setPromotions(pr);
      setRecall(rc);
      setSample(sm);
      setLabels(lb);
      setFairness(fa);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = useCallback(
    (
      key: string,
      fn: () => Promise<unknown>,
      okMsg: string | ((result: unknown) => string),
    ) => {
      if (busyKey !== null) return;
      setBusyKey(key);
      fn()
        .then(async (result) => {
          await load();
          setToast({
            message: typeof okMsg === "function" ? okMsg(result) : okMsg,
            tone: "success",
          });
        })
        .catch((e) =>
          setToast({
            message: e instanceof ApiError ? e.message : "Request failed.",
            tone: "error",
          }),
        )
        .finally(() => setBusyKey(null));
    },
    [busyKey, load],
  );

  const loading =
    precision === null ||
    promotions === null ||
    recall === null ||
    labels === null ||
    fairness === null;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Governance</h1>
        <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
          Fair, measured, defensible. Precision, recall and disparate impact are
          measured against closed-case ground truth — asserted by nothing, earned
          by evidence (domain-logic §11).
        </p>
      </header>

      {loadError && <ErrorBox message={loadError} />}

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

      {loading ? (
        <Loading label="Measuring…" />
      ) : tab === "signals" ? (
        <SignalHealth
          precision={precision}
          promotions={promotions}
          recall={recall}
          sample={sample}
          isAdmin={isAdmin}
          busyKey={busyKey}
          drawN={drawN}
          setDrawN={setDrawN}
          run={run}
        />
      ) : tab === "fairness" ? (
        <FairnessTab fairness={fairness} />
      ) : (
        <GroundTruth labels={labels} recall={recall} />
      )}

      {toast && (
        <Toast
          message={toast.message}
          tone={toast.tone}
          onClose={() => setToast(null)}
        />
      )}
    </div>
  );
}

// ── Signal health ────────────────────────────────────────────────────────────
function SignalHealth({
  precision,
  promotions,
  recall,
  sample,
  isAdmin,
  busyKey,
  drawN,
  setDrawN,
  run,
}: {
  precision: PrecisionRow[];
  promotions: PrecisionRow[];
  recall: RecallEstimate;
  sample: RecallSample | null;
  isAdmin: boolean;
  busyKey: string | null;
  drawN: number;
  setDrawN: (n: number) => void;
  run: (
    key: string,
    fn: () => Promise<unknown>,
    okMsg: string | ((result: unknown) => string),
  ) => void;
}) {
  const [q, setQ] = useState("");
  const rows = useMemo(
    () =>
      [...precision]
        .sort((a, b) => b.labeled - a.labeled)
        .filter((r) => matchQ(q, r.signal, r.category, r.maturity)),
    [precision, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(rows, 15);

  return (
    <div className="space-y-4">
      {/* Recall */}
      <Card
        title="Recall — what the engine misses"
        sub="Auto-cleared GREEN claims reviewed blind: a substantiated outcome is a measured false negative. The recall floor is a conservative 1 − Wilson-upper of that miss rate — a promise the true recall is at least this high."
        right={
          <div className="flex items-end gap-2">
            <div>
              <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
                sample
              </label>
              <input
                type="number"
                min={1}
                max={200}
                value={drawN}
                onChange={(e) => setDrawN(Number(e.target.value))}
                className="tnum w-20 rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
              />
            </div>
            <button
              onClick={() =>
                run(
                  "draw",
                  () =>
                    api.drawQaReviews(drawN).then((r) => {
                      if (r.drawn === 0)
                        throw new ApiError(
                          409,
                          `Nothing drawn — all ${r.sampled} sampled claims already have an open review.`,
                          null,
                        );
                      return r;
                    }),
                  (r) =>
                    `${(r as { drawn: number }).drawn} QA review(s) opened into Cases (REVIEW lane).`,
                )
              }
              disabled={busyKey !== null}
              className="rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40"
            >
              {busyKey === "draw" ? "Drawing…" : "Draw QA reviews"}
            </button>
          </div>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
              Recall floor
            </div>
            <div className="tnum mt-0.5 text-2xl font-bold text-emerald-800">
              {pctP(recall.recall_floor)}
            </div>
            <p className="mt-1 text-xs text-emerald-800/80">
              1 − Wilson-upper of the miss rate — the conservative lower bound on
              how much the engine catches.
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 p-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Miss rate
            </div>
            <div className="tnum mt-0.5 text-2xl font-bold text-slate-800">
              {pctP(recall.miss_rate)}
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {num(recall.misses)} of {num(recall.reviewed)} reviewed GREEN claims
              later found adverse · Wilson upper {pctP(recall.miss_rate_wilson_upper)}
            </p>
          </div>
        </div>
        {sample && (
          <p className="mt-3 text-xs text-slate-400">
            Pool: {num(sample.population)} auto-cleared GREEN claims. A draw spreads
            a deterministic blind sample into the Cases REVIEW lane; each closed
            verdict becomes ground truth that tightens this estimate.
          </p>
        )}
      </Card>

      {/* Promotion action list */}
      <Card
        title="Promotion action list"
        sub="Signals whose measured mode differs from where they sit today. Applying is an audit-logged, effective-dated reference-data edit — never a code deploy (§11). Grounded, law-cited signals are always SCORED and never appear here."
      >
        {promotions.length === 0 ? (
          <Empty label="No changes recommended — every signal sits where the evidence puts it." />
        ) : (
          <div className="overflow-x-auto rounded-md border border-slate-100">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>Signal</th>
                  <th className={`${th} text-left`}>Action</th>
                  <th className={`${th} text-left`}>Change</th>
                  <th className={`${th} text-right`}>Substantiation</th>
                  <th className={`${th} text-right`}>Wilson-lower</th>
                  <th className={`${th} text-left`}>Apply</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {promotions.map((r) => (
                  <tr key={r.signal} className="hover:bg-slate-50">
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
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {pctP(r.substantiation)}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {pctP(r.wilson_lower)}
                    </td>
                    <td className="px-3 py-2">
                      {isAdmin ? (
                        <button
                          onClick={() =>
                            run(
                              `apply.${r.signal}`,
                              () =>
                                api.setSignalMode({
                                  code: r.signal,
                                  mode: r.recommended_mode,
                                  note: "applied from governance action list",
                                }),
                              `${r.signal} → ${r.recommended_mode}.`,
                            )
                          }
                          disabled={busyKey !== null}
                          className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-100 disabled:opacity-40"
                        >
                          {busyKey === `apply.${r.signal}`
                            ? "…"
                            : `Set ${r.recommended_mode}`}
                        </button>
                      ) : (
                        <span className="text-[11px] text-slate-400">
                          ADMIN applies
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Precision by signal */}
      <Card
        title="Precision by signal"
        sub={`${num(precision.length)} signals over the labelled corpus. A signal earns SCORED weight only when its Wilson-lower substantiation clears the 60% floor (§11); maturity is the basis grade from the reason register. Precision below 50% is flagged.`}
        right={
          <SearchInput
            value={q}
            onChange={setQ}
            placeholder="Search signal…"
            className="w-52"
          />
        }
      >
        {total === 0 ? (
          <Empty label={q ? "No signals match your search." : "No signals labelled yet."} />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className={`${th} text-left`}>Signal</th>
                    <th className={`${th} text-left`}>Maturity</th>
                    <th className={`${th} text-left`}>Mode</th>
                    <th className={`${th} text-right`}>Fired</th>
                    <th className={`${th} text-right`}>Labelled</th>
                    <th className={`${th} text-right`}>Substantiated</th>
                    <th className={`${th} text-left`}>Precision</th>
                    <th className={`${th} text-right`}>Wilson [lo, hi]</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {slice.map((r) => {
                    const weak =
                      r.substantiation != null && r.substantiation < 0.5;
                    return (
                      <tr key={r.signal} className="align-top hover:bg-slate-50">
                        <td className="px-3 py-2">
                          <CodePill>{r.signal}</CodePill>
                          {r.category && (
                            <div className="mt-0.5 text-[10px] uppercase tracking-wide text-slate-400">
                              {r.category}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <MaturityChip maturity={r.maturity ?? ""} />
                        </td>
                        <td className="px-3 py-2">
                          <span className="inline-flex items-center gap-1">
                            <ModeChip mode={r.current_mode} />
                            {r.recommended_mode !== r.current_mode && (
                              <>
                                <span className="text-slate-300">→</span>
                                <ModeChip mode={r.recommended_mode} />
                              </>
                            )}
                          </span>
                        </td>
                        <td className="tnum px-3 py-2 text-right text-slate-600">
                          {num(r.fired)}
                        </td>
                        <td className="tnum px-3 py-2 text-right text-slate-600">
                          {num(r.labeled)}
                        </td>
                        <td className="tnum px-3 py-2 text-right text-slate-600">
                          {num(r.substantiated)}
                        </td>
                        <td className="px-3 py-2">
                          {r.labeled === 0 ? (
                            <span className="text-slate-400">—</span>
                          ) : (
                            <div className="flex items-center gap-2">
                              <span
                                className={`tnum w-9 text-right ${weak ? "font-semibold text-rose-600" : "text-slate-700"}`}
                              >
                                {pctP(r.substantiation)}
                              </span>
                              <Bar
                                value={(r.substantiation ?? 0) * 100}
                                tone="score"
                              />
                            </div>
                          )}
                        </td>
                        <td className="tnum px-3 py-2 text-right text-slate-500">
                          [{pctP(r.wilson_lower)}, {pctP(r.wilson_upper)}]
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
              unit="signals"
            />
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Fairness ─────────────────────────────────────────────────────────────────
function FairnessTab({ fairness }: { fairness: Fairness }) {
  const lo = fairness.impact_low ?? 0.8;
  const hi = fairness.impact_high ?? 1.25;
  const min = fairness.min_group ?? 5;
  const reviewCount = fairness.by_cohort.filter((c) => c.review).length;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <Card
          title="Disparate impact — provider cohort"
          sub={`impact = cohort flag rate ÷ overall (${pctR(fairness.overall_flag_rate)}); a cohort with ≥${min} claims whose impact falls outside [${lo}, ${hi}] is flagged for review. A question, not a verdict — and BOTH tails matter: under-scrutiny is where bad actors hide.`}
        >
          <div className="overflow-x-auto rounded-md border border-slate-100">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>Cohort</th>
                  <th className={`${th} text-right`}>Claims</th>
                  <th className={`${th} text-left`}>Flag rate</th>
                  <th className={`${th} text-right`}>Impact</th>
                  <th className={`${th} text-left`}></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {fairness.by_cohort.map((c) => (
                  <tr
                    key={c.cohort}
                    className={`hover:bg-slate-50 ${c.small ? "opacity-50" : ""}`}
                  >
                    <td className="px-3 py-2">
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
                        {c.cohort}
                      </span>
                      {c.small && (
                        <span className="ml-1.5 text-[10px] text-slate-400">
                          small-n
                        </span>
                      )}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-600">
                      {num(c.n_claims)}
                    </td>
                    <td className="px-3 py-2">
                      <Bar value={c.flag_rate} width="w-32" />
                    </td>
                    <td className="tnum px-3 py-2 text-right">
                      {c.impact == null ? (
                        <span className="text-slate-300">—</span>
                      ) : (
                        <span
                          className={
                            c.review
                              ? "rounded bg-amber-100 px-1.5 font-semibold text-amber-800"
                              : c.small
                                ? "text-slate-400"
                                : "text-slate-700"
                          }
                        >
                          {c.impact.toFixed(2)}×
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {c.review && (
                        <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
                          review
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            {reviewCount === 0
              ? "No cohort is outside the impact band — impact is even across cohorts."
              : `${reviewCount} cohort${reviewCount === 1 ? "" : "s"} flagged for review.`}
          </p>
        </Card>
      </div>

      <Card
        title="Four-fifths ratio"
        sub="min ÷ max cohort flag rate; the 4/5ths rule flags disparate impact below 0.80."
      >
        <div className="flex flex-col items-center py-4">
          <div className="tnum text-5xl font-bold text-slate-900">
            {fairness.four_fifths_ratio.toFixed(2)}
          </div>
          <div className="mt-3">
            {fairness.pass ? (
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
            A headline gauge only — the impact table beside it is the finer,
            two-tailed instrument.
          </p>
        </div>
      </Card>
    </div>
  );
}

// ── Ground truth ─────────────────────────────────────────────────────────────
function GroundTruth({
  labels,
  recall,
}: {
  labels: LabelRow[];
  recall: RecallEstimate;
}) {
  const [q, setQ] = useState("");
  const rows = useMemo(
    () =>
      labels.filter((r) =>
        matchQ(q, r.claim_id, r.verdict, r.label, r.lane, `#${r.case_id}`),
      ),
    [labels, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(rows, 25);

  return (
    <div className="space-y-4">
      <Card
        title="Closed-case labels"
        sub="One row per closed-case verdict — the ground truth precision and recall are measured against. Adverse = the signal was right (confirmed fraud / adjusted / referred); benign = a false positive (cleared / no action)."
        right={
          <a
            href="/api/governance/labels.csv"
            download
            className="rounded-md border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
          >
            Export CSV
          </a>
        }
      >
        <div className="mb-3">
          <SearchInput
            value={q}
            onChange={setQ}
            placeholder="Search claim, verdict, lane, #case…"
          />
        </div>
        {total === 0 ? (
          <Empty label={q ? "No labels match your search." : "No closed-case labels yet."} />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className={`${th} text-left`}>Claim</th>
                    <th className={`${th} text-left`}>Verdict</th>
                    <th className={`${th} text-left`}>Label</th>
                    <th className={`${th} text-left`}>Lane</th>
                    <th className={`${th} text-right`}>Case</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {slice.map((r) => (
                    <tr key={`${r.case_id}-${r.claim_id}`} className="hover:bg-slate-50">
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
                        <LabelBadge label={r.label} />
                      </td>
                      <td className="px-3 py-2 text-slate-600">{r.lane}</td>
                      <td className="tnum px-3 py-2 text-right text-slate-400">
                        #{r.case_id}
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
              unit="labels"
            />
          </div>
        )}
      </Card>

      <Card
        title="Measurement basis"
        sub="The constants every number on this page is computed against — stable, spec-cited, and the same in the engine and here (§11)."
      >
        <dl className="grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
          <Basis
            k="SCORED promotion floor"
            v="Wilson-lower substantiation ≥ 60%"
            note="A signal is only allowed to score points once its measured precision clears this floor; below it, it stays ADVISORY."
          />
          <Basis
            k="Minimum labels to judge"
            v="5 closed-case labels"
            note="Fewer than five and a signal's mode is held — too little evidence to promote or demote."
          />
          <Basis
            k="Adverse verdicts"
            v="CONFIRMED_FRAUD · ADJUSTED · REFERRED_LEGAL"
            note="The signal was right — counts toward substantiation and toward a recall miss on a GREEN claim."
          />
          <Basis
            k="Benign verdicts"
            v="CLEARED · NO_ACTION"
            note="A false positive — the signal fired but the claim was clean."
          />
          <Basis
            k="Recall floor"
            v="1 − Wilson-upper(miss rate)"
            note={`Measured over ${num(recall.reviewed)} reviewed GREEN claims; conservative by construction.`}
          />
          <Basis
            k="Grounded signals"
            v="always SCORED, floor-exempt"
            note="Law-cited hard gates are not subject to the measured-precision floor."
          />
        </dl>
      </Card>
    </div>
  );
}

function Basis({ k, v, note }: { k: string; v: string; note: string }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {k}
      </dt>
      <dd className="mt-0.5 text-sm font-medium text-slate-800">{v}</dd>
      <dd className="mt-0.5 text-xs leading-relaxed text-slate-500">{note}</dd>
    </div>
  );
}

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

function LabelBadge({ label }: { label: string }) {
  const up = label.toUpperCase();
  const tone =
    up === "ADVERSE"
      ? "bg-rose-50 text-rose-700 ring-rose-600/20"
      : up === "BENIGN"
        ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
        : "bg-slate-100 text-slate-600 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${tone}`}
    >
      {label}
    </span>
  );
}
