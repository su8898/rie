// Admin — the ADMIN-only operator console.
//
// Five tabs over the /api/admin surface:
//   • users          — role + active management, plus a create-user form.
//   • signal-modes   — effective-dated SHADOW/ADVISORY/SCORED overrides on the
//                      signal catalogue (Grounded signals are locked SCORED).
//   • caps           — statutory annual-cap schedule (effective-dated).
//   • negotiated     — negotiated tariff / NAPPI rates.
//   • audit          — the admin action log (newest first).
//
// Everything mutating goes through `run(key, fn, okMsg)`: it disables all
// controls while in flight, refetches the affected data, and surfaces the
// backend's 400 {detail} (bad role, Grounded override, …) verbatim via Toast.

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import {
  CodePill,
  Empty,
  ErrorBox,
  Loading,
  MaturityChip,
  ModeChip,
  Pagination,
  Toast,
  YesNo,
  usePaged,
} from "../components/ui";
import { rand } from "../format";
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
  | "audit";

const TABS: { key: Tab; label: string }[] = [
  { key: "users", label: "Users" },
  { key: "signal-modes", label: "Signal modes" },
  { key: "caps", label: "Caps" },
  { key: "preauth", label: "Pre-auth" },
  { key: "negotiated", label: "Negotiated" },
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

const tableShell =
  "overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm";

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
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Admin</h1>
        <span className="text-xs text-slate-400">
          users · statutory config · signal modes · audit
        </span>
      </div>

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
    <div className="space-y-3">
      {/* Create user */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
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

      {users === null ? (
        <Loading label="Loading users…" />
      ) : users.length === 0 ? (
        <Empty label="No users." />
      ) : (
        <div className={tableShell}>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
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
  const { page, setPage, pageCount, total, slice } = usePaged(rows ?? [], 20);
  if (rows === null) return <Loading label="Loading signal modes…" />;
  if (rows.length === 0) return <Empty label="No signals." />;

  return (
    <div className="space-y-2">
      <div className={tableShell}>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
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
      <p className="px-1 text-xs text-slate-400">
        Mode changes are audit-logged, effective-dated reference data — never a
        code deploy.
      </p>
    </div>
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
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
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

      {caps === null ? (
        <Loading label="Loading caps…" />
      ) : caps.length === 0 ? (
        <Empty label="No caps configured." />
      ) : (
        <div className={tableShell}>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
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
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
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

      {rows === null ? (
        <Loading label="Loading negotiated rates…" />
      ) : rows.length === 0 ? (
        <Empty label="No negotiated rates." />
      ) : (
        <div className={tableShell}>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
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
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
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

      {rows === null ? (
        <Loading label="Loading pre-auth codes…" />
      ) : rows.length === 0 ? (
        <Empty label="No pre-auth codes configured." />
      ) : (
        <div className={tableShell}>
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
    </div>
  );
}

// ── Audit log ────────────────────────────────────────────────────────────────
function AuditTab({ rows }: { rows: AdminAuditRow[] | null }) {
  const { page, setPage, pageCount, total, slice } = usePaged(rows ?? [], 25);
  if (rows === null) return <Loading label="Loading audit log…" />;
  if (rows.length === 0) return <Empty label="No audit entries." />;

  return (
    <div className={tableShell}>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
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
  );
}
