// Disputes — the objection register, the CIE s91 pattern generalised across the
// three RAF challenge paths (SPECIFICATION §168, §215; the s91 W.G.29 / 180-day
// objection re-expressed).
//
// A claimant, provider or attorney lodges an objection on a subject — MERITS,
// QUANTUM, TARIFF, REPUDIATION or SERIOUS_INJURY. The Fund takes it under
// reconsideration and either upholds, rejects or resolves it internally, OR
// refers it out: a SERIOUS_INJURY objection goes to the HPCSA Appeal Tribunal
// (RAF 4, ≥30% WPI / narrative test — §67); anything else opens a litigation
// record. Every stage carries a statutory deadline; the backend owns the
// transition guards and this page surfaces its 403/409 verbatim.

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import {
  Card,
  Stat,
  Loading,
  ErrorBox,
  Empty,
  Pagination,
  SearchInput,
  Toast,
  StateChip,
  matchQ,
  usePaged,
} from "../components/ui";
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

// What each subject means for the raiser, and where a referral of it lands.
const SUBJECT_HINT: Record<DisputeSubject, string> = {
  MERITS: "liability / apportionment (§4c) — refers to litigation",
  QUANTUM: "the assessed award (§5) — refers to litigation",
  TARIFF: "a repriced line (RPL / SEP) — refers to litigation",
  REPUDIATION: "an s19 / no-nexus rejection — refers to litigation",
  SERIOUS_INJURY: "the RAF 4 gate (§67) — refers to the HPCSA tribunal",
};

// Where the outcome text on a closed dispute comes from, per action.
const ACTION_HINT: Record<string, string> = {
  reconsider: "take under reconsideration (no note)",
  withdraw: "raiser drops the objection (no note)",
  refer: "hand out — HPCSA tribunal or a litigation record",
  uphold: "objection succeeds — record the outcome",
  reject: "objection fails — record the outcome",
  resolve: "settled internally — record the outcome",
};

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
  const [search, setSearch] = useState("");
  const filtered = useMemo(
    () =>
      (items ?? []).filter((it) =>
        matchQ(search, it.claim_id, it.subject, it.raised_by, it.status,
               it.channel, it.outcome, `#${it.id}`),
      ),
    [items, search],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 20);

  // Presentational-only read-outs derived from what's already loaded.
  const closed = analytics ? analytics.n - analytics.open : 0;
  const overdueCount = (items ?? []).filter((it) => it.overdue).length;
  const filtersActive = Boolean(subject || status);

  if (items === null || analytics === null) {
    if (loadError) return <ErrorBox message={loadError} />;
    return <Loading />;
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Disputes</h1>
        <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
          The objection register — the CIE s91 objection (W.G.29, 180-day window)
          generalised across the three RAF challenge paths (§168, §215). A
          claimant, provider or attorney objects on a subject (MERITS, QUANTUM,
          TARIFF, REPUDIATION, SERIOUS_INJURY); the Fund reconsiders and upholds,
          rejects or resolves it — or refers it out: SERIOUS_INJURY to the HPCSA
          Appeal Tribunal (RAF 4, §67), everything else to a litigation record.
          Each stage carries a statutory deadline; the backend owns the transition
          guards.
        </p>
      </header>

      {loadError && <ErrorBox message={loadError} />}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Total"
          value={num(analytics.n)}
          sub="every objection ever lodged"
        />
        <Stat
          label="Open"
          value={num(analytics.open)}
          accent={analytics.open > 0 ? "text-amber-600" : "text-slate-900"}
          sub={`${num(closed)} closed · in-flight, awaiting a decision`}
        />
        <Stat
          label="Overdue"
          value={num(overdueCount)}
          accent={overdueCount > 0 ? "text-rose-600" : "text-slate-900"}
          sub="past this stage's deadline (loaded set)"
        />
        <Stat
          label="Subjects seen"
          value={num(Object.keys(analytics.by_subject).length)}
          sub={`of ${SUBJECTS.length} objection subjects`}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card
          title="By subject"
          sub="What claimants and providers push back on. MERITS/QUANTUM/TARIFF/REPUDIATION objections refer to litigation; SERIOUS_INJURY refers to the HPCSA tribunal. A concentration in one subject points at where determinations are being contested."
        >
          <div className="flex flex-wrap gap-2">
            {Object.keys(analytics.by_subject).length === 0 ? (
              <span className="text-sm text-slate-400">—</span>
            ) : (
              Object.entries(analytics.by_subject)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => (
                  <span
                    key={k}
                    className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700"
                  >
                    {k}
                    <span className="tnum rounded-full bg-white px-1.5 text-slate-500">
                      {num(v)}
                    </span>
                  </span>
                ))
            )}
          </div>
        </Card>
        <Card
          title="By channel"
          sub="Where objections resolve. INTERNAL is the Fund's own reconsideration; HPCSA_TRIBUNAL and LITIGATION are external referrals (LEGAL-only). Objections with no channel yet are still internal — not referred."
        >
          <div className="flex flex-wrap gap-2">
            {Object.keys(analytics.by_channel).length === 0 ? (
              <span className="text-sm text-slate-400">—</span>
            ) : (
              Object.entries(analytics.by_channel)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => (
                  <span
                    key={k}
                    className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700"
                  >
                    {k}
                    <span className="tnum rounded-full bg-white px-1.5 text-slate-500">
                      {num(v)}
                    </span>
                  </span>
                ))
            )}
          </div>
        </Card>
      </div>

      <Card
        title="Filters"
        sub={
          filtersActive
            ? "Subject and status filter the register server-side; search narrows the loaded page. Filtering by a subject or status."
            : "Subject and status filter the register server-side; the search box narrows the loaded page by claim, channel, outcome or #id."
        }
        right={
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Claim, subject, channel, #id…"
            className="w-64"
          />
        }
      >
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs font-medium text-slate-500">
            Subject
            <select
              className={inputCls}
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            >
              <option value="">All subjects</option>
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
              <option value="">All statuses</option>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Card>

      <Card
        title="Lodge dispute"
        sub="Open an objection against a claim. Any raiser — CLAIMANT, PROVIDER or ATTORNEY — may lodge; the subject fixes which path a referral later takes (SERIOUS_INJURY → HPCSA tribunal, all others → litigation). Referral itself is a LEGAL-only step taken from the register below, never here."
      >
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
              placeholder="optional — the basis for the objection"
            />
          </label>
          <button
            type="button"
            className={primaryBtn}
            disabled={busy || !lodgeClaimId.trim()}
            onClick={submitLodge}
          >
            {busyKey === "lodge" ? "Lodging…" : "Lodge"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Selected: a{" "}
          <span className="font-medium text-slate-500">{lodgeSubject}</span>{" "}
          objection — {SUBJECT_HINT[lodgeSubject]}.
        </p>
      </Card>

      <Card
        title="Objection register"
        sub="One row per objection: its subject and who raised it, the current state and (once referred) its channel, the deadline for the stage it is in, the linked litigation / tribunal ref, and any recorded outcome. A rose deadline is overdue; a plain count is days remaining. Actions are the exact transitions the backend allows from this state — it stays authoritative and rejects the rest (403/409)."
        right={
          <span className="tnum text-xs text-slate-400">
            {num(filtered.length)} shown
            {overdueCount > 0 && (
              <span className="ml-1.5 rounded-full bg-rose-100 px-1.5 py-0.5 font-medium text-rose-700">
                {num(overdueCount)} overdue
              </span>
            )}
          </span>
        }
      >
        {filtered.length === 0 ? (
          <Empty
            label={
              search || filtersActive
                ? "No disputes match the current filters."
                : "No disputes yet."
            }
          />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className={`${th} text-right`}>#</th>
                    <th className={`${th} text-left`}>Claim</th>
                    <th className={`${th} text-left`}>Subject</th>
                    <th className={`${th} text-left`}>Raised by</th>
                    <th className={`${th} text-left`}>Status</th>
                    <th className={`${th} text-left`}>Channel</th>
                    <th className={`${th} text-left`}>Deadline</th>
                    <th className={`${th} text-left`}>Ref</th>
                    <th className={`${th} text-left`}>Outcome</th>
                    <th className={`${th} text-left`}>Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {slice.map((item) => (
                    <tr key={item.id} className="align-top hover:bg-slate-50">
                      <td className="tnum px-3 py-2 text-right text-slate-400">
                        {item.id}
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          to={`/claims/${encodeURIComponent(item.claim_id)}`}
                          className="font-mono text-[13px] text-slate-900 hover:text-blue-600 hover:underline"
                        >
                          {item.claim_id}
                        </Link>
                      </td>
                      <td className="px-3 py-2">
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-700">
                          {item.subject}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-slate-600">{item.raised_by}</td>
                      <td className="px-3 py-2">
                        <StateChip state={item.status} />
                      </td>
                      <td className="px-3 py-2">
                        {item.channel ? (
                          <span className="text-[11px] font-medium text-slate-600">
                            {item.channel}
                          </span>
                        ) : (
                          <span className="text-slate-400" title="not referred — still internal">
                            —
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {item.overdue ? (
                          <span
                            className="inline-flex items-center rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700"
                            title={item.deadline ?? undefined}
                          >
                            overdue
                          </span>
                        ) : item.days_to_deadline !== null ? (
                          <span
                            className="tnum text-xs text-slate-500"
                            title={item.deadline ?? undefined}
                          >
                            {num(item.days_to_deadline)}d left
                          </span>
                        ) : (
                          <span className="text-slate-400" title="no deadline at this state">
                            —
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {item.linked_ref ? (
                          <span className="font-mono text-[11px] text-slate-600">
                            {item.linked_ref}
                          </span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="max-w-[14rem] px-3 py-2 text-slate-600">
                        {item.outcome ?? (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-col gap-2">
                          {item.actions.length === 0 ? (
                            <span className="text-[11px] text-slate-400">
                              closed — no transitions
                            </span>
                          ) : (
                            <div className="flex flex-wrap gap-1.5">
                              {item.actions.map((action) => (
                                <button
                                  key={action}
                                  type="button"
                                  className={smallBtn}
                                  disabled={busy}
                                  title={ACTION_HINT[action] ?? action}
                                  onClick={() => doAction(item, action)}
                                >
                                  {busyKey === `${action}-${item.id}`
                                    ? "…"
                                    : action}
                                </button>
                              ))}
                            </div>
                          )}
                          {formFor && formFor.id === item.id && formFor.action === "refer" && (
                            <div className="flex flex-col gap-1 rounded-md border border-slate-200 bg-slate-50/60 p-2">
                              <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
                                refer channel
                              </span>
                              <div className="flex flex-wrap items-center gap-1.5">
                                <select
                                  className={inputCls}
                                  value={referChannel}
                                  onChange={(e) => setReferChannel(e.target.value)}
                                >
                                  <option value="">auto (by subject)</option>
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
                              <span className="text-[10px] text-slate-400">
                                Leave on auto to route by subject: SERIOUS_INJURY →
                                HPCSA tribunal, else litigation.
                              </span>
                            </div>
                          )}
                          {formFor &&
                            formFor.id === item.id &&
                            (formFor.action === "uphold" ||
                              formFor.action === "reject" ||
                              formFor.action === "resolve") && (
                              <div className="flex flex-col gap-1 rounded-md border border-slate-200 bg-slate-50/60 p-2">
                                <span className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
                                  {formFor.action} — outcome
                                </span>
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <input
                                    className={inputCls}
                                    value={outcomeText}
                                    onChange={(e) => setOutcomeText(e.target.value)}
                                    placeholder="outcome / reasons"
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
                              </div>
                            )}
                        </div>
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
              unit="disputes"
            />
          </div>
        )}

        <div className="mt-3 rounded-md border border-slate-100 bg-slate-50/60 p-3 text-xs leading-relaxed text-slate-500">
          <span className="font-semibold text-slate-600">Workflow.</span>{" "}
          LODGED → <span className="font-medium">reconsider</span> takes it
          UNDER_RECONSIDERATION, from where it may{" "}
          <span className="font-medium">uphold</span> /{" "}
          <span className="font-medium">reject</span> /{" "}
          <span className="font-medium">resolve</span> internally, or{" "}
          <span className="font-medium">refer</span> out; the raiser may{" "}
          <span className="font-medium">withdraw</span> while it is still open.{" "}
          <span className="font-medium">refer</span> is LEGAL-only —
          SERIOUS_INJURY opens an HPCSA Appeal Tribunal referral (RAF 4, §67), any
          other subject opens a litigation record; the linked ref then appears in
          the Ref column. The backend enforces every guard and is authoritative:
          a disallowed transition returns 403/409 and surfaces as a toast.
        </div>
      </Card>

      {toast && (
        <Toast tone={toast.kind} message={toast.message} onClose={() => setToast(null)} />
      )}
    </div>
  );
}
