// Admin — the ADMIN-only operator console: where the engine's reference/config
// data is edited. Nothing here is a code deploy — every change is effective-dated,
// audit-logged reference data the engine reads live on the next determination.
//
// Nine tabs — eight over the /api/admin surface, plus dated rates over /api/rates:
//   • users          — RBAC: create user, change role, activate/deactivate.
//   • signal-modes   — the §11 promotion lifecycle as an effective-dated
//                      SHADOW/ADVISORY/SCORED override (Grounded locked SCORED).
//   • caps           — the s17(4)(c) statutory annual-cap schedule (effective-dated).
//   • preauth        — the codes that require pre-authorisation (ENFORCEABLE tier, §5f).
//   • negotiated     — negotiated ENFORCEABLE TARIFF/NAPPI rates that override RPL/SEP.
//   • rates          — dated versions of the tariff / negotiated / NAPPI rates: the
//                      engine prices each line at the version in force on its
//                      service date (AdminRates.tsx).
//   • code-rules     — the tariff's own billing rules per code: once per encounter,
//                      time-modifier ladders, percentage of time (AdminCodeRules.tsx).
//   • rails-parties  — who may sign onto the provider channel: each party's public
//                      ES256 key and the providers it may act for (AdminRailsParties.tsx).
//   • audit          — the append-only admin CUD log (§9), newest first.
//
// Everything mutating goes through `run(key, fn, okMsg)`: it disables all
// controls while in flight, refetches the affected data, and surfaces the
// backend's 400 {detail} (bad role, Grounded override, self-deactivation, …)
// verbatim via Toast.

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import {
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
  YesNo,
  matchQ,
  usePaged,
} from "../components/ui";
import { rand } from "../format";
import CodeRulesTab from "./AdminCodeRules";
import RailsPartiesTab from "./AdminRailsParties";
import RatesTab from "./AdminRates";
import type {
  AdminAuditRow,
  AdminUser,
  NegotiatedRate,
  Role,
  SignalMode,
  StatutoryCap,
} from "../types";

type Tab =
  | "users"
  | "signal-modes"
  | "caps"
  | "preauth"
  | "negotiated"
  | "rates"
  | "code-rules"
  | "rails-parties"
  | "audit";

const TABS: { key: Tab; label: string }[] = [
  { key: "users", label: "Users" },
  { key: "signal-modes", label: "Signal modes" },
  { key: "caps", label: "Caps" },
  { key: "preauth", label: "Pre-auth" },
  { key: "negotiated", label: "Negotiated" },
  { key: "rates", label: "Dated rates" },
  { key: "code-rules", label: "Coding rules" },
  { key: "rails-parties", label: "Channel keys" },
  { key: "audit", label: "Audit" },
];

const ROLES: Role[] = [
  "ADMIN",
  "HANDLER",
  "MEDICAL_OFFICER",
  "INVESTIGATOR",
  "LEGAL",
];

const MODES = ["SHADOW", "ADVISORY", "SCORED"] as const;
type Mode = (typeof MODES)[number];

const th =
  "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";
const inputCls =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const primaryBtn =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40";
const smallBtn =
  "rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40";
const dangerBtn =
  "rounded-md border border-rose-200 px-2.5 py-1 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-40";

export default function AdminPage() {
  const { user } = useAuth();

  const [tab, setTab] = useState<Tab>("users");

  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [signalModes, setSignalModes] = useState<SignalMode[] | null>(null);
  const [caps, setCaps] = useState<StatutoryCap[] | null>(null);
  const [preauth, setPreauth] = useState<string[] | null>(null);
  const [negotiated, setNegotiated] = useState<NegotiatedRate[] | null>(null);
  const [audit, setAudit] = useState<AdminAuditRow[] | null>(null);

  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    tone: "error" | "success";
  } | null>(null);

  const isAdmin = user?.role === "ADMIN";

  const load = useCallback(async () => {
    try {
      const [u, s, c, p, n, a] = await Promise.all([
        api.adminUsers(),
        api.signalModes(),
        api.adminCaps(),
        api.adminPreauth(),
        api.adminNegotiated(),
        api.adminAudit(),
      ]);
      setUsers(u);
      setSignalModes(s);
      setCaps(c);
      setPreauth(p);
      setNegotiated(n);
      setAudit(a);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load.");
    }
  }, []);

  useEffect(() => {
    if (isAdmin) void load();
  }, [isAdmin, load]);

  // Mutations: disable while in flight, refetch on success, surface {detail}.
  const run = useCallback(
    (key: string, fn: () => Promise<unknown>, okMsg: string) => {
      if (busyKey !== null) return;
      setBusyKey(key);
      fn()
        .then(async () => {
          await load();
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
    [busyKey, load],
  );

  const busy = busyKey !== null;

  if (!isAdmin) {
    return <ErrorBox message="This console requires the ADMIN role." />;
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Admin</h1>
        <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
          The operator console for the reference and config data the engine reads
          live — role assignments, the s17(4)(c) statutory cap schedule, the
          ENFORCEABLE reference tiers that overlay the gazetted tariff (negotiated
          rates, pre-auth gates), and the §11 signal-mode overrides — over an
          append-only audit log. Every change here is effective-dated,
          audit-logged reference data, never a code deploy.
        </p>
      </header>

      {loadError && <ErrorBox message={loadError} />}

      {/* Tabs */}
      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              tab === t.key
                ? "bg-slate-900 text-white"
                : "border border-slate-300 text-slate-700 hover:bg-slate-100"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "users" && (
        <UsersTab users={users} busy={busy} busyKey={busyKey} run={run} />
      )}
      {tab === "signal-modes" && (
        <SignalModesTab
          rows={signalModes}
          busy={busy}
          busyKey={busyKey}
          run={run}
        />
      )}
      {tab === "caps" && (
        <CapsTab caps={caps} busy={busy} busyKey={busyKey} run={run} />
      )}
      {tab === "preauth" && (
        <PreauthTab rows={preauth} busy={busy} busyKey={busyKey} run={run} />
      )}
      {tab === "negotiated" && (
        <NegotiatedTab
          rows={negotiated}
          busy={busy}
          busyKey={busyKey}
          run={run}
        />
      )}
      {tab === "rates" && <RatesTab />}
      {tab === "code-rules" && <CodeRulesTab />}
      {tab === "rails-parties" && <RailsPartiesTab />}
      {tab === "audit" && <AuditTab rows={audit} />}

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

// Shared prop bag for the mutating tabs.
interface TabProps {
  busy: boolean;
  busyKey: string | null;
  run: (key: string, fn: () => Promise<unknown>, okMsg: string) => void;
}

// ── Users ────────────────────────────────────────────────────────────────────
function UsersTab({
  users,
  busy,
  busyKey,
  run,
}: TabProps & { users: AdminUser[] | null }) {
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<Role>("HANDLER");
  const [password, setPassword] = useState("");
  const { page, setPage, pageCount, total, slice } = usePaged(users ?? [], 20);

  const canCreate = username.trim() !== "" && password !== "" && !busy;

  const createUser = () =>
    run(
      "user.create",
      () =>
        api.createUser({
          username: username.trim(),
          role,
          password,
        }),
      `User "${username.trim()}" created.`,
    );

  return (
    <div className="space-y-4">
      {/* Create user */}
      <Card
        title="Create user"
        sub="RBAC roster — a role gates what a user may do: HANDLER assesses / handles claims · MEDICAL_OFFICER does medical review · INVESTIGATOR owns cases (BLOCK / CLAWBACK) and post-payment recovery · LEGAL owns disputes / referrals · ADMIN runs this console and approves / pays batches. The account starts active; every create is audit-logged."
      >
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Username
            </label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={inputCls}
              placeholder="jdoe"
            />
          </div>
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Role
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              className={inputCls}
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputCls}
              placeholder="••••••••"
            />
          </div>
          <button onClick={createUser} disabled={!canCreate} className={primaryBtn}>
            {busyKey === "user.create" ? "Creating…" : "Create user"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Create adds an active user in the chosen role — audit-logged.
        </p>
      </Card>

      {/* Roster */}
      <Card
        title="Users"
        sub="Every operator, with the role the service layer enforces on each request. Change a role from the dropdown, or activate / deactivate — but you cannot deactivate the account you're signed in as (the backend rejects it). Each change is audit-logged."
      >
        {users === null ? (
          <Loading label="Loading users…" />
        ) : users.length === 0 ? (
          <Empty label="No users." />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className={`${th} text-left`}>Username</th>
                    <th className={`${th} text-left`}>Role</th>
                    <th className={`${th} text-left`}>Active</th>
                    <th className={`${th} text-left`}>Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {slice.map((u) => (
                    <tr key={u.id} className="align-middle hover:bg-slate-50">
                      <td className="px-3 py-2 font-mono text-[13px] text-slate-900">
                        {u.username}
                      </td>
                      <td className="px-3 py-2 text-slate-700">{u.role}</td>
                      <td className="px-3 py-2">
                        <YesNo value={u.active} />
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <select
                            value={u.role}
                            disabled={busy}
                            onChange={(e) =>
                              run(
                                `user.role.${u.username}`,
                                () =>
                                  api.setUserRole(
                                    u.username,
                                    e.target.value as Role,
                                  ),
                                `${u.username}: role set to ${e.target.value}.`,
                              )
                            }
                            className="rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 disabled:opacity-40"
                          >
                            {ROLES.map((r) => (
                              <option key={r} value={r}>
                                {r}
                              </option>
                            ))}
                          </select>
                          <button
                            onClick={() =>
                              run(
                                `user.active.${u.username}`,
                                () =>
                                  api.setUserActive(u.username, !u.active),
                                `${u.username}: ${
                                  u.active ? "deactivated" : "activated"
                                }.`,
                              )
                            }
                            disabled={busy}
                            className={smallBtn}
                          >
                            {busyKey === `user.active.${u.username}`
                              ? "…"
                              : u.active
                                ? "deactivate"
                                : "activate"}
                          </button>
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
              unit="users"
            />
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Signal modes ─────────────────────────────────────────────────────────────
function SignalModesTab({
  rows,
  busy,
  busyKey,
  run,
}: TabProps & { rows: SignalMode[] | null }) {
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () =>
      (rows ?? []).filter((r) =>
        matchQ(q, r.signal, r.maturity, r.effective_mode, r.default_mode,
               r.recommended_mode),
      ),
    [rows, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 20);

  return (
    <Card
      title="Signal modes"
      sub="The §11 promotion lifecycle as an effective-dated, audit-logged override: SHADOW (computed, invisible, 0 points) → ADVISORY (shown, still 0 points) → SCORED (adds to the band). Effective is what the engine reads now; Recommended is what measured precision suggests (Governance computes the Wilson-lower ≥ 60% floor; you apply it here). GROUNDED law-cited signals are locked SCORED — no control, they cannot be overridden."
      right={
        <SearchInput
          value={q}
          onChange={setQ}
          placeholder="Search signal…"
          className="w-52"
        />
      }
    >
      {rows === null ? (
        <Loading label="Loading signal modes…" />
      ) : filtered.length === 0 ? (
        <Empty label={q ? "No signals match your search." : "No signals."} />
      ) : (
        <div className="overflow-hidden rounded-md border border-slate-100">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>Signal</th>
                  <th className={`${th} text-left`}>Maturity</th>
                  <th className={`${th} text-left`}>Effective</th>
                  <th className={`${th} text-left`}>Default</th>
                  <th className={`${th} text-right`}>Substantiation</th>
                  <th className={`${th} text-left`}>Recommended</th>
                  <th className={`${th} text-left`}>Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((r) => (
                  <SignalModeRow
                    key={r.signal}
                    row={r}
                    busy={busy}
                    busyKey={busyKey}
                    run={run}
                  />
                ))}
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
      <p className="mt-2 text-xs text-slate-400">
        Set applies the chosen mode as an override; clear reverts to the default.
        Both are audit-logged, effective-dated reference data — never a code
        deploy. Grounded signals show no control — always SCORED.
      </p>
    </Card>
  );
}

function SignalModeRow({
  row,
  busy,
  busyKey,
  run,
}: TabProps & { row: SignalMode }) {
  const [mode, setMode] = useState<Mode>(
    (MODES as readonly string[]).includes(row.effective_mode)
      ? (row.effective_mode as Mode)
      : "SHADOW",
  );
  const [note, setNote] = useState("");

  const subst =
    row.substantiation != null
      ? `${(row.substantiation * 100).toFixed(0)}%`
      : "—";

  return (
    <tr className="align-top hover:bg-slate-50">
      <td className="px-3 py-2">
        <CodePill>{row.signal}</CodePill>
      </td>
      <td className="px-3 py-2">
        <MaturityChip maturity={row.maturity} />
      </td>
      <td className="px-3 py-2">
        <ModeChip mode={row.effective_mode} />
        {row.overridden && (
          <div className="mt-0.5 text-[10px] text-slate-400">
            (override{row.set_by ? ` · ${row.set_by}` : ""})
          </div>
        )}
      </td>
      <td className="px-3 py-2">
        <ModeChip mode={row.default_mode} />
      </td>
      <td className="tnum px-3 py-2 text-right text-slate-600">{subst}</td>
      <td className="px-3 py-2">
        <ModeChip mode={row.recommended_mode ?? row.default_mode} />
      </td>
      <td className="px-3 py-2">
        {row.overridable ? (
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as Mode)}
              disabled={busy}
              className="rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500 disabled:opacity-40"
            >
              {MODES.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="note (optional)"
              className="w-40 rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
            />
            <button
              onClick={() =>
                run(
                  `signal.set.${row.signal}`,
                  () =>
                    api.setSignalMode({
                      code: row.signal,
                      mode,
                      note: note.trim() || undefined,
                    }),
                  `${row.signal}: mode set to ${mode}.`,
                )
              }
              disabled={busy}
              className={smallBtn}
            >
              {busyKey === `signal.set.${row.signal}` ? "…" : "Set"}
            </button>
            {row.overridden && (
              <button
                onClick={() =>
                  run(
                    `signal.clear.${row.signal}`,
                    () => api.clearSignalMode(row.signal),
                    `${row.signal}: override cleared.`,
                  )
                }
                disabled={busy}
                className={smallBtn}
              >
                {busyKey === `signal.clear.${row.signal}` ? "…" : "clear"}
              </button>
            )}
          </div>
        ) : (
          <span className="text-[11px] text-slate-400">
            Grounded · always SCORED
          </span>
        )}
      </td>
    </tr>
  );
}

// ── Caps ─────────────────────────────────────────────────────────────────────
function CapsTab({
  caps,
  busy,
  busyKey,
  run,
}: TabProps & { caps: StatutoryCap[] | null }) {
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [annualCap, setAnnualCap] = useState("");
  const { page, setPage, pageCount, total, slice } = usePaged(caps ?? [], 15);

  const canSave = effectiveFrom !== "" && annualCap !== "" && !busy;

  const upsert = () =>
    run(
      "cap.upsert",
      () => api.upsertCap(effectiveFrom, Number(annualCap)),
      `Cap effective ${effectiveFrom} saved.`,
    );

  return (
    <div className="space-y-4">
      <Card
        title="Add / update cap"
        sub="The statutory annual cap on medical costs (s17(4)(c)) as an effective-dated schedule — the engine applies the cap effective on the service date. Saving a date that already exists overwrites that row; a new date adds a dated entry to the schedule."
      >
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Effective from
            </label>
            <input
              type="date"
              value={effectiveFrom}
              onChange={(e) => setEffectiveFrom(e.target.value)}
              className={inputCls}
            />
          </div>
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Annual cap
            </label>
            <input
              type="number"
              value={annualCap}
              onChange={(e) => setAnnualCap(e.target.value)}
              className={`tnum ${inputCls}`}
              placeholder="0"
            />
          </div>
          <button onClick={upsert} disabled={!canSave} className={primaryBtn}>
            {busyKey === "cap.upsert" ? "Saving…" : "Save cap"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Save upserts the row for that effective date — audit-logged. The cap in
          force on a claim's service date is the one applied.
        </p>
      </Card>

      <Card
        title="Cap schedule"
        sub="The effective-dated s17(4)(c) rows, each the medical ceiling from its date forward. Deleting a row removes that dated entry from the schedule."
      >
        {caps === null ? (
          <Loading label="Loading caps…" />
        ) : caps.length === 0 ? (
          <Empty label="No caps configured." />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className={`${th} text-left`}>Effective from</th>
                    <th className={`${th} text-right`}>Annual cap</th>
                    <th className={`${th} text-right`}>Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {slice.map((c) => (
                    <tr
                      key={c.effective_from}
                      className="align-middle hover:bg-slate-50"
                    >
                      <td className="px-3 py-2 text-slate-700">
                        {c.effective_from}
                      </td>
                      <td className="tnum px-3 py-2 text-right font-medium text-slate-800">
                        {rand(c.annual_cap)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={() =>
                            run(
                              `cap.delete.${c.effective_from}`,
                              () => api.deleteCap(c.effective_from),
                              `Cap effective ${c.effective_from} deleted.`,
                            )
                          }
                          disabled={busy}
                          className={dangerBtn}
                        >
                          {busyKey === `cap.delete.${c.effective_from}`
                            ? "…"
                            : "delete"}
                        </button>
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
              unit="caps"
            />
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Negotiated rates ─────────────────────────────────────────────────────────
function NegotiatedTab({
  rows,
  busy,
  busyKey,
  run,
}: TabProps & { rows: NegotiatedRate[] | null }) {
  const [kind, setKind] = useState("TARIFF");
  const [code, setCode] = useState("");
  const [rate, setRate] = useState("");
  const { page, setPage, pageCount, total, slice } = usePaged(rows ?? [], 15);

  const canSave = kind.trim() !== "" && code.trim() !== "" && rate !== "" && !busy;

  const upsert = () =>
    run(
      "negotiated.upsert",
      () =>
        api.upsertNegotiated({
          kind: kind.trim(),
          code: code.trim(),
          rate: Number(rate),
        }),
      `Rate for ${code.trim()} saved.`,
    );

  return (
    <div className="space-y-4">
      <Card
        title="Add / update negotiated rate"
        sub="Negotiated ENFORCEABLE rates (RAF↔provider agreements) that OVERRIDE the gazetted RPL / SEP reference: for these codes the engine prices payable = min(billed, negotiated). Kind is the code namespace (TARIFF / NAPPI); saving an existing kind + code overwrites its rate. This is the lever the Coding negotiation-targets tab points at."
      >
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Kind
            </label>
            <input
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className={inputCls}
              placeholder="TARIFF"
            />
          </div>
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Code
            </label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className={inputCls}
              placeholder="4301"
            />
          </div>
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Rate
            </label>
            <input
              type="number"
              value={rate}
              onChange={(e) => setRate(e.target.value)}
              className={`tnum ${inputCls}`}
              placeholder="0"
            />
          </div>
          <button onClick={upsert} disabled={!canSave} className={primaryBtn}>
            {busyKey === "negotiated.upsert" ? "Saving…" : "Save rate"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Save upserts the negotiated rate for that kind + code — audit-logged. It
          becomes the reference the pay-min rule uses for those lines.
        </p>
      </Card>

      <Card
        title="Negotiated rates"
        sub="The ENFORCEABLE overrides in force, one row per kind + code. For a listed code the engine caps payable at the negotiated rate instead of the gazetted RPL / SEP. Deleting a row drops the override — the line reverts to the gazetted reference."
      >
        {rows === null ? (
          <Loading label="Loading negotiated rates…" />
        ) : rows.length === 0 ? (
          <Empty label="No negotiated rates." />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className={`${th} text-left`}>Kind</th>
                    <th className={`${th} text-left`}>Code</th>
                    <th className={`${th} text-right`}>Rate</th>
                    <th className={`${th} text-right`}>Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {slice.map((r) => (
                    <tr
                      key={`${r.kind}:${r.code}`}
                      className="align-middle hover:bg-slate-50"
                    >
                      <td className="px-3 py-2 text-slate-700">{r.kind}</td>
                      <td className="px-3 py-2 font-mono text-[13px] text-slate-900">
                        {r.code}
                      </td>
                      <td className="tnum px-3 py-2 text-right font-medium text-slate-800">
                        {rand(r.rate)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={() =>
                            run(
                              `negotiated.delete.${r.kind}:${r.code}`,
                              () => api.deleteNegotiated(r.kind, r.code),
                              `Rate for ${r.code} deleted.`,
                            )
                          }
                          disabled={busy}
                          className={dangerBtn}
                        >
                          {busyKey === `negotiated.delete.${r.kind}:${r.code}`
                            ? "…"
                            : "delete"}
                        </button>
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
              unit="rates"
            />
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Pre-auth code classes ────────────────────────────────────────────────────
// Codes that require pre-authorisation (ENFORCEABLE ruleset tier). Add / remove
// only — a code is either in the pre-auth set or it isn't.
function PreauthTab({
  rows,
  busy,
  busyKey,
  run,
}: TabProps & { rows: string[] | null }) {
  const [code, setCode] = useState("");
  const { page, setPage, pageCount, total, slice } = usePaged(rows ?? [], 24);

  const canAdd = code.trim() !== "" && !busy;

  const add = () =>
    run(
      "preauth.add",
      () => api.addPreauth(code.trim()),
      `Pre-auth code ${code.trim()} added.`,
    );

  return (
    <div className="space-y-4">
      <Card
        title="Add pre-auth code"
        sub="The set of codes that require pre-authorisation (the ENFORCEABLE ruleset tier, §5f): a line on a pre-auth code with no authorisation is gated (PREAUTH_MISSING). Membership is binary — a code is either in the set or it isn't; adding one puts it in scope for the gate."
      >
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Code
            </label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canAdd) add();
              }}
              className={inputCls}
              placeholder="0600"
            />
          </div>
          <button onClick={add} disabled={!canAdd} className={primaryBtn}>
            {busyKey === "preauth.add" ? "Adding…" : "Add code"}
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Add puts the code in the pre-auth set — audit-logged. From then on, a
          line on it without authorisation is gated.
        </p>
      </Card>

      <Card
        title="Pre-auth codes"
        sub="The codes currently in the pre-auth set — the members the engine gates on. Remove (✕) takes a code out of the set; lines on it no longer require authorisation."
      >
        {rows === null ? (
          <Loading label="Loading pre-auth codes…" />
        ) : rows.length === 0 ? (
          <Empty label="No pre-auth codes configured." />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="flex flex-wrap gap-2 p-4">
              {slice.map((c) => (
                <span
                  key={c}
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 py-1 pl-2.5 pr-1.5 font-mono text-[13px] text-slate-800"
                >
                  {c}
                  <button
                    onClick={() =>
                      run(
                        `preauth.remove.${c}`,
                        () => api.removePreauth(c),
                        `Pre-auth code ${c} removed.`,
                      )
                    }
                    disabled={busy}
                    title={`Remove ${c}`}
                    className="rounded px-1 text-slate-400 transition hover:bg-rose-100 hover:text-rose-600 disabled:opacity-40"
                  >
                    {busyKey === `preauth.remove.${c}` ? "…" : "✕"}
                  </button>
                </span>
              ))}
            </div>
            <Pagination
              page={page}
              pageCount={pageCount}
              total={total}
              onPage={setPage}
              unit="codes"
            />
          </div>
        )}
      </Card>
    </div>
  );
}

// ── Audit log ────────────────────────────────────────────────────────────────
function AuditTab({ rows }: { rows: AdminAuditRow[] | null }) {
  const { page, setPage, pageCount, total, slice } = usePaged(rows ?? [], 25);

  return (
    <Card
      title="Audit log"
      sub="The append-only record of every admin mutation on this console — each create / update / delete stamped with actor, action, target, detail and time, newest first. It is written, never edited or deleted: the accountability trail (§9) behind every change to the engine's reference data."
    >
      {rows === null ? (
        <Loading label="Loading audit log…" />
      ) : rows.length === 0 ? (
        <Empty label="No audit entries." />
      ) : (
        <div className="overflow-hidden rounded-md border border-slate-100">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>When</th>
                  <th className={`${th} text-left`}>Actor</th>
                  <th className={`${th} text-left`}>Action</th>
                  <th className={`${th} text-left`}>Target</th>
                  <th className={`${th} text-left`}>Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((r) => (
                  <tr key={r.id} className="align-top hover:bg-slate-50">
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {r.at ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-slate-700">{r.actor}</td>
                    <td className="px-3 py-2">
                      <CodePill>{r.action}</CodePill>
                    </td>
                    <td className="px-3 py-2 font-mono text-[13px] text-slate-900">
                      {r.target}
                    </td>
                    <td className="max-w-md px-3 py-2 font-mono text-[11px] text-slate-500">
                      {JSON.stringify(r.detail)}
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
            unit="entries"
          />
        </div>
      )}
    </Card>
  );
}
