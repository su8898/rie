// Notifications — the POPIA-minimal outbound outbox + opt-in channel preference
// (the direct-claimant notification service, domain-logic §8 / §12.8).
//
// Lifecycle and checklist transitions emit outbound messages, but the body is
// data-minimised by construction: it carries only the claim reference and the
// required action — never medical or quantum detail. Delivery is opt-in, so the
// opt-in flag on the party record IS the POPIA lawful-basis gate: a party with
// no opt-in is SUPPRESSED — logged, not delivered. That is the privacy-correct
// outcome, not a failure. Parties are identified by an HMAC pseudonym (P_*),
// never a name (SPECIFICATION — Party token; no raw PII stored).
//
// Two workflows on one page:
//   • Channel preference — look up a party token's channel (SMS / EMAIL / NONE)
//     and opt-in, and save a change. No opt-in ⇒ every message to that party
//     SUPPRESSES.
//   • Outbox — the notification log, one row per message, with the lifecycle
//     status (PENDING / SENT / SUPPRESSED / FAILED). Delivery itself is external
//     (an SMS / e-mail gateway); mark-sent / mark-failed are the manual delivery
//     reconciliation for a PENDING row until that gateway reports back.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import {
  Card,
  Loading,
  ErrorBox,
  Empty,
  Pagination,
  SearchInput,
  Toast,
  StateChip,
  CodePill,
  matchQ,
  usePaged,
} from "../components/ui";
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

// One-line meaning per lifecycle status — what a row in this state actually is.
const STATUS_MEANING: Record<string, string> = {
  PENDING: "queued for the gateway; awaiting a delivery result",
  SENT: "handed to the SMS / e-mail gateway",
  SUPPRESSED: "not delivered — the party has no opt-in (privacy-correct)",
  FAILED: "the gateway could not deliver it",
};

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
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () =>
      (notifs ?? []).filter((n) =>
        matchQ(q, n.claim_id, n.event, n.channel, n.status, n.body, `#${n.id}`),
      ),
    [notifs, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 25);

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Notifications</h1>
        <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
          The POPIA-minimal outbound outbox (§8 / §12.8). Every message carries
          only a{" "}
          <span className="font-medium text-slate-600">claim reference</span> and
          the{" "}
          <span className="font-medium text-slate-600">required action</span> —
          never medical or quantum detail. Delivery is opt-in, so a party with no
          opt-in is <span className="font-medium text-slate-600">SUPPRESSED</span>{" "}
          (logged, not delivered) — data-minimisation by construction, not a
          failure to reach them.
        </p>
      </header>

      <Card
        title="Channel preference"
        sub="Opt-in IS the POPIA lawful-basis gate for reaching a party. Look up a party token to see its channel — SMS / EMAIL / NONE — and opt-in state, then save a change; with no opt-in, every message to that party SUPPRESSES rather than sends. The token is an HMAC pseudonym (P_*), never a name."
      >
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Party token
              </span>
              <input
                className={inputClass}
                value={tokenInput}
                placeholder="P_… party pseudonym"
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
              {pref.opted_in ? (
                <span className="font-medium text-emerald-700">opted in</span>
              ) : (
                <span className="font-medium text-amber-700">
                  not opted in — messages SUPPRESS
                </span>
              )}
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

          <p className="text-xs text-slate-400">
            NONE and an unchecked opt-in mean the same outcome on the outbox: the
            message is logged as SUPPRESSED, never delivered. Opting in is the
            party's own act — this form records it, it does not grant consent.
          </p>
        </div>
      </Card>

      {loadError && <ErrorBox message={loadError} />}

      <Card
        title="Outbox"
        sub="One row per outbound message: the claim it concerns, the lifecycle event that emitted it, the party's channel, and the delivery status. PENDING is queued, SENT reached the gateway, FAILED could not be delivered, and SUPPRESSED means the party had no opt-in — the privacy-correct outcome, not an error. Delivery itself is external (SMS / e-mail gateway); mark-sent / mark-failed are the manual delivery reconciliation for a PENDING row."
        right={
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
                Status
              </label>
              <select
                className={inputClass}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Filter by status"
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s || "all"} value={s}>
                    {s || "All statuses"}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
                Search
              </label>
              <SearchInput
                value={q}
                onChange={setQ}
                placeholder="Claim, event, channel, message…"
                className="w-56"
              />
            </div>
            {notifs && (
              <div className="pb-1 text-xs text-slate-400">
                <span className="tnum font-semibold text-slate-700">
                  {num(filtered.length)}
                </span>{" "}
                in view
              </div>
            )}
          </div>
        }
      >
        {notifs === null ? (
          <Loading label="Loading outbox…" />
        ) : filtered.length === 0 ? (
          <Empty
            label={
              q || statusFilter
                ? "No notifications match the current status / search."
                : "No notifications sent yet."
            }
          />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className={`${th} text-left`}>#</th>
                    <th className={`${th} text-left`}>Claim</th>
                    <th className={`${th} text-left`}>Event</th>
                    <th className={`${th} text-left`}>Channel</th>
                    <th className={`${th} text-left`}>Status</th>
                    <th className={`${th} text-left`}>Message</th>
                    <th className={`${th} text-left`}>Created</th>
                    <th className={`${th} text-left`}>Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {slice.map((n) => (
                    <tr key={n.id} className="align-top hover:bg-slate-50">
                      <td className="px-3 py-2 font-mono text-[13px] text-slate-400">
                        #{n.id}
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
                        {STATUS_MEANING[n.status] && (
                          <div className="mt-0.5 max-w-[13rem] text-[10px] leading-snug text-slate-400">
                            {STATUS_MEANING[n.status]}
                          </div>
                        )}
                      </td>
                      <td className="max-w-md px-3 py-2 text-xs text-slate-600">
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
                              {busyKey === `sent:${n.id}` ? "…" : "mark sent"}
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
                              {busyKey === `failed:${n.id}` ? "…" : "mark failed"}
                            </button>
                          </div>
                        ) : (
                          <span className="text-slate-300">—</span>
                        )}
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
              unit="notifications"
            />
          </div>
        )}
        <p className="mt-3 text-xs text-slate-400">
          Only PENDING rows can be reconciled — SENT / FAILED / SUPPRESSED are
          terminal. Marking a row records the delivery outcome the external
          gateway reported; it never changes what the body may contain.
        </p>
      </Card>

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
