import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { Card, Stat, Loading, ErrorBox, Empty, Toast, StateChip, CodePill } from "../components/ui";
import { num } from "../format";
import type { Notification, NotifPref, NotifChannel } from "../types";

const th = "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";

const inputClass =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const smallBtn =
  "rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40";
const claimLink =
  "font-mono text-[13px] text-slate-900 hover:text-blue-600 hover:underline";

const STATUS_OPTIONS = ["", "PENDING", "SENT", "SUPPRESSED", "FAILED"] as const;
const CHANNEL_OPTIONS: NotifChannel[] = ["SMS", "EMAIL", "NONE"];

export default function NotificationsPage() {

  const [statusFilter, setStatusFilter] = useState<string>("");
  const [notifs, setNotifs] = useState<Notification[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const [tokenInput, setTokenInput] = useState<string>("");
  const [pref, setPref] = useState<NotifPref | null>(null);
  const [prefChannel, setPrefChannel] = useState<NotifChannel>("SMS");
  const [prefOptedIn, setPrefOptedIn] = useState<boolean>(false);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const rows = await api.notifications(
        statusFilter ? { status: statusFilter } : {}
      );
      setNotifs(rows);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load notifications.");
    }
  }, [statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const run = useCallback(
    async (key: string, fn: () => Promise<unknown>, okMsg: string) => {
      setBusyKey(key);
      try {
        await fn();
        await load();
        setToast(okMsg);
      } catch (e) {
        setToast(e instanceof ApiError ? e.message : "Request failed.");
      } finally {
        setBusyKey(null);
      }
    },
    [load]
  );

  const lookUpPref = useCallback(async () => {
    const token = tokenInput.trim();
    if (!token) return;
    setBusyKey("pref:lookup");
    try {
      const p = await api.notifPref(token);
      setPref(p);
      setPrefChannel(
        p.channel === "EMAIL" ? "EMAIL" : p.channel === "NONE" ? "NONE" : "SMS"
      );
      setPrefOptedIn(p.opted_in);
    } catch (e) {
      setToast(e instanceof ApiError ? e.message : "Request failed.");
    } finally {
      setBusyKey(null);
    }
  }, [tokenInput]);

  const savePref = useCallback(async () => {
    const token = pref ? pref.party_token : tokenInput.trim();
    if (!token) return;
    setBusyKey("pref:save");
    try {
      const p = await api.setNotifPref(token, prefChannel, prefOptedIn);
      setPref(p);
      setToast("Preference saved.");
    } catch (e) {
      setToast(e instanceof ApiError ? e.message : "Request failed.");
    } finally {
      setBusyKey(null);
    }
  }, [pref, tokenInput, prefChannel, prefOptedIn]);

  const disabled = busyKey !== null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Notifications</h1>
        <span className="text-xs text-slate-400">
          POPIA-minimal outbox · opt-in channel
        </span>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1">
          <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Status
          </span>
          <select
            className={inputClass}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s || "all"} value={s}>
                {s || "All"}
              </option>
            ))}
          </select>
        </label>
        {notifs && (
          <Stat label="In view" value={num(notifs.length)} />
        )}
      </div>

      <Card title="Channel preference">
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Party token
              </span>
              <input
                className={inputClass}
                value={tokenInput}
                placeholder="party token"
                onChange={(e) => setTokenInput(e.target.value)}
              />
            </label>
            <button
              type="button"
              className={smallBtn}
              disabled={disabled || !tokenInput.trim()}
              onClick={lookUpPref}
            >
              Look up
            </button>
          </div>

          {pref && (
            <div className="text-xs text-slate-600">
              Current: <CodePill>{pref.party_token}</CodePill> · channel{" "}
              <CodePill>{pref.channel}</CodePill> ·{" "}
              {pref.opted_in ? "opted in" : "not opted in"}
            </div>
          )}

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Channel
              </span>
              <select
                className={inputClass}
                value={prefChannel}
                onChange={(e) => setPrefChannel(e.target.value as NotifChannel)}
              >
                {CHANNEL_OPTIONS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 pb-1.5 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={prefOptedIn}
                onChange={(e) => setPrefOptedIn(e.target.checked)}
              />
              opted in
            </label>
            <button
              type="button"
              className={smallBtn}
              disabled={disabled || (!pref && !tokenInput.trim())}
              onClick={savePref}
            >
              Save
            </button>
          </div>

          <p className="text-xs text-slate-500">
            Opt-in is POPIA: a party with no opt-in gets SUPPRESSED (logged, not
            delivered).
          </p>
        </div>
      </Card>

      {loadError ? (
        <ErrorBox message={loadError} />
      ) : notifs === null ? (
        <Loading />
      ) : notifs.length === 0 ? (
        <Empty label="No notifications." />
      ) : (
        <div className="space-y-1">
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr>
                    <th className={th}>#</th>
                    <th className={th}>Claim</th>
                    <th className={th}>Event</th>
                    <th className={th}>Channel</th>
                    <th className={th}>Status</th>
                    <th className={th}>Message</th>
                    <th className={th}>Created</th>
                    <th className={th}>Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {notifs.map((n) => (
                    <tr key={n.id}>
                      <td className="px-3 py-2 font-mono text-[13px] text-slate-700">
                        {n.id}
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          to={`/claims/${encodeURIComponent(n.claim_id)}`}
                          className={claimLink}
                        >
                          {n.claim_id}
                        </Link>
                      </td>
                      <td className="px-3 py-2">
                        <CodePill>{n.event}</CodePill>
                      </td>
                      <td className="px-3 py-2 text-slate-700">{n.channel}</td>
                      <td className="px-3 py-2">
                        <StateChip state={n.status} />
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-600 max-w-md">
                        {n.body}
                      </td>
                      <td className="px-3 py-2 text-slate-500">
                        {n.created_at ?? "—"}
                      </td>
                      <td className="px-3 py-2">
                        {n.status === "PENDING" ? (
                          <div className="flex gap-1">
                            <button
                              type="button"
                              className={smallBtn}
                              disabled={disabled}
                              onClick={() =>
                                run(
                                  `sent:${n.id}`,
                                  () => api.notifMarkSent(n.id),
                                  "Marked sent."
                                )
                              }
                            >
                              mark sent
                            </button>
                            <button
                              type="button"
                              className={smallBtn}
                              disabled={disabled}
                              onClick={() =>
                                run(
                                  `failed:${n.id}`,
                                  () => api.notifMarkFailed(n.id),
                                  "Marked failed."
                                )
                              }
                            >
                              mark failed
                            </button>
                          </div>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <p className="text-xs text-slate-500">
            Delivery (SMS/e-mail) is external; bodies carry only the claim
            reference and required action — never medical or quantum detail.
          </p>
        </div>
      )}

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
