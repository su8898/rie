import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { Card, Stat, Loading, ErrorBox, Empty, Toast, StateChip } from "../components/ui";
import { num } from "../format";
import type {
  DisputeItem,
  DisputeAnalytics,
  DisputeSubject,
  DisputeRaiser,
} from "../types";

const th = "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";
const inputCls =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const primaryBtn =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed";
const smallBtn =
  "rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40";

const SUBJECTS: DisputeSubject[] = [
  "MERITS",
  "QUANTUM",
  "TARIFF",
  "REPUDIATION",
  "SERIOUS_INJURY",
];
const RAISERS: DisputeRaiser[] = ["CLAIMANT", "PROVIDER", "ATTORNEY"];
const STATUSES = [
  "LODGED",
  "UNDER_RECONSIDERATION",
  "UPHELD",
  "REJECTED",
  "REFERRED",
  "RESOLVED",
  "WITHDRAWN",
];
const REFER_CHANNELS = ["INTERNAL", "HPCSA_TRIBUNAL", "LITIGATION"];

type ToastState = { kind: "success" | "error"; message: string } | null;
type FormFor = { id: number; action: string } | null;

export default function DisputesPage() {

  const [analytics, setAnalytics] = useState<DisputeAnalytics | null>(null);
  const [items, setItems] = useState<DisputeItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [subject, setSubject] = useState<string>("");
  const [status, setStatus] = useState<string>("");

  const [lodgeClaimId, setLodgeClaimId] = useState<string>("");
  const [lodgeSubject, setLodgeSubject] = useState<DisputeSubject>("MERITS");
  const [lodgeRaisedBy, setLodgeRaisedBy] = useState<DisputeRaiser>("CLAIMANT");
  const [lodgeGrounds, setLodgeGrounds] = useState<string>("");

  const [formFor, setFormFor] = useState<FormFor>(null);
  const [outcomeText, setOutcomeText] = useState<string>("");
  const [referChannel, setReferChannel] = useState<string>("");

  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState>(null);

  const load = useCallback(async () => {
    try {
      setLoadError(null);
      const [a, list] = await Promise.all([
        api.disputeAnalytics(),
        api.disputes({
          subject: subject || undefined,
          status: status || undefined,
        }),
      ]);
      setAnalytics(a);
      setItems(list);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load disputes.");
    }
  }, [subject, status]);

  useEffect(() => {
    void load();
  }, [load]);

  const run = useCallback(
    async (key: string, fn: () => Promise<unknown>, okMsg: string) => {
      setBusyKey(key);
      try {
        await fn();
        await load();
        setToast({ kind: "success", message: okMsg });
      } catch (e) {
        setToast({
          kind: "error",
          message: e instanceof ApiError ? e.message : "Request failed.",
        });
      } finally {
        setBusyKey(null);
      }
    },
    [load],
  );

  const openForm = (id: number, action: string) => {
    setFormFor({ id, action });
    setOutcomeText("");
    setReferChannel("");
  };

  const closeForm = () => setFormFor(null);

  const doAction = (item: DisputeItem, action: string) => {
    if (action === "reconsider" || action === "withdraw") {
      void run(
        `${action}-${item.id}`,
        () => api.disputeAction(item.id, action),
        `Dispute #${item.id} ${action}.`,
      );
      return;
    }
    openForm(item.id, action);
  };

  const submitRefer = (item: DisputeItem) => {
    void run(
      `refer-${item.id}`,
      () =>
        api.disputeAction(item.id, "refer", {
          channel: referChannel || undefined,
        }),
      `Dispute #${item.id} referred.`,
    ).then(closeForm);
  };

  const submitOutcome = (item: DisputeItem, action: string) => {
    void run(
      `${action}-${item.id}`,
      () => api.disputeAction(item.id, action, { outcome: outcomeText }),
      `Dispute #${item.id} ${action}.`,
    ).then(closeForm);
  };

  const submitLodge = () => {
    void run(
      "lodge",
      () =>
        api.lodgeDispute({
          claim_id: lodgeClaimId,
          subject: lodgeSubject,
          raised_by: lodgeRaisedBy,
          grounds: lodgeGrounds || undefined,
        }),
      "Dispute lodged.",
    ).then(() => {
      setLodgeClaimId("");
      setLodgeGrounds("");
    });
  };

  const busy = busyKey !== null;

  if (items === null || analytics === null) {
    if (loadError) return <ErrorBox message={loadError} />;
    return <Loading />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Disputes</h1>
        <span className="text-xs text-slate-400">objection register (s91 generalised)</span>
      </div>

      {loadError && <ErrorBox message={loadError} />}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Total" value={num(analytics.n)} />
        <Stat label="Open" value={num(analytics.open)} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title="By subject">
          <div className="flex flex-wrap gap-2">
            {Object.keys(analytics.by_subject).length === 0 ? (
              <span className="text-sm text-slate-400">—</span>
            ) : (
              Object.entries(analytics.by_subject).map(([k, v]) => (
                <span
                  key={k}
                  className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700"
                >
                  {k} · {num(v)}
                </span>
              ))
            )}
          </div>
        </Card>
        <Card title="By channel">
          <div className="flex flex-wrap gap-2">
            {Object.keys(analytics.by_channel).length === 0 ? (
              <span className="text-sm text-slate-400">—</span>
            ) : (
              Object.entries(analytics.by_channel).map(([k, v]) => (
                <span
                  key={k}
                  className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700"
                >
                  {k} · {num(v)}
                </span>
              ))
            )}
          </div>
        </Card>
      </div>

      <Card title="Filters">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            Subject
            <select
              className={inputCls}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            >
              <option value="">All</option>
              {SUBJECTS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            Status
            <select
              className={inputCls}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">All</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      <Card title="Lodge dispute">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            Claim ID
            <input
              className={inputCls}
              value={lodgeClaimId}
              onChange={(e) => setLodgeClaimId(e.target.value)}
              placeholder="CLM-…"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            Subject
            <select
              className={inputCls}
              value={lodgeSubject}
              onChange={(e) => setLodgeSubject(e.target.value as DisputeSubject)}
            >
              {SUBJECTS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            Raised by
            <select
              className={inputCls}
              value={lodgeRaisedBy}
              onChange={(e) => setLodgeRaisedBy(e.target.value as DisputeRaiser)}
            >
              {RAISERS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-1 flex-col gap-1 text-xs font-medium text-slate-500">
            Grounds
            <input
              className={inputCls}
              value={lodgeGrounds}
              onChange={(e) => setLodgeGrounds(e.target.value)}
              placeholder="optional"
            />
          </label>
          <button
            type="button"
            className={primaryBtn}
            disabled={busy || !lodgeClaimId.trim()}
            onClick={submitLodge}
          >
            Lodge
          </button>
        </div>
      </Card>

      {items.length === 0 ? (
        <Empty />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={th}>#</th>
                  <th className={th}>Claim</th>
                  <th className={th}>Subject</th>
                  <th className={th}>Raised by</th>
                  <th className={th}>Status</th>
                  <th className={th}>Channel</th>
                  <th className={th}>Deadline</th>
                  <th className={th}>Ref</th>
                  <th className={th}>Outcome</th>
                  <th className={th}>Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {items.map((item) => (
                  <tr key={item.id} className="align-top">
                    <td className="px-3 py-2 text-slate-500">{item.id}</td>
                    <td className="px-3 py-2">
                      <Link
                        to={`/claims/${encodeURIComponent(item.claim_id)}`}
                        className="font-mono text-[13px] text-slate-900 hover:text-blue-600 hover:underline"
                      >
                        {item.claim_id}
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-slate-700">{item.subject}</td>
                    <td className="px-3 py-2 text-slate-700">{item.raised_by}</td>
                    <td className="px-3 py-2">
                      <StateChip state={item.status} />
                    </td>
                    <td className="px-3 py-2 text-slate-700">{item.channel ?? "—"}</td>
                    <td className="px-3 py-2">
                      {item.overdue ? (
                        <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700">
                          overdue
                        </span>
                      ) : item.days_to_deadline !== null ? (
                        <span className="text-xs text-slate-500">
                          {num(item.days_to_deadline)}d
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-700">{item.linked_ref ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-700">{item.outcome ?? "—"}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-col gap-2">
                        <div className="flex flex-wrap gap-1.5">
                          {item.actions.map((action) => (
                            <button
                              key={action}
                              type="button"
                              className={smallBtn}
                              disabled={busy}
                              onClick={() => doAction(item, action)}
                            >
                              {action}
                            </button>
                          ))}
                        </div>
                        {formFor && formFor.id === item.id && formFor.action === "refer" && (
                          <div className="flex flex-wrap items-center gap-1.5">
                            <select
                              className={inputCls}
                              value={referChannel}
                              onChange={(e) => setReferChannel(e.target.value)}
                            >
                              <option value="">auto</option>
                              {REFER_CHANNELS.map((c) => (
                                <option key={c} value={c}>
                                  {c}
                                </option>
                              ))}
                            </select>
                            <button
                              type="button"
                              className={smallBtn}
                              disabled={busy}
                              onClick={() => submitRefer(item)}
                            >
                              Confirm
                            </button>
                            <button
                              type="button"
                              className={smallBtn}
                              disabled={busy}
                              onClick={closeForm}
                            >
                              Cancel
                            </button>
                          </div>
                        )}
                        {formFor &&
                          formFor.id === item.id &&
                          (formFor.action === "uphold" ||
                            formFor.action === "reject" ||
                            formFor.action === "resolve") && (
                            <div className="flex flex-wrap items-center gap-1.5">
                              <input
                                className={inputCls}
                                value={outcomeText}
                                onChange={(e) => setOutcomeText(e.target.value)}
                                placeholder="outcome"
                              />
                              <button
                                type="button"
                                className={smallBtn}
                                disabled={busy}
                                onClick={() => submitOutcome(item, formFor.action)}
                              >
                                Confirm
                              </button>
                              <button
                                type="button"
                                className={smallBtn}
                                disabled={busy}
                                onClick={closeForm}
                              >
                                Cancel
                              </button>
                            </div>
                          )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="text-xs text-slate-400">
        refer is LEGAL-only; SERIOUS_INJURY refers to HPCSA tribunal, others to litigation
        (opens a litigation record).
      </p>

      {toast && (
        <Toast tone={toast.kind} message={toast.message} onClose={() => setToast(null)} />
      )}
    </div>
  );
}
