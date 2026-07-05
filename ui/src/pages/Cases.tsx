// Cases — the investigation / review case machine.
//
// Top: analytics cards (open / at-stake / recovered / prevented) plus by-lane
// and by-status breakdowns. A filter row (lane + status) re-queries the list.
// An "Open case" inline form creates a REVIEW / BLOCK / CLAWBACK case. The
// table drives each case through its state machine via `item.actions`
// (assign / escalate / close): assign and escalate are one-click, close opens
// an inline verdict form.
//
// The backend is authoritative: it owns role gating (REVIEW → HANDLER,
// BLOCK/CLAWBACK → INVESTIGATOR) and legal transitions, so we don't pre-block
// beyond disabling in-flight buttons — its 403/409 {detail} is surfaced
// verbatim via Toast. Analytics + list re-fetch on every success.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import {
  Card,
  Empty,
  ErrorBox,
  Loading,
  Pagination,
  SearchInput,
  Stat,
  StateChip,
  Toast,
  matchQ,
  usePaged,
} from "../components/ui";
import { rand } from "../format";
import type {
  CaseAnalytics,
  CaseItem,
  CaseLane,
  CaseVerdict,
} from "../types";

const LANES: CaseLane[] = ["REVIEW", "BLOCK", "CLAWBACK"];
const STATUSES = ["OPEN", "IN_REVIEW", "ESCALATED", "CLOSED"] as const;
const VERDICTS: CaseVerdict[] = [
  "CONFIRMED_FRAUD",
  "CLEARED",
  "ADJUSTED",
  "NO_ACTION",
  "REFERRED_LEGAL",
];
const PRIORITIES = [1, 2, 3, 4, 5] as const;
// Priority → SLA days (mirrors the backend ladder).
const SLA_DAYS: Record<number, number> = { 1: 1, 2: 3, 3: 7, 4: 10, 5: 14 };

const th =
  "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";
const inputCls =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const primaryBtn =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed";
const smallBtn =
  "rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40";

interface ToastState {
  message: string;
  tone: "error" | "success";
}

export default function CasesPage() {
  const { user } = useAuth();

  const [analytics, setAnalytics] = useState<CaseAnalytics | null>(null);
  const [cases, setCases] = useState<CaseItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [laneFilter, setLaneFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [closeFor, setCloseFor] = useState<number | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);

  // Open-case form.
  const [newLane, setNewLane] = useState<CaseLane>("REVIEW");
  const [newReason, setNewReason] = useState("");
  const [newPriority, setNewPriority] = useState(3);
  const [newStake, setNewStake] = useState("0");
  const [newClaimId, setNewClaimId] = useState("");

  const load = useCallback(async (lane: string, status: string) => {
    try {
      const [a, c] = await Promise.all([
        api.caseAnalytics(),
        api.cases({
          lane: lane || undefined,
          status: status || undefined,
        }),
      ]);
      setAnalytics(a);
      setCases(c);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load.");
    }
  }, []);

  useEffect(() => {
    void load(laneFilter, statusFilter);
  }, [load, laneFilter, statusFilter]);

  // Action runner: disable in-flight, refetch analytics + list on success,
  // surface backend {detail} on failure, always clear busyKey.
  const run = useCallback(
    (key: string, fn: () => Promise<unknown>, okMsg: string) => {
      if (busyKey !== null) return;
      setBusyKey(key);
      fn()
        .then(async () => {
          await load(laneFilter, statusFilter);
          setToast({ message: okMsg, tone: "success" });
        })
        .catch((e) =>
          setToast({
            message: e instanceof ApiError ? e.message : "Request failed.",
            tone: "error",
          }),
        )
        .finally(() => setBusyKey(null));
    },
    [busyKey, load, laneFilter, statusFilter],
  );

  function openCase() {
    run(
      "open",
      () =>
        api.openCase({
          lane: newLane,
          reason: newReason,
          claim_id: newClaimId.trim() ? newClaimId.trim() : undefined,
          priority: newPriority,
          rand_at_stake: Number(newStake) || 0,
        }),
      "Case opened.",
    );
    // Optimistically reset the reason/claim fields; a failure keeps the Toast
    // visible so the operator can re-enter.
    setNewReason("");
    setNewClaimId("");
  }

  const anyInFlight = busyKey !== null;
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () =>
      (cases ?? []).filter((c) =>
        matchQ(q, c.claim_id, c.assigned_to, c.lane, c.status, c.verdict, `#${c.id}`),
      ),
    [cases, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 20);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Cases</h1>
        <span className="text-xs text-slate-400">
          investigation / review case machine
        </span>
      </div>

      {loadError && <ErrorBox message={loadError} />}

      {/* Analytics */}
      {analytics && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Open" value={analytics.open} />
            <Stat label="At stake" value={rand(analytics.rand_at_stake_open)} />
            <Stat
              label="Recovered"
              value={rand(analytics.rand_recovered)}
              accent="text-emerald-600"
            />
            <Stat label="Prevented" value={rand(analytics.rand_prevented)} />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Card title="By lane">
              <Chips map={analytics.by_lane} empty="No cases." />
            </Card>
            <Card title="By status">
              <Chips map={analytics.by_status} empty="No cases." />
            </Card>
          </div>
        </>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Lane
          </label>
          <select
            value={laneFilter}
            onChange={(e) => setLaneFilter(e.target.value)}
            className={inputCls}
            aria-label="Filter by lane"
          >
            <option value="">All</option>
            {LANES.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Status
          </label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className={inputCls}
            aria-label="Filter by status"
          >
            <option value="">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
        <div className="min-w-[16rem] flex-1">
          <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Search
          </label>
          <SearchInput
            value={q}
            onChange={setQ}
            placeholder="Claim, assignee, verdict, #id…"
            className="w-full"
          />
        </div>
      </div>

      {/* Open case */}
      <Card title="Open case">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Lane
            </label>
            <select
              value={newLane}
              onChange={(e) => setNewLane(e.target.value as CaseLane)}
              className={inputCls}
            >
              {LANES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-[16rem] flex-1">
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Reason
            </label>
            <input
              type="text"
              value={newReason}
              onChange={(e) => setNewReason(e.target.value)}
              placeholder="Why open this case?"
              className={`${inputCls} w-full`}
            />
          </div>
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Priority
            </label>
            <select
              value={newPriority}
              onChange={(e) => setNewPriority(Number(e.target.value))}
              className={inputCls}
            >
              {PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  P{p} · {SLA_DAYS[p]}-day SLA
                </option>
              ))}
            </select>
          </div>
          <div className="w-32">
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Rand at stake
            </label>
            <input
              type="number"
              min={0}
              value={newStake}
              onChange={(e) => setNewStake(e.target.value)}
              className={`${inputCls} tnum w-full`}
            />
          </div>
          <div className="w-40">
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Claim ID (optional)
            </label>
            <input
              type="text"
              value={newClaimId}
              onChange={(e) => setNewClaimId(e.target.value)}
              placeholder="—"
              className={`${inputCls} w-full`}
            />
          </div>
          <button
            onClick={openCase}
            disabled={anyInFlight || !newReason.trim()}
            className={primaryBtn}
          >
            {busyKey === "open" ? "Opening…" : "Open case"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          REVIEW is owned by HANDLER; BLOCK/CLAWBACK by INVESTIGATOR. Signed in
          as {user?.username} ({user?.role}).
        </p>
      </Card>

      {/* Table */}
      {cases === null ? (
        <Loading label="Loading cases…" />
      ) : filtered.length === 0 ? (
        <Empty label={q ? "No cases match your search." : "No cases match — open one above."} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>#</th>
                  <th className={`${th} text-left`}>Claim</th>
                  <th className={`${th} text-left`}>Lane</th>
                  <th className={`${th} text-left`}>Status</th>
                  <th className={`${th} text-left`}>Priority / SLA</th>
                  <th className={`${th} text-right`}>At stake</th>
                  <th className={`${th} text-left`}>Assigned</th>
                  <th className={`${th} text-left`}>Verdict</th>
                  <th className={`${th} text-left`}>Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((c) => (
                  <tr key={c.id} className="align-top hover:bg-slate-50">
                    <td className="px-3 py-2 text-xs text-slate-400">
                      #{c.id}
                    </td>
                    <td className="px-3 py-2">
                      {c.claim_id ? (
                        <Link
                          to={`/claims/${encodeURIComponent(c.claim_id)}`}
                          className="font-mono text-[13px] text-slate-900 hover:text-blue-600 hover:underline"
                        >
                          {c.claim_id}
                        </Link>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <StateChip state={c.lane} />
                    </td>
                    <td className="px-3 py-2">
                      <StateChip state={c.status} />
                    </td>
                    <td className="px-3 py-2 text-xs">
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold text-slate-700">
                          P{c.priority}
                        </span>
                        {c.sla_days != null && (
                          <span className="text-slate-400">
                            {c.sla_days}d SLA
                          </span>
                        )}
                      </div>
                      {c.overdue ? (
                        <span className="mt-0.5 inline-flex items-center rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold text-rose-700 ring-1 ring-inset ring-rose-600/20">
                          overdue
                        </span>
                      ) : c.days_to_sla != null ? (
                        <span className="mt-0.5 inline-block text-[10px] text-slate-400">
                          {c.days_to_sla}d left
                        </span>
                      ) : null}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {rand(c.rand_at_stake)}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-600">
                      {c.assigned_to ?? (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {c.verdict ? (
                        <StateChip state={c.verdict} />
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <RowActions
                        item={c}
                        busyKey={busyKey}
                        closeOpen={closeFor === c.id}
                        openClose={() => setCloseFor(c.id)}
                        cancelClose={() => setCloseFor(null)}
                        run={run}
                      />
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
            unit="cases"
          />
        </div>
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

// Small label + count chips for a Record<string, number> breakdown.
function Chips({
  map,
  empty,
}: {
  map: Record<string, number>;
  empty: string;
}) {
  const entries = Object.entries(map);
  if (entries.length === 0)
    return <div className="text-sm text-slate-400">{empty}</div>;
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([k, v]) => (
        <span
          key={k}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs"
        >
          <span className="text-slate-500">{k.replace(/_/g, " ")}</span>
          <span className="tnum font-semibold text-slate-800">{v}</span>
        </span>
      ))}
    </div>
  );
}

// Per-row actions driven by `item.actions` (subset of assign / escalate /
// close). assign + escalate are one-click; close opens an inline verdict form.
function RowActions({
  item,
  busyKey,
  closeOpen,
  openClose,
  cancelClose,
  run,
}: {
  item: CaseItem;
  busyKey: string | null;
  closeOpen: boolean;
  openClose: () => void;
  cancelClose: () => void;
  run: (key: string, fn: () => Promise<unknown>, okMsg: string) => void;
}) {
  const [verdict, setVerdict] = useState<CaseVerdict>("CONFIRMED_FRAUD");
  const [rootCause, setRootCause] = useState("");
  const [recovered, setRecovered] = useState("0");
  const [prevented, setPrevented] = useState("0");
  const anyInFlight = busyKey !== null;

  if (item.actions.length === 0) {
    return <span className="text-[11px] text-slate-300">—</span>;
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {item.actions.includes("assign") && (
          <button
            onClick={() =>
              run(
                `case.${item.id}.assign`,
                () => api.caseAction(item.id, "assign"),
                "Case assigned.",
              )
            }
            disabled={anyInFlight}
            className={smallBtn}
          >
            {busyKey === `case.${item.id}.assign` ? "…" : "assign"}
          </button>
        )}
        {item.actions.includes("escalate") && (
          <button
            onClick={() =>
              run(
                `case.${item.id}.escalate`,
                () => api.caseAction(item.id, "escalate"),
                "Case escalated.",
              )
            }
            disabled={anyInFlight}
            className={smallBtn}
          >
            {busyKey === `case.${item.id}.escalate` ? "…" : "escalate"}
          </button>
        )}
        {item.actions.includes("close") && (
          <button
            onClick={openClose}
            disabled={anyInFlight}
            className={smallBtn}
          >
            close
          </button>
        )}
      </div>

      {/* Close inline form */}
      {closeOpen && item.actions.includes("close") && (
        <div className="flex flex-wrap items-end gap-2 rounded-md border border-slate-200 bg-slate-50/60 p-2">
          <div className="w-44">
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              verdict
            </label>
            <select
              value={verdict}
              onChange={(e) => setVerdict(e.target.value as CaseVerdict)}
              className="w-full rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
            >
              {VERDICTS.map((v) => (
                <option key={v} value={v}>
                  {v.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <div className="w-48">
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              root cause
            </label>
            <input
              type="text"
              value={rootCause}
              onChange={(e) => setRootCause(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
            />
          </div>
          <div className="w-28">
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              recovered
            </label>
            <input
              type="number"
              min={0}
              value={recovered}
              onChange={(e) => setRecovered(e.target.value)}
              className="tnum w-full rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
            />
          </div>
          <div className="w-28">
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              prevented
            </label>
            <input
              type="number"
              min={0}
              value={prevented}
              onChange={(e) => setPrevented(e.target.value)}
              className="tnum w-full rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
            />
          </div>
          <button
            onClick={() =>
              run(
                `case.${item.id}.close`,
                () =>
                  api.caseAction(item.id, "close", {
                    verdict,
                    root_cause: rootCause,
                    recovered: Number(recovered) || 0,
                    prevented: Number(prevented) || 0,
                  }),
                "Case closed.",
              )
            }
            disabled={anyInFlight}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40"
          >
            {busyKey === `case.${item.id}.close` ? "…" : "Confirm"}
          </button>
          <button
            onClick={cancelClose}
            className="rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-600 transition hover:bg-slate-100"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
