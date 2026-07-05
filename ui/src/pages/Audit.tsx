// Audit — post-payment clawback recovery.
//
// Top: ROI cards (at-stake / recovered / recovery-rate / n_items) + by-status
// and by-outcome breakdowns. A recovery-sweep control (INVESTIGATOR) scans paid
// claims and opens clawback items. The queue table drives each item through its
// state machine: OPEN -> UNDER_REVIEW -> RECOVERED / CLEARED. `review` and
// `clear` are one-click; `recover` opens an inline amount + outcome form.
//
// All transitions require INVESTIGATOR; the backend is authoritative and its
// 403/409 {detail} (wrong role, illegal transition, invalid outcome) is
// surfaced verbatim via Toast. Queue + ROI re-fetch on every success.

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import {
  Card,
  Empty,
  ErrorBox,
  Loading,
  Pagination,
  Stat,
  Toast,
  usePaged,
} from "../components/ui";
import { num, rand } from "../format";
import type {
  AuditItem,
  AuditRoi,
  AuditStatus,
  RecoveryOutcome,
} from "../types";

const STATUS_OPTS: AuditStatus[] = [
  "OPEN",
  "UNDER_REVIEW",
  "RECOVERED",
  "CLEARED",
];

const OUTCOMES: RecoveryOutcome[] = [
  "RECOVERED_FULL",
  "RECOVERED_PARTIAL",
  "WRITTEN_OFF",
  "NOT_PURSUED",
];

// Status chip: OPEN=sky, UNDER_REVIEW=amber, RECOVERED=emerald, CLEARED=slate.
function AuditStatusChip({ status }: { status: AuditStatus }) {
  const cls =
    status === "OPEN"
      ? "bg-sky-100 text-sky-800 ring-sky-600/20"
      : status === "UNDER_REVIEW"
        ? "bg-amber-100 text-amber-800 ring-amber-600/20"
        : status === "RECOVERED"
          ? "bg-emerald-100 text-emerald-800 ring-emerald-600/20"
          : "bg-slate-200 text-slate-600 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${cls}`}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

export default function AuditPage() {
  const { user } = useAuth();
  const isInvestigator = user?.role === "INVESTIGATOR" || user?.role === "ADMIN";

  const [items, setItems] = useState<AuditItem[] | null>(null);
  const [roi, setRoi] = useState<AuditRoi | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [threshold, setThreshold] = useState(20);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [recoverFor, setRecoverFor] = useState<number | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    tone: "error" | "success";
  } | null>(null);

  const load = useCallback(async (status: string) => {
    try {
      const [i, r] = await Promise.all([
        api.auditItems(status || undefined),
        api.auditRoi(),
      ]);
      setItems(i);
      setRoi(r);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    void load(statusFilter);
  }, [load, statusFilter]);

  // Fire an item action: disable in-flight, refetch queue + ROI on success,
  // surface backend {detail} on failure.
  const run = useCallback(
    (key: string, fn: () => Promise<unknown>, okMsg: string) => {
      if (busyKey !== null) return;
      setBusyKey(key);
      fn()
        .then(async () => {
          await load(statusFilter);
          setRecoverFor(null);
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
    [busyKey, load, statusFilter],
  );

  function runSweep() {
    if (busyKey !== null) return;
    setBusyKey("sweep");
    api
      .auditSweep(threshold)
      .then(async (r) => {
        await load(statusFilter);
        setToast({
          message:
            r.n === 0
              ? `Sweep at ${r.threshold}: no new items opened.`
              : `Sweep at ${r.threshold}: opened ${r.n} item${r.n === 1 ? "" : "s"} (${r.opened.join(", ")}).`,
          tone: "success",
        });
      })
      .catch((e) =>
        setToast({
          message: e instanceof ApiError ? e.message : "Sweep failed.",
          tone: "error",
        }),
      )
      .finally(() => setBusyKey(null));
  }

  const selectCls =
    "rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";

  const { page, setPage, pageCount, total, slice } = usePaged(items ?? [], 20);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Audit</h1>
        <span className="text-xs text-slate-400">
          post-payment clawback recovery
        </span>
      </div>

      {loadError && <ErrorBox message={loadError} />}

      {/* ROI cards */}
      {roi && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="Amount at stake" value={rand(roi.amount_at_stake)} />
            <Stat
              label="Amount recovered"
              value={rand(roi.amount_recovered)}
              accent="text-emerald-600"
            />
            <Stat
              label="Recovery rate"
              value={`${roi.recovery_rate}%`}
              accent={
                roi.recovery_rate >= 50
                  ? "text-emerald-600"
                  : "text-slate-900"
              }
            />
            <Stat label="Items" value={num(roi.n_items)} />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Card title="By status">
              <Breakdown map={roi.by_status} empty="No items." />
            </Card>
            <Card title="By outcome">
              <Breakdown map={roi.by_outcome} empty="No recoveries yet." />
            </Card>
          </div>
        </>
      )}

      {/* Recovery sweep control */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="w-32">
          <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
            Sweep threshold
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
          onClick={runSweep}
          disabled={busyKey !== null || !isInvestigator}
          title={
            isInvestigator ? undefined : "Requires role: INVESTIGATOR"
          }
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busyKey === "sweep" ? "Sweeping…" : "Run recovery sweep"}
        </button>
        <span className="text-xs text-slate-400">
          Opens clawback items on paid claims flagged RED/FRAUD or touched by a
          high-risk provider.
        </span>
      </div>

      {/* Queue */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Recovery queue
        </h2>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className={selectCls}
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          {STATUS_OPTS.map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </div>

      {items === null ? (
        <Loading label="Loading recovery queue…" />
      ) : items.length === 0 ? (
        <Empty label="No audit items match — run a recovery sweep to open some." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>ID</th>
                  <th className={`${th} text-left`}>Claim</th>
                  <th className={`${th} text-left`}>Status</th>
                  <th className={`${th} text-left`}>Reason</th>
                  <th className={`${th} text-right`}>At stake</th>
                  <th className={`${th} text-right`}>Recovered</th>
                  <th className={`${th} text-left`}>Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((it) => (
                  <tr key={it.id} className="align-top hover:bg-slate-50">
                    <td className="px-3 py-2 text-xs text-slate-400">
                      #{it.id}
                    </td>
                    <td className="px-3 py-2">
                      <Link
                        to={`/claims/${encodeURIComponent(it.claim_id)}`}
                        className="font-mono text-[13px] text-slate-900 hover:text-blue-600 hover:underline"
                      >
                        {it.claim_id}
                      </Link>
                    </td>
                    <td className="px-3 py-2">
                      <AuditStatusChip status={it.status} />
                      {it.recovery_outcome && (
                        <div className="mt-0.5 text-[10px] text-slate-400">
                          {it.recovery_outcome.replace(/_/g, " ")}
                        </div>
                      )}
                    </td>
                    <td className="max-w-xs px-3 py-2 text-xs text-slate-600">
                      {it.reason}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {rand(it.amount_at_stake)}
                    </td>
                    <td className="tnum px-3 py-2 text-right font-medium text-slate-800">
                      {rand(it.amount_recovered)}
                    </td>
                    <td className="px-3 py-2">
                      <ItemActions
                        item={it}
                        busyKey={busyKey}
                        canAct={isInvestigator}
                        recoverOpen={recoverFor === it.id}
                        openRecover={() => setRecoverFor(it.id)}
                        cancelRecover={() => setRecoverFor(null)}
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
            unit="items"
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

const th =
  "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";

function Breakdown({
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

function ItemActions({
  item,
  busyKey,
  canAct,
  recoverOpen,
  openRecover,
  cancelRecover,
  run,
}: {
  item: AuditItem;
  busyKey: string | null;
  canAct: boolean;
  recoverOpen: boolean;
  openRecover: () => void;
  cancelRecover: () => void;
  run: (key: string, fn: () => Promise<unknown>, okMsg: string) => void;
}) {
  const [amount, setAmount] = useState<string>(String(item.amount_at_stake));
  const [outcome, setOutcome] = useState<RecoveryOutcome>("RECOVERED_FULL");
  const anyInFlight = busyKey !== null;

  if (item.actions.length === 0) {
    return <span className="text-[11px] text-slate-300">—</span>;
  }

  const btn = (
    label: string,
    onClick: () => void,
    tone: "default" | "primary" | "danger" = "default",
    key = `audit.${item.id}.${label}`,
  ) => (
    <button
      onClick={onClick}
      disabled={anyInFlight || !canAct}
      title={canAct ? undefined : "Requires role: INVESTIGATOR"}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
        tone === "primary"
          ? "bg-slate-900 text-white hover:bg-slate-800"
          : tone === "danger"
            ? "border border-rose-300 text-rose-700 hover:bg-rose-50"
            : "border border-slate-300 text-slate-700 hover:bg-slate-100"
      }`}
    >
      {busyKey === key ? "…" : label}
    </button>
  );

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {item.actions.includes("review") &&
          btn(
            "review",
            () =>
              run(
                `audit.${item.id}.review`,
                () => api.auditAction(item.id, "review"),
                "Item under review.",
              ),
            "default",
            `audit.${item.id}.review`,
          )}
        {item.actions.includes("recover") &&
          btn(
            "recover",
            openRecover,
            "primary",
            `audit.${item.id}.recover-open`,
          )}
        {item.actions.includes("clear") &&
          btn(
            "clear",
            () =>
              run(
                `audit.${item.id}.clear`,
                () => api.auditAction(item.id, "clear"),
                "Item cleared.",
              ),
            "danger",
            `audit.${item.id}.clear`,
          )}
      </div>

      {/* Recover inline form */}
      {recoverOpen && item.actions.includes("recover") && (
        <div className="flex flex-wrap items-end gap-2 rounded-md border border-slate-200 bg-slate-50/60 p-2">
          <div className="w-28">
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              amount
            </label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="tnum w-full rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
            />
          </div>
          <div className="w-40">
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              outcome
            </label>
            <select
              value={outcome}
              onChange={(e) => setOutcome(e.target.value as RecoveryOutcome)}
              className="w-full rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
            >
              {OUTCOMES.map((o) => (
                <option key={o} value={o}>
                  {o.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={() =>
              run(
                `audit.${item.id}.recover`,
                () =>
                  api.auditAction(item.id, "recover", {
                    amount: Number(amount),
                    outcome,
                  }),
                "Recovery captured.",
              )
            }
            disabled={anyInFlight || !canAct}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40"
          >
            {busyKey === `audit.${item.id}.recover` ? "…" : "Confirm"}
          </button>
          <button
            onClick={cancelRecover}
            className="rounded-md border border-slate-300 px-2.5 py-1.5 text-xs text-slate-600 transition hover:bg-slate-100"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
