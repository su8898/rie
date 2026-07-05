// Payments — the payment-batch operations page.
//
// Two-column ops layout:
//   Left  — the eligible-to-pay queue (/payments/queue) and the batch list
//           (/payments/batches). Selecting a batch loads it on the right;
//           clicking a queue row prefills the add-instruction form when an OPEN
//           batch is selected.
//   Right — the selected batch: header + instructions table + payment-event
//           timeline + its `actions` (approve / pay / cancel) as buttons, plus
//           an add-instruction form while the batch is OPEN.
//
// Every action button disables in-flight; on success we re-fetch the batch and
// the queue; failures surface the backend {detail} (segregation of duties,
// PAYEE_UNVERIFIED, eligibility, empty-batch, illegal transition) via Toast.
// Approve/pay are greyed for non-ADMIN as a courtesy — the backend remains
// authoritative and its 403 detail is always shown.

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import {
  BandChip,
  Card,
  DispositionChip,
  Empty,
  ErrorBox,
  Loading,
  Toast,
  YesNo,
} from "../components/ui";
import { rand } from "../format";
import type {
  BatchDict,
  BatchStatus,
  PaymentSource,
  QueueRow,
} from "../types";

const SOURCES: PaymentSource[] = [
  "SETTLEMENT",
  "COURT_ORDER",
  "UNDERTAKING_INVOICE",
  "SUPPLIER",
  "INTERIM",
];

// Which role may fire each batch action (courtesy graying; backend is authoritative).
// ADMIN is a superuser everywhere.
const ADMIN_ONLY = new Set(["approve", "pay"]);

// ── Batch status chip (OPEN=sky, APPROVED=amber, PAID=emerald, CANCELLED=slate)
function BatchStatusChip({ status }: { status: BatchStatus }) {
  const cls =
    status === "OPEN"
      ? "bg-sky-100 text-sky-800 ring-sky-600/20"
      : status === "APPROVED"
        ? "bg-amber-100 text-amber-800 ring-amber-600/20"
        : status === "PAID"
          ? "bg-emerald-100 text-emerald-800 ring-emerald-600/20"
          : "bg-slate-200 text-slate-600 ring-slate-500/20";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${cls}`}
    >
      {status}
    </span>
  );
}

export default function PaymentsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";

  const [queue, setQueue] = useState<QueueRow[] | null>(null);
  const [batches, setBatches] = useState<BatchDict[] | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [batch, setBatch] = useState<BatchDict | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    tone: "error" | "success";
  } | null>(null);

  // Add-instruction form state.
  const [formClaimId, setFormClaimId] = useState("");
  const [formSource, setFormSource] = useState<PaymentSource>("SUPPLIER");
  const [formAmount, setFormAmount] = useState("");

  // New-batch note.
  const [newNote, setNewNote] = useState("");

  const loadLists = useCallback(async () => {
    try {
      const [q, b] = await Promise.all([
        api.paymentsQueue(),
        api.listBatches(),
      ]);
      setQueue(q);
      setBatches(b);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load");
    }
  }, []);

  const loadBatch = useCallback(async (id: number) => {
    try {
      setBatch(await api.getBatch(id));
    } catch (e) {
      setToast({
        message: e instanceof ApiError ? e.message : "Failed to load batch",
        tone: "error",
      });
    }
  }, []);

  useEffect(() => {
    void loadLists();
  }, [loadLists]);

  // Load the selected batch whenever the selection changes.
  useEffect(() => {
    if (selectedId == null) {
      setBatch(null);
      return;
    }
    void loadBatch(selectedId);
  }, [selectedId, loadBatch]);

  // Fire an action: disable in-flight, refetch batch + lists on success,
  // surface the backend {detail} on failure.
  const run = useCallback(
    (key: string, fn: () => Promise<unknown>, okMsg = "Done.") => {
      if (busyKey !== null) return;
      setBusyKey(key);
      fn()
        .then(async () => {
          await Promise.all([
            loadLists(),
            selectedId != null ? loadBatch(selectedId) : Promise.resolve(),
          ]);
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
    [busyKey, loadLists, loadBatch, selectedId],
  );

  function createBatch() {
    if (busyKey !== null) return;
    setBusyKey("new-batch");
    api
      .createBatch(newNote.trim() || undefined)
      .then(async (b) => {
        setNewNote("");
        await loadLists();
        setSelectedId(b.id);
        setToast({ message: `Batch #${b.id} created.`, tone: "success" });
      })
      .catch((e) =>
        setToast({
          message: e instanceof ApiError ? e.message : "Request failed.",
          tone: "error",
        }),
      )
      .finally(() => setBusyKey(null));
  }

  function addInstruction() {
    if (selectedId == null || !formClaimId.trim()) return;
    const amt = formAmount.trim() === "" ? undefined : Number(formAmount);
    run(
      "add-instruction",
      () =>
        api.addInstruction(selectedId, {
          claim_id: formClaimId.trim(),
          source: formSource,
          ...(amt != null && !Number.isNaN(amt) ? { amount: amt } : {}),
        }),
      "Instruction added.",
    );
    setFormAmount("");
  }

  // Clicking a queue row prefills the add-instruction form when a batch is
  // selected and OPEN; otherwise it's a no-op (aside from being harmless).
  function pickQueueRow(row: QueueRow) {
    setFormClaimId(row.claim_id);
    // Heuristic source seed from disposition — user can still change it.
    setFormSource(
      row.disposition === "CLEAN" || row.disposition === "ADJUSTED"
        ? "SUPPLIER"
        : "SETTLEMENT",
    );
  }

  const canPrefill = batch != null && batch.status === "OPEN";

  const labelBtn = (a: string) => a.replace(/_/g, " ");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Payments</h1>
        <span className="text-xs text-slate-400">
          assemble → approve (different admin) → pay
        </span>
      </div>

      {loadError && <ErrorBox message={loadError} />}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* ── Left column ──────────────────────────────────────────────── */}
        <div className="space-y-4 lg:col-span-2">
          {/* Eligible queue */}
          <Card title="Eligible queue">
            {queue === null ? (
              <Loading label="Loading queue…" />
            ) : queue.length === 0 ? (
              <div className="text-sm text-slate-400">
                No claims currently eligible to pay.
              </div>
            ) : (
              <div className="overflow-hidden rounded-md border border-slate-100">
                <table className="min-w-full divide-y divide-slate-100 text-sm">
                  <thead className="bg-slate-50">
                    <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                      <th className="px-3 py-2">Claim</th>
                      <th className="px-3 py-2">Band</th>
                      <th className="px-3 py-2 text-right">Net payable</th>
                      {canPrefill && <th className="px-3 py-2" />}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {queue.map((r) => (
                      <tr key={r.claim_id} className="hover:bg-slate-50">
                        <td className="px-3 py-2">
                          <Link
                            to={`/claims/${encodeURIComponent(r.claim_id)}`}
                            className="font-mono text-[13px] text-slate-900 hover:text-blue-600 hover:underline"
                          >
                            {r.claim_id}
                          </Link>
                          <div className="mt-0.5">
                            <DispositionChip disposition={r.disposition} />
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <BandChip band={r.band} />
                        </td>
                        <td className="tnum px-3 py-2 text-right font-medium text-slate-800">
                          {rand(r.net_payable)}
                        </td>
                        {canPrefill && (
                          <td className="px-3 py-2 text-right">
                            <button
                              onClick={() => pickQueueRow(r)}
                              className="rounded border border-slate-300 px-2 py-0.5 text-[11px] text-slate-600 transition hover:bg-slate-100"
                              title="Prefill add-instruction form"
                            >
                              use
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {/* Batches */}
          <Card
            title={
              <div className="flex items-center justify-between">
                <span>Batches</span>
              </div>
            }
          >
            <div className="mb-3 flex items-end gap-2">
              <div className="flex-1">
                <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
                  New batch note (optional)
                </label>
                <input
                  value={newNote}
                  onChange={(e) => setNewNote(e.target.value)}
                  className="w-full rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
                  placeholder="e.g. weekly supplier run"
                />
              </div>
              <button
                onClick={createBatch}
                disabled={busyKey !== null}
                className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40"
              >
                {busyKey === "new-batch" ? "…" : "New batch"}
              </button>
            </div>

            {batches === null ? (
              <Loading label="Loading batches…" />
            ) : batches.length === 0 ? (
              <div className="text-sm text-slate-400">No batches yet.</div>
            ) : (
              <ul className="space-y-1.5">
                {batches.map((b) => {
                  const active = b.id === selectedId;
                  return (
                    <li key={b.id}>
                      <button
                        onClick={() => setSelectedId(b.id)}
                        className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-left transition ${
                          active
                            ? "border-slate-900 bg-slate-50"
                            : "border-slate-200 hover:bg-slate-50"
                        }`}
                      >
                        <span className="flex items-center gap-2">
                          <span className="text-xs font-medium text-slate-500">
                            #{b.id}
                          </span>
                          <BatchStatusChip status={b.status} />
                          <span className="text-[11px] text-slate-400">
                            {b.instructions.length} instr ·{" "}
                            {b.created_by}
                          </span>
                        </span>
                        <span className="tnum text-sm font-semibold text-slate-800">
                          {rand(b.total)}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>
        </div>

        {/* ── Right column: selected batch ─────────────────────────────── */}
        <div className="lg:col-span-3">
          {batch === null ? (
            <Empty label="Select a batch to view its instructions and events." />
          ) : (
            <div className="space-y-4">
              {/* Header */}
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <h2 className="text-lg font-semibold text-slate-900">
                      Batch #{batch.id}
                    </h2>
                    <BatchStatusChip status={batch.status} />
                  </div>
                  <div className="tnum text-xl font-semibold text-slate-900">
                    {rand(batch.total)}
                  </div>
                </div>

                <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
                  <Meta k="created by" v={batch.created_by} />
                  <Meta k="approved by" v={batch.approved_by ?? "—"} />
                  <Meta k="paid by" v={batch.paid_by ?? "—"} />
                  {batch.note && (
                    <div className="col-span-2 sm:col-span-3">
                      <span className="text-slate-400">note: </span>
                      <span className="text-slate-700">{batch.note}</span>
                    </div>
                  )}
                </dl>

                {/* Action buttons from batch.actions (approve/pay/cancel). */}
                {batch.actions.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                    {batch.actions.map((a) => {
                      const adminGated = ADMIN_ONLY.has(a) && !isAdmin;
                      const danger = a === "cancel";
                      return (
                        <button
                          key={a}
                          onClick={() =>
                            run(
                              `batch.${a}`,
                              () =>
                                a === "approve"
                                  ? api.approveBatch(batch.id)
                                  : a === "pay"
                                    ? api.payBatch(batch.id)
                                    : api.cancelBatch(batch.id),
                              `Batch ${a}${a === "pay" ? "" : "d"}.`,
                            )
                          }
                          disabled={busyKey !== null || adminGated}
                          title={
                            adminGated ? "Requires role: ADMIN" : undefined
                          }
                          className={`rounded-md px-3 py-1.5 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
                            a === "pay"
                              ? "bg-slate-900 text-white hover:bg-slate-800"
                              : danger
                                ? "border border-rose-300 text-rose-700 hover:bg-rose-50"
                                : "border border-slate-300 text-slate-700 hover:bg-slate-100"
                          }`}
                        >
                          {busyKey === `batch.${a}` ? "…" : labelBtn(a)}
                        </button>
                      );
                    })}
                  </div>
                )}
              </Card>

              {/* Instructions */}
              <Card title="Instructions">
                {batch.instructions.length === 0 ? (
                  <div className="text-sm text-slate-400">
                    No instructions yet.
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded-md border border-slate-100">
                    <table className="min-w-full divide-y divide-slate-100 text-sm">
                      <thead className="bg-slate-50">
                        <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                          <th className="px-3 py-2">Claim</th>
                          <th className="px-3 py-2">Source</th>
                          <th className="px-3 py-2 text-right">Amount</th>
                          <th className="px-3 py-2 text-center">Paid</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {batch.instructions.map((i) => (
                          <tr key={i.id}>
                            <td className="px-3 py-2">
                              <Link
                                to={`/claims/${encodeURIComponent(i.claim_id)}`}
                                className="font-mono text-[13px] text-slate-800 hover:text-blue-600 hover:underline"
                              >
                                {i.claim_id}
                              </Link>
                            </td>
                            <td className="px-3 py-2 text-slate-600">
                              {i.source.replace(/_/g, " ")}
                            </td>
                            <td className="tnum px-3 py-2 text-right font-medium text-slate-800">
                              {rand(i.amount)}
                            </td>
                            <td className="px-3 py-2 text-center">
                              <YesNo value={i.paid} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Add-instruction form (OPEN only). */}
                {batch.status === "OPEN" && (
                  <div className="mt-3 space-y-2 rounded-md border border-slate-100 bg-slate-50/60 p-3">
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      Add instruction
                    </div>
                    <div className="flex flex-wrap items-end gap-2">
                      <div className="w-40">
                        <label className={microLabel}>claim id</label>
                        <input
                          value={formClaimId}
                          onChange={(e) => setFormClaimId(e.target.value)}
                          className={`${fieldCls} font-mono`}
                          placeholder="pick from queue →"
                        />
                      </div>
                      <div className="w-48">
                        <label className={microLabel}>source</label>
                        <select
                          value={formSource}
                          onChange={(e) =>
                            setFormSource(e.target.value as PaymentSource)
                          }
                          className={fieldCls}
                        >
                          {SOURCES.map((s) => (
                            <option key={s} value={s}>
                              {s}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="w-32">
                        <label className={microLabel}>
                          amount (optional)
                        </label>
                        <input
                          type="number"
                          value={formAmount}
                          onChange={(e) => setFormAmount(e.target.value)}
                          className={`${fieldCls} tnum`}
                          placeholder="net_payable"
                        />
                      </div>
                      <button
                        onClick={addInstruction}
                        disabled={busyKey !== null || !formClaimId.trim()}
                        className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40"
                      >
                        {busyKey === "add-instruction" ? "…" : "Add"}
                      </button>
                    </div>
                    <p className="text-[11px] text-slate-400">
                      Amount defaults to the claim's net_payable when left blank.
                    </p>
                  </div>
                )}
              </Card>

              {/* Event timeline */}
              <Card title="Payment events">
                {batch.events.length === 0 ? (
                  <div className="text-sm text-slate-400">No events.</div>
                ) : (
                  <ol className="space-y-0">
                    {batch.events.map((e, i) => (
                      <li
                        key={i}
                        className="relative flex gap-3 pb-3 last:pb-0"
                      >
                        {/* rail */}
                        <div className="flex flex-col items-center">
                          <span className="mt-1 h-2 w-2 rounded-full bg-slate-400" />
                          {i < batch.events.length - 1 && (
                            <span className="w-px flex-1 bg-slate-200" />
                          )}
                        </div>
                        <div className="flex-1 pb-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-medium text-slate-800">
                              {e.event.replace(/_/g, " ")}
                            </span>
                            {e.amount != null && (
                              <span className="tnum text-xs font-medium text-slate-600">
                                {rand(e.amount)}
                              </span>
                            )}
                          </div>
                          <div className="text-[11px] text-slate-400">
                            {e.actor}
                            <span className="text-slate-300"> · {e.role}</span>
                            {e.at && (
                              <span className="text-slate-300">
                                {" "}
                                · {new Date(e.at).toLocaleString()}
                              </span>
                            )}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </Card>
            </div>
          )}
        </div>
      </div>

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

const fieldCls =
  "w-full rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const microLabel =
  "mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400";

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <span className="text-slate-400">{k}: </span>
      <span className="font-medium text-slate-700">{v}</span>
    </div>
  );
}
