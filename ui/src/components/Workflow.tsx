// Interactive Workflow panel for the claim detail page.
//
// Fetches GET /api/claims/{claim_id}/workflow (the one aggregation endpoint)
// and renders a sub-panel per operational state machine: lifecycle, merits,
// offer, serious injury, undertakings, litigation. Each entity's `actions`
// array is exactly the transitions currently allowed from its state, so we
// render one button per entry. Firing an action POSTs it, then re-fetches the
// whole workflow on success; failures (409 illegal transition / unmet gate,
// 403 wrong role) surface the backend {detail} in a toast.
//
// Buttons the current user's role cannot perform are greyed as a courtesy, but
// role enforcement is the backend's — we always surface its 403 detail.

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { rand } from "../format";
import type {
  LitigationRecord,
  MeritsGround,
  OfferHeadsInput,
  Role,
  SeriousInjuryRecord,
  UndertakingInvoice,
  UndertakingRecord,
  Workflow,
} from "../types";
import {
  Card,
  CodePill,
  StateChip,
  Toast,
} from "./ui";

// ── Role permission map (courtesy graying only; backend is authoritative) ────
// action keys are namespaced "entity.action". ADMIN is a superuser everywhere.
const PERMS: Record<string, Role[]> = {
  // lifecycle
  "lifecycle.validate": ["HANDLER"],
  "lifecycle.reject_compliance": ["HANDLER"],
  "lifecycle.open_merits": ["HANDLER"],
  "lifecycle.accept_merits": ["HANDLER", "LEGAL"],
  "lifecycle.repudiate": ["HANDLER", "LEGAL"],
  "lifecycle.litigate": ["LEGAL"],
  "lifecycle.make_offer": ["HANDLER"],
  "lifecycle.settle": ["HANDLER", "LEGAL"],
  "lifecycle.court_order": ["LEGAL"],
  "lifecycle.pay": ["ADMIN"],
  "lifecycle.finalize": ["HANDLER", "ADMIN"],
  // merits
  "merits.accept": ["HANDLER", "LEGAL"],
  "merits.reject": ["HANDLER", "LEGAL"],
  "merits.appeal": ["LEGAL"],
  "merits.dismiss": ["LEGAL"],
  // serious injury
  "si.create": ["MEDICAL_OFFICER"],
  "si.accept": ["MEDICAL_OFFICER"],
  "si.reject": ["MEDICAL_OFFICER"],
  "si.appeal": ["LEGAL"],
  "si.uphold": ["LEGAL"],
  "si.dismiss": ["LEGAL"],
  // undertaking
  "undertaking.create": ["HANDLER", "MEDICAL_OFFICER"],
  "undertaking.activate": ["HANDLER", "MEDICAL_OFFICER"],
  "undertaking.suspend": ["INVESTIGATOR", "MEDICAL_OFFICER"],
  "undertaking.resume": ["INVESTIGATOR", "MEDICAL_OFFICER"],
  "undertaking.terminate": ["ADMIN", "MEDICAL_OFFICER"],
  "undertaking.lapse": ["ADMIN"],
  // invoice
  "invoice.submit": ["MEDICAL_OFFICER"],
  "invoice.adjudicate": ["MEDICAL_OFFICER"],
  "invoice.approve": ["MEDICAL_OFFICER"],
  "invoice.reject": ["MEDICAL_OFFICER"],
  "invoice.pay": ["ADMIN"],
  // offer
  "offer.build": ["HANDLER"],
  // litigation
  "litigation.create": ["LEGAL"],
  "litigation.plead": ["LEGAL"],
  "litigation.set_trial": ["LEGAL"],
  "litigation.default_judgment": ["LEGAL", "ADMIN"],
  "litigation.settle": ["LEGAL"],
  "litigation.judgment": ["LEGAL"],
  "litigation.order_paid": ["ADMIN"],
  "litigation.close": ["LEGAL", "ADMIN"],
};

const GROUNDS: MeritsGround[] = [
  "S19_EXCLUSION",
  "SOLE_NEGLIGENCE",
  "NO_MVA_NEXUS",
];

// ── Shared action button ─────────────────────────────────────────────────────
type Runner = (key: string, fn: () => Promise<unknown>) => void;

function useCan(role: Role | undefined) {
  return useCallback(
    (permKey: string) => {
      if (!role) return false;
      if (role === "ADMIN") return true;
      const allowed = PERMS[permKey];
      if (!allowed) return true; // unknown action: let the backend decide
      return allowed.includes(role);
    },
    [role],
  );
}

function ActionButton({
  label,
  permKey,
  actionKey,
  busyKey,
  can,
  run,
  fn,
  tone = "default",
}: {
  label: string;
  permKey: string;
  actionKey: string;
  busyKey: string | null;
  can: (k: string) => boolean;
  run: Runner;
  fn: () => Promise<unknown>;
  tone?: "default" | "danger" | "primary";
}) {
  const inFlight = busyKey === actionKey;
  const anyInFlight = busyKey !== null;
  const allowed = can(permKey);
  const base =
    tone === "primary"
      ? "bg-slate-900 text-white hover:bg-slate-800"
      : tone === "danger"
        ? "border border-rose-300 text-rose-700 hover:bg-rose-50"
        : "border border-slate-300 text-slate-700 hover:bg-slate-100";
  return (
    <button
      onClick={() => run(actionKey, fn)}
      disabled={anyInFlight || !allowed}
      title={allowed ? undefined : `Requires role: ${PERMS[permKey]?.join(" / ")}`}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${base}`}
    >
      {inFlight ? "…" : label}
    </button>
  );
}

function labelFor(action: string): string {
  return action.replace(/_/g, " ");
}

// ── Panel wrapper ────────────────────────────────────────────────────────────
function Panel({
  title,
  right,
  children,
}: {
  title: string;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {title}
        </span>
        {right}
      </div>
      <div className="space-y-3 p-4">{children}</div>
    </div>
  );
}

const fieldCls =
  "w-full rounded-md border border-slate-300 px-2 py-1 text-xs outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const microLabel = "mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400";

// ─────────────────────────────────────────────────────────────────────────────
export default function WorkflowPanel({ claimId }: { claimId: string }) {
  const { user } = useAuth();
  const can = useCan(user?.role);
  const [wf, setWf] = useState<Workflow | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [toast, setToast] = useState<{
    message: string;
    tone: "error" | "success";
  } | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.workflow(claimId);
      setWf(data);
      setLoadError(null);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load workflow");
    }
  }, [claimId]);

  useEffect(() => {
    setWf(null);
    void load();
  }, [load]);

  // Fire an action: disable while in flight, refetch + success toast on success,
  // surface the backend {detail} on failure.
  const run = useCallback<Runner>(
    (key, fn) => {
      if (busyKey !== null) return;
      setBusyKey(key);
      fn()
        .then(async () => {
          await load();
          setToast({ message: "Done.", tone: "success" });
        })
        .catch((e) => {
          const msg =
            e instanceof ApiError ? e.message : "Request failed.";
          setToast({ message: msg, tone: "error" });
        })
        .finally(() => setBusyKey(null));
    },
    [busyKey, load],
  );

  if (loadError) {
    return (
      <Card title="Workflow">
        <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
          {loadError}
        </div>
      </Card>
    );
  }
  if (!wf) {
    return (
      <Card title="Workflow">
        <div className="text-sm text-slate-400">Loading workflow…</div>
      </Card>
    );
  }

  const btnProps = { busyKey, can, run };

  return (
    <div>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
        Workflow
      </h2>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <LifecyclePanel wf={wf} claimId={claimId} {...btnProps} />
        <MeritsPanel wf={wf} claimId={claimId} {...btnProps} />
        <OfferPanel wf={wf} claimId={claimId} {...btnProps} />
        <SeriousInjuryPanel wf={wf} claimId={claimId} {...btnProps} />
        <div className="lg:col-span-2">
          <UndertakingPanel wf={wf} claimId={claimId} {...btnProps} />
        </div>
        <LitigationPanel wf={wf} claimId={claimId} {...btnProps} />
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

interface PanelProps {
  wf: Workflow;
  claimId: string;
  busyKey: string | null;
  can: (k: string) => boolean;
  run: Runner;
}

// ── Lifecycle ────────────────────────────────────────────────────────────────
function LifecyclePanel({ wf, claimId, busyKey, can, run }: PanelProps) {
  const lc = wf.lifecycle;
  return (
    <Panel
      title="Lifecycle"
      right={lc ? <StateChip state={lc.stage} /> : undefined}
    >
      {!lc ? (
        <div className="text-sm text-slate-400">
          Not initialised for this claim.
        </div>
      ) : lc.actions.length === 0 ? (
        <div className="text-xs text-slate-400">
          Terminal stage — no further transitions.
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {lc.actions.map((a) => (
            <ActionButton
              key={a}
              label={labelFor(a)}
              permKey={`lifecycle.${a}`}
              actionKey={`lifecycle.${a}`}
              busyKey={busyKey}
              can={can}
              run={run}
              fn={() => api.lifecycleAction(claimId, a)}
            />
          ))}
        </div>
      )}
    </Panel>
  );
}

// ── Merits ───────────────────────────────────────────────────────────────────
function MeritsPanel({ wf, claimId, busyKey, can, run }: PanelProps) {
  const m = wf.merits;
  const [faultPct, setFaultPct] = useState(0);
  const [ground, setGround] = useState<MeritsGround>(GROUNDS[0]);

  return (
    <Panel
      title="Merits"
      right={m ? <StateChip state={m.status} /> : undefined}
    >
      {!m ? (
        <div className="text-sm text-slate-400">
          No merits determination yet.
        </div>
      ) : (
        <>
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
            <div>
              fault:{" "}
              <span className="tnum font-medium text-slate-700">
                {m.fault_pct == null ? "—" : `${m.fault_pct}%`}
              </span>
            </div>
            <div>
              ground:{" "}
              <span className="font-medium text-slate-700">
                {m.ground ?? "—"}
              </span>
            </div>
          </dl>

          {m.actions.length === 0 ? (
            <div className="text-xs text-slate-400">No further actions.</div>
          ) : (
            <div className="space-y-2">
              {/* Inline inputs used by accept (fault_pct) and reject/dismiss (ground). */}
              {m.actions.includes("accept") && (
                <div className="flex items-end gap-2">
                  <div className="w-28">
                    <label className={microLabel}>fault %</label>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={faultPct}
                      onChange={(e) => setFaultPct(Number(e.target.value))}
                      className={`${fieldCls} tnum`}
                    />
                  </div>
                  <ActionButton
                    label="accept"
                    permKey="merits.accept"
                    actionKey="merits.accept"
                    busyKey={busyKey}
                    can={can}
                    run={run}
                    tone="primary"
                    fn={() =>
                      api.meritsAction(claimId, "accept", {
                        fault_pct: faultPct,
                      })
                    }
                  />
                </div>
              )}

              {(m.actions.includes("reject") ||
                m.actions.includes("dismiss")) && (
                <div className="flex items-end gap-2">
                  <div className="w-44">
                    <label className={microLabel}>ground</label>
                    <select
                      value={ground}
                      onChange={(e) =>
                        setGround(e.target.value as MeritsGround)
                      }
                      className={fieldCls}
                    >
                      {GROUNDS.map((g) => (
                        <option key={g} value={g}>
                          {g}
                        </option>
                      ))}
                    </select>
                  </div>
                  {m.actions.includes("reject") && (
                    <ActionButton
                      label="reject"
                      permKey="merits.reject"
                      actionKey="merits.reject"
                      busyKey={busyKey}
                      can={can}
                      run={run}
                      tone="danger"
                      fn={() =>
                        api.meritsAction(claimId, "reject", { ground })
                      }
                    />
                  )}
                  {m.actions.includes("dismiss") && (
                    <ActionButton
                      label="dismiss"
                      permKey="merits.dismiss"
                      actionKey="merits.dismiss"
                      busyKey={busyKey}
                      can={can}
                      run={run}
                      tone="danger"
                      fn={() =>
                        api.meritsAction(claimId, "dismiss", { ground })
                      }
                    />
                  )}
                </div>
              )}

              {/* Any remaining actions (e.g. appeal) with no extra input. */}
              <div className="flex flex-wrap gap-2">
                {m.actions
                  .filter(
                    (a) => !["accept", "reject", "dismiss"].includes(a),
                  )
                  .map((a) => (
                    <ActionButton
                      key={a}
                      label={labelFor(a)}
                      permKey={`merits.${a}`}
                      actionKey={`merits.${a}`}
                      busyKey={busyKey}
                      can={can}
                      run={run}
                      fn={() => api.meritsAction(claimId, a, {})}
                    />
                  ))}
              </div>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

// ── Offer ────────────────────────────────────────────────────────────────────
function OfferPanel({ wf, claimId, busyKey, can, run }: PanelProps) {
  const o = wf.offer;
  const [useLoe, setUseLoe] = useState(false);
  const [annualLosses, setAnnualLosses] = useState("100000, 100000, 100000");
  const [useGd, setUseGd] = useState(false);
  const [proposed, setProposed] = useState(0);
  const [p25, setP25] = useState(0);
  const [p75, setP75] = useState(0);

  function buildOffer() {
    const heads: OfferHeadsInput = {};
    if (useLoe) {
      const losses = annualLosses
        .split(",")
        .map((s) => Number(s.trim()))
        .filter((n) => !Number.isNaN(n));
      heads.loss_of_earnings = { annual_losses: losses };
    }
    if (useGd) {
      heads.general_damages = {
        proposed,
        band_p25: p25,
        band_p75: p75,
      };
    }
    return api.buildOffer(claimId, heads);
  }

  return (
    <Panel
      title="Offer"
      right={o ? <StateChip state={o.status} /> : undefined}
    >
      {o ? (
        <>
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-slate-400">
              offer #{o.offer_id}
            </span>
            <span className="tnum text-lg font-semibold text-slate-900">
              {rand(o.total)}
            </span>
          </div>

          {o.heads.length > 0 && (
            <table className="w-full text-xs">
              <tbody className="divide-y divide-slate-100">
                {o.heads.map((h) => (
                  <tr key={h.head}>
                    <td className="py-1 text-slate-500">
                      {h.head.replace(/_/g, " ")}
                    </td>
                    <td className="tnum py-1 text-right font-medium text-slate-700">
                      {rand(h.amount)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {o.gated_by.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] text-slate-400">gated by</span>
              {o.gated_by.map((g) => (
                <span
                  key={g}
                  className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[11px] text-amber-800"
                >
                  {g}
                </span>
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="text-sm text-slate-400">No offer assembled yet.</div>
      )}

      {/* Build / rebuild form */}
      <div className="mt-1 space-y-2 rounded-md border border-slate-100 bg-slate-50/60 p-3">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          {o ? "Rebuild offer" : "Build offer"}
        </div>

        <label className="flex items-center gap-2 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={useLoe}
            onChange={(e) => setUseLoe(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-slate-300"
          />
          loss of earnings
        </label>
        {useLoe && (
          <div>
            <label className={microLabel}>annual losses (comma-separated)</label>
            <input
              value={annualLosses}
              onChange={(e) => setAnnualLosses(e.target.value)}
              className={`${fieldCls} tnum`}
              placeholder="100000, 100000"
            />
          </div>
        )}

        <label className="flex items-center gap-2 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={useGd}
            onChange={(e) => setUseGd(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-slate-300"
          />
          general damages
        </label>
        {useGd && (
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className={microLabel}>proposed</label>
              <input
                type="number"
                value={proposed}
                onChange={(e) => setProposed(Number(e.target.value))}
                className={`${fieldCls} tnum`}
              />
            </div>
            <div>
              <label className={microLabel}>band p25</label>
              <input
                type="number"
                value={p25}
                onChange={(e) => setP25(Number(e.target.value))}
                className={`${fieldCls} tnum`}
              />
            </div>
            <div>
              <label className={microLabel}>band p75</label>
              <input
                type="number"
                value={p75}
                onChange={(e) => setP75(Number(e.target.value))}
                className={`${fieldCls} tnum`}
              />
            </div>
          </div>
        )}

        <ActionButton
          label={o ? "Rebuild offer" : "Build offer"}
          permKey="offer.build"
          actionKey="offer.build"
          busyKey={busyKey}
          can={can}
          run={run}
          tone="primary"
          fn={buildOffer}
        />
      </div>
    </Panel>
  );
}

// ── Serious injury (RAF 4) ───────────────────────────────────────────────────
function SeriousInjuryPanel({ wf, claimId, busyKey, can, run }: PanelProps) {
  const [listMatch, setListMatch] = useState(false);
  const [wpi, setWpi] = useState(30);
  const [narrative, setNarrative] = useState(false);

  return (
    <Panel title="Serious injury (RAF 4)">
      {wf.serious_injury.length === 0 ? (
        <div className="text-sm text-slate-400">No RAF 4 assessments.</div>
      ) : (
        <ul className="space-y-2">
          {wf.serious_injury.map((si) => (
            <SiRow
              key={si.id}
              si={si}
              busyKey={busyKey}
              can={can}
              run={run}
            />
          ))}
        </ul>
      )}

      <div className="mt-1 space-y-2 rounded-md border border-slate-100 bg-slate-50/60 p-3">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          New RAF 4
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={listMatch}
              onChange={(e) => setListMatch(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-slate-300"
            />
            list match
          </label>
          <div className="w-24">
            <label className={microLabel}>WPI %</label>
            <input
              type="number"
              value={wpi}
              onChange={(e) => setWpi(Number(e.target.value))}
              className={`${fieldCls} tnum`}
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={narrative}
              onChange={(e) => setNarrative(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-slate-300"
            />
            narrative
          </label>
          <ActionButton
            label="Create RAF 4"
            permKey="si.create"
            actionKey="si.create"
            busyKey={busyKey}
            can={can}
            run={run}
            tone="primary"
            fn={() =>
              api.createSeriousInjury({
                claim_id: claimId,
                list_match: listMatch,
                wpi,
                narrative,
              })
            }
          />
        </div>
      </div>
    </Panel>
  );
}

function SiRow({
  si,
  busyKey,
  can,
  run,
}: {
  si: SeriousInjuryRecord;
  busyKey: string | null;
  can: (k: string) => boolean;
  run: Runner;
}) {
  return (
    <li className="rounded-md border border-slate-100 bg-slate-50/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400">#{si.id}</span>
        <StateChip state={si.status} />
        <span className="text-[11px] text-slate-500">
          WPI{" "}
          <span className="tnum font-medium text-slate-700">
            {si.wpi == null ? "—" : `${si.wpi}%`}
          </span>
        </span>
        {si.list_match && (
          <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] text-slate-600">
            list match
          </span>
        )}
        {si.narrative && (
          <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] text-slate-600">
            narrative
          </span>
        )}
      </div>
      {si.actions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {si.actions.map((a) => (
            <ActionButton
              key={a}
              label={labelFor(a)}
              permKey={`si.${a}`}
              actionKey={`si.${si.id}.${a}`}
              busyKey={busyKey}
              can={can}
              run={run}
              tone={a === "reject" || a === "dismiss" ? "danger" : "default"}
              fn={() => api.seriousInjuryAction(si.id, a)}
            />
          ))}
        </div>
      )}
    </li>
  );
}

// ── Undertakings ─────────────────────────────────────────────────────────────
function UndertakingPanel({ wf, claimId, busyKey, can, run }: PanelProps) {
  const [origin, setOrigin] = useState<"SETTLEMENT" | "EMERGENCY">(
    "SETTLEMENT",
  );
  const [scopeDx, setScopeDx] = useState("S72, S82");

  return (
    <Panel title="Undertakings">
      {wf.undertakings.length === 0 ? (
        <div className="text-sm text-slate-400">No undertakings issued.</div>
      ) : (
        <div className="space-y-3">
          {wf.undertakings.map((u) => (
            <UndertakingRow
              key={u.id}
              u={u}
              busyKey={busyKey}
              can={can}
              run={run}
            />
          ))}
        </div>
      )}

      <div className="mt-1 space-y-2 rounded-md border border-slate-100 bg-slate-50/60 p-3">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          Issue undertaking
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-40">
            <label className={microLabel}>origin</label>
            <select
              value={origin}
              onChange={(e) =>
                setOrigin(e.target.value as "SETTLEMENT" | "EMERGENCY")
              }
              className={fieldCls}
            >
              <option value="SETTLEMENT">SETTLEMENT</option>
              <option value="EMERGENCY">EMERGENCY</option>
            </select>
          </div>
          <div className="w-56">
            <label className={microLabel}>scope dx (comma-separated)</label>
            <input
              value={scopeDx}
              onChange={(e) => setScopeDx(e.target.value)}
              className={`${fieldCls} font-mono`}
              placeholder="S72, S82"
            />
          </div>
          <ActionButton
            label="Issue"
            permKey="undertaking.create"
            actionKey="undertaking.create"
            busyKey={busyKey}
            can={can}
            run={run}
            tone="primary"
            fn={() =>
              api.createUndertaking({
                claim_id: claimId,
                origin,
                scope_dx: scopeDx
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
              })
            }
          />
        </div>
      </div>
    </Panel>
  );
}

function UndertakingRow({
  u,
  busyKey,
  can,
  run,
}: {
  u: UndertakingRecord;
  busyKey: string | null;
  can: (k: string) => boolean;
  run: Runner;
}) {
  const [billed, setBilled] = useState(500);
  const [dx, setDx] = useState("");

  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400">#{u.id}</span>
        <StateChip state={u.status} />
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
          {u.origin}
        </span>
        {u.scope_dx.length > 0 && (
          <span className="flex flex-wrap gap-1">
            {u.scope_dx.map((d) => (
              <CodePill key={d}>{d}</CodePill>
            ))}
          </span>
        )}
      </div>

      {u.actions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {u.actions.map((a) => (
            <ActionButton
              key={a}
              label={labelFor(a)}
              permKey={`undertaking.${a}`}
              actionKey={`undertaking.${u.id}.${a}`}
              busyKey={busyKey}
              can={can}
              run={run}
              tone={
                a === "terminate" || a === "lapse" || a === "suspend"
                  ? "danger"
                  : "default"
              }
              fn={() => api.undertakingAction(u.id, a)}
            />
          ))}
        </div>
      )}

      {/* Invoices */}
      <div className="mt-3">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          Invoices
        </div>
        {u.invoices.length === 0 ? (
          <div className="text-xs text-slate-400">No invoices.</div>
        ) : (
          <div className="space-y-1.5">
            {u.invoices.map((inv) => (
              <InvoiceRow
                key={inv.id}
                inv={inv}
                busyKey={busyKey}
                can={can}
                run={run}
              />
            ))}
          </div>
        )}

        {/* Submit invoice (only meaningful against an ACTIVE undertaking; the
            backend enforces the gate and we surface its detail). */}
        {u.status === "ACTIVE" && (
          <div className="mt-2 flex flex-wrap items-end gap-2 rounded border border-dashed border-slate-200 p-2">
            <div className="w-28">
              <label className={microLabel}>billed</label>
              <input
                type="number"
                value={billed}
                onChange={(e) => setBilled(Number(e.target.value))}
                className={`${fieldCls} tnum`}
              />
            </div>
            <div className="w-28">
              <label className={microLabel}>dx</label>
              <input
                value={dx}
                onChange={(e) => setDx(e.target.value)}
                className={`${fieldCls} font-mono`}
                placeholder="S72.0"
              />
            </div>
            <ActionButton
              label="Submit invoice"
              permKey="invoice.submit"
              actionKey={`invoice.submit.${u.id}`}
              busyKey={busyKey}
              can={can}
              run={run}
              fn={() => api.submitInvoice(u.id, { billed, dx })}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function InvoiceRow({
  inv,
  busyKey,
  can,
  run,
}: {
  inv: UndertakingInvoice;
  busyKey: string | null;
  can: (k: string) => boolean;
  run: Runner;
}) {
  const [approved, setApproved] = useState(inv.billed);
  const isAdjudicate = inv.actions.includes("adjudicate");

  return (
    <div className="rounded border border-slate-100 bg-slate-50/60 px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-slate-400">#{inv.id}</span>
        <StateChip state={inv.status} />
        <span className="tnum text-slate-500">
          billed{" "}
          <span className="font-medium text-slate-700">{rand(inv.billed)}</span>
        </span>
        <span className="tnum text-slate-500">
          payable{" "}
          <span className="font-medium text-slate-700">
            {rand(inv.payable)}
          </span>
        </span>
        {inv.reasons.map((r) => (
          <span
            key={r}
            className="rounded bg-rose-100 px-1.5 py-0.5 font-mono text-[10px] text-rose-700"
          >
            {r}
          </span>
        ))}
      </div>

      <div className="mt-1.5 flex flex-wrap items-end gap-2">
        {/* Adjudicate takes an `approved` amount; other transitions are plain. */}
        {isAdjudicate && (
          <div className="w-24">
            <label className={microLabel}>approved</label>
            <input
              type="number"
              value={approved}
              onChange={(e) => setApproved(Number(e.target.value))}
              className={`${fieldCls} tnum`}
            />
          </div>
        )}
        {inv.actions.map((a) =>
          a === "adjudicate" ? (
            <ActionButton
              key={a}
              label="adjudicate"
              permKey="invoice.adjudicate"
              actionKey={`invoice.${inv.id}.adjudicate`}
              busyKey={busyKey}
              can={can}
              run={run}
              fn={() => api.adjudicateInvoice(inv.id, approved)}
            />
          ) : (
            <ActionButton
              key={a}
              label={labelFor(a)}
              permKey={`invoice.${a}`}
              actionKey={`invoice.${inv.id}.${a}`}
              busyKey={busyKey}
              can={can}
              run={run}
              tone={a === "reject" ? "danger" : "default"}
              fn={() => api.invoiceAction(inv.id, a)}
            />
          ),
        )}
      </div>
    </div>
  );
}

// ── Litigation ───────────────────────────────────────────────────────────────
function LitigationPanel({ wf, claimId, busyKey, can, run }: PanelProps) {
  return (
    <Panel title="Litigation">
      {wf.litigation.length === 0 ? (
        <div className="text-sm text-slate-400">No litigation matters.</div>
      ) : (
        <ul className="space-y-2">
          {wf.litigation.map((lit) => (
            <LitRow
              key={lit.id}
              lit={lit}
              busyKey={busyKey}
              can={can}
              run={run}
            />
          ))}
        </ul>
      )}

      <ActionButton
        label="Open litigation"
        permKey="litigation.create"
        actionKey="litigation.create"
        busyKey={busyKey}
        can={can}
        run={run}
        tone="primary"
        fn={() => api.createLitigation(claimId)}
      />
    </Panel>
  );
}

function LitRow({
  lit,
  busyKey,
  can,
  run,
}: {
  lit: LitigationRecord;
  busyKey: string | null;
  can: (k: string) => boolean;
  run: Runner;
}) {
  return (
    <li className="rounded-md border border-slate-100 bg-slate-50/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400">#{lit.id}</span>
        <StateChip state={lit.status} />
        {lit.default_judgment && (
          <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-medium text-rose-700">
            default judgment
          </span>
        )}
      </div>
      {lit.actions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {lit.actions.map((a) => (
            <ActionButton
              key={a}
              label={labelFor(a)}
              permKey={`litigation.${a}`}
              actionKey={`litigation.${lit.id}.${a}`}
              busyKey={busyKey}
              can={can}
              run={run}
              fn={() => api.litigationAction(lit.id, a)}
            />
          ))}
        </div>
      )}
    </li>
  );
}
