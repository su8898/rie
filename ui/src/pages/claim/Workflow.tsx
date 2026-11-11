// The claim's workflow. Where the claim is on its path from lodgement to payment, the next steps
// available, and the decisions that sit beside the path: merits, the offer, serious-injury
// assessments, undertakings and their invoices, and litigation. Each step says what it does
// before it is taken, and is offered only to the roles that may take it.

import { Check, Plus } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ApiError, api } from "../../api";
import { useAuth } from "../../auth";
import { HOLDS, ROLES, dateTime, humanise, reasonLabel, workError } from "../../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Badge, Button, Checkbox, EmptyState, ErrorBlock, Facts, Field, Input, LoadingBlock, Panel, Ref, Select, Textarea, cx } from "../../ds/primitives";
import { rand } from "../../format";
import type { AwardClass, OfferHeadsInput, UndertakingInvoice, Workflow, WorkflowHistoryEntry } from "../../types";
import { AREAS, GROUNDS, HEADS, PERMS, STAGES, STAGE_PATH, STATUS, STEPS } from "./workflowLabels";

type Pending =
  | { kind: "step"; key: string; subject?: string; run: () => Promise<unknown> }
  | { kind: "merits-accept" } | { kind: "merits-ground"; action: "reject" | "dismiss" }
  | { kind: "offer" } | { kind: "si-new" } | { kind: "undertaking-new" }
  | { kind: "invoice-new"; undertaking: number } | { kind: "adjudicate"; invoice: UndertakingInvoice }
  | null;

const message = (e: unknown, fallback: string) => (e instanceof ApiError ? workError(e.message) : fallback);
const amounts = (text: string) => text.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean).map(Number);
const alertBox = (m: string | null) => m && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{m}</p>;
const statusBadge = (key: string) => { const s = STATUS[key]; return <Badge tone={s?.tone ?? "neutral"} dot>{s?.label ?? humanise(key.split(".")[1] ?? key)}</Badge>; };

export default function ClaimWorkflow({ claimId, claimType }: { claimId: string; claimType: string }) {
  const toast = useToast();
  const { user } = useAuth();
  const [wf, setWf] = useState<Workflow | null>(null);
  const [history, setHistory] = useState<WorkflowHistoryEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending>(null);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [classes, setClasses] = useState<AwardClass[]>([]);
  // form state, one object per dialog
  const [fault, setFault] = useState("0");
  const [ground, setGround] = useState("S19_EXCLUSION");
  const [si, setSi] = useState({ list_match: false, wpi: "", narrative: false });
  const [ut, setUt] = useState({ origin: "SETTLEMENT" as "SETTLEMENT" | "EMERGENCY", scope: "" });
  const [inv, setInv] = useState({ billed: "", dx: "" });
  const [approved, setApproved] = useState("");
  const [offer, setOffer] = useState({ loe: false, loeYears: "", los: false, losYears: "", gd: false, proposed: "", injury: "", severity: "", from: "", to: "", fun: false, necessary: "", other: "" });

  const load = useCallback(async () => {
    setError(null);
    try {
      const [w, h] = await Promise.all([api.workflow(claimId), api.workflowHistory(claimId)]);
      setWf(w); setHistory(h);
    } catch (e) {
      setError(message(e, "The workflow could not be loaded."));
    }
  }, [claimId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { api.awardClasses().then(setClasses).catch(() => setClasses([])); }, []);

  if (error) return <ErrorBlock message={error} onRetry={load} />;
  if (!wf) return <LoadingBlock />;

  const role = user?.role;
  const can = (key: string) => role === "ADMIN" || !PERMS[key] || (role !== undefined && PERMS[key].includes(role));
  const who = (key: string) => `Only ${(PERMS[key] ?? []).concat("ADMIN").filter((r, i, a) => a.indexOf(r) === i).map((r) => ROLES[r]?.label.toLowerCase() ?? r).join(" or ")} users can do this.`;
  const open = (p: Pending) => { setAttempted(false); setFormError(null); setPending(p); };
  const step = (key: string, run: () => Promise<unknown>, subject?: string) => open({ kind: "step", key, subject, run });

  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true);
    setFormError(null);
    try {
      await fn();
      toast.success(done);
      setPending(null);
      await load();
    } catch (e) {
      setFormError(message(e, "The step could not be completed."));
    } finally {
      setBusy(false);
    }
  }

  /** One button per available action, greyed out with the reason when the role may not take it. */
  const StepButtons = ({ area, actions, onStep, skip = [] }: { area: string; actions: string[]; onStep: (a: string) => void; skip?: string[] }) => (
    <div className="flex flex-wrap gap-2">
      {actions.filter((a) => !skip.includes(a)).map((a, i) => {
        const key = `${area}.${a}`;
        const s = STEPS[key];
        return <Button key={a} size="sm" variant={s?.danger ? "secondary" : i === 0 ? "primary" : "secondary"} disabled={!can(key)} title={can(key) ? s?.help : who(key)} onClick={() => onStep(a)}>{s?.label ?? humanise(a)}</Button>;
      })}
    </div>
  );
  const AddButton = ({ permKey, children, onClick }: { permKey: string; children: ReactNode; onClick: () => void }) => (
    <Button size="sm" icon={Plus} disabled={!can(permKey)} title={can(permKey) ? undefined : who(permKey)} onClick={onClick}>{children}</Button>
  );

  // ── lifecycle ──
  const lc = wf.lifecycle;
  const onPath = lc ? STAGE_PATH.indexOf(lc.stage) : -1;
  const m = wf.merits;
  const o = wf.offer;
  const tiers = classes.find((c) => c.injury_class === offer.injury)?.severity_tiers ?? [];

  // ── offer form ──
  const offerErrors = {
    none: !(offer.loe || offer.los || offer.gd || offer.fun) ? "Tick at least one head of damage." : null,
    loe: offer.loe && (amounts(offer.loeYears).length === 0 || amounts(offer.loeYears).some((n) => !(n >= 0))) ? "Enter one amount per year." : null,
    los: offer.los && (amounts(offer.losYears).length === 0 || amounts(offer.losYears).some((n) => !(n >= 0))) ? "Enter one amount per year." : null,
    gd: offer.gd && !(Number(offer.proposed) > 0) ? "Enter the amount proposed." : offer.gd && !offer.injury && !(Number(offer.from) > 0 && Number(offer.to) >= Number(offer.from)) ? "Choose the injury, or enter the range of comparable awards." : null,
    fun: offer.fun && !(Number(offer.necessary) >= 0 && offer.necessary !== "") ? "Enter the necessary costs." : null,
  };
  function buildOffer() {
    setAttempted(true);
    if (Object.values(offerErrors).some(Boolean)) return;
    const heads: OfferHeadsInput = {};
    if (offer.loe) heads.loss_of_earnings = { annual_losses: amounts(offer.loeYears) };
    if (offer.los) heads.loss_of_support = { annual_losses: amounts(offer.losYears) };
    if (offer.gd) heads.general_damages = offer.injury
      ? { proposed: Number(offer.proposed), injury_class: offer.injury, severity_tier: offer.severity || undefined }
      : { proposed: Number(offer.proposed), band_p25: Number(offer.from), band_p75: Number(offer.to) };
    if (offer.fun) heads.funeral = { necessary_costs: Number(offer.necessary), non_necessary: Number(offer.other) || 0 };
    void run(() => api.buildOffer(claimId, heads), "Offer assembled.");
  }

  const describe = (h: WorkflowHistoryEntry) => {
    const area = AREAS[h.area];
    const s = area ? STEPS[`${area.key}.${h.action}`] : undefined;
    const subject = area && area.key !== "lifecycle" && area.key !== "merits" ? `${area.label} ${h.ref}: ` : area?.key === "merits" ? "Merits: " : "";
    return `${subject}${s?.label ?? humanise(h.action)}`;
  };

  return (
    <div className="space-y-4">
      <Panel title="Where this claim is" description={lc ? STAGES[lc.stage]?.help : "This claim has not entered the workflow."}>
        {!lc ? <p className="text-sm text-ink-500">Nothing has been recorded yet.</p> : (
          <>
            <ol className="flex flex-wrap gap-x-1 gap-y-2" aria-label="Stages">
              {STAGE_PATH.map((s, i) => {
                const done = onPath > i || lc.stage === "FINALIZED";
                const current = lc.stage === s;
                return (
                  <li key={s} className="flex items-center gap-1">
                    <span className={cx("flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[13px]", current ? "border-ink-900 bg-ink-900 font-medium text-white" : done ? "border-ok-line bg-ok-bg text-ok-fg" : "border-line bg-white text-ink-500")} aria-current={current ? "step" : undefined}>
                      {done && !current && <Check size={12} aria-hidden />}{STAGES[s].label}
                    </span>
                    {i < STAGE_PATH.length - 1 && <span className="h-px w-3 bg-line-strong" aria-hidden />}
                  </li>
                );
              })}
            </ol>
            {onPath === -1 && <p className="mt-3 inline-flex rounded-md border border-warn-line bg-warn-bg px-3 py-1.5 text-sm font-medium text-warn-fg">{STAGES[lc.stage]?.label ?? humanise(lc.stage)}</p>}
            <div className="mt-4 border-t border-line pt-3">
              <div className="mb-2 text-xs font-medium text-ink-500">{lc.actions.length ? "Next steps" : "No further steps. This is the end of the path."}</div>
              <StepButtons area="lifecycle" actions={lc.actions} onStep={(a) => step(`lifecycle.${a}`, () => api.lifecycleAction(claimId, a))} />
            </div>
          </>
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Merits" description="Whether the Fund is liable, and the claimant's share of fault." actions={m ? statusBadge(`merits.${m.status}`) : undefined}>
          {!m ? <p className="text-sm text-ink-500">{claimType === "PERSONAL" ? "No merits decision has been opened. Use Open merits above." : "Merits apply to personal claims. A supplier claim follows the claimant's merits."}</p> : (
            <>
              <Facts items={[
                { label: "Claimant's share of fault", value: m.fault_pct == null ? "Not recorded" : <span className="tnum">{m.fault_pct}%</span> },
                { label: "Ground for rejection", value: m.ground ? GROUNDS[m.ground] ?? m.ground : "None" },
              ]} />
              {m.actions.length > 0 && (
                <div className="mt-3 border-t border-line pt-3">
                  <StepButtons area="merits" actions={m.actions} onStep={(a) => {
                    if (a === "accept") { setFault(String(m.fault_pct ?? 0)); open({ kind: "merits-accept" }); }
                    else if (a === "reject" || a === "dismiss") { setGround(m.ground ?? "S19_EXCLUSION"); open({ kind: "merits-ground", action: a }); }
                    else step(`merits.${a}`, () => api.meritsAction(claimId, a, {}));
                  }} />
                </div>
              )}
            </>
          )}
        </Panel>

        <Panel
          title="Offer" description="The heads of damage assembled for settlement." flush
          actions={<div className="flex items-center gap-2">{o && statusBadge(`offer.${o.status}`)}<AddButton permKey="offer.build" onClick={() => open({ kind: "offer" })}>{o ? "Rebuild" : "Build offer"}</AddButton></div>}
        >
          {!o ? <EmptyState title="No offer yet" body="Build the offer once the amounts for each head of damage are known." /> : (
            <>
              <table className="min-w-full border-collapse text-sm">
                <tbody className="divide-y divide-line">
                  {o.heads.map((h) => <tr key={h.head}><td className="px-4 py-2 text-ink-800">{HEADS[h.head] ?? humanise(h.head)}</td><td className="tnum px-4 py-2 text-right text-ink-900">{rand(h.amount)}</td></tr>)}
                  <tr className="bg-ink-50/50 font-semibold"><td className="px-4 py-2 text-ink-900">Offer total</td><td className="tnum px-4 py-2 text-right text-ink-900">{rand(o.total)}</td></tr>
                </tbody>
              </table>
              {o.gated_by.length > 0 && (
                <div className="border-t border-line px-4 py-3 text-sm text-warn-fg">
                  <span className="font-medium">The offer is held:</span> {o.gated_by.map((g) => HOLDS[g]?.label ?? reasonLabel(g)).join("; ")}.
                </div>
              )}
            </>
          )}
        </Panel>
      </div>

      <Panel
        title="Serious-injury assessments" description="The RAF 4 decision. General damages are payable only once an injury is accepted as serious." flush
        actions={<AddButton permKey="si.create" onClick={() => { setSi({ list_match: false, wpi: "", narrative: false }); open({ kind: "si-new" }); }}>New assessment</AddButton>}
      >
        {wf.serious_injury.length === 0 ? <EmptyState title="No assessment" body="A medical officer opens one when a RAF 4 is received." /> : (
          <ul className="divide-y divide-line">
            {wf.serious_injury.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div>
                  <div className="flex items-center gap-2 text-sm font-medium text-ink-900">Assessment {s.id} {statusBadge(`si.${s.status}`)}</div>
                  <div className="mt-0.5 text-[13px] text-ink-600">
                    {s.list_match ? "On the list of serious injuries" : "Not on the list of serious injuries"} · whole-person impairment {s.wpi == null ? "not recorded" : `${s.wpi}%`} · narrative test {s.narrative ? "met" : "not met"}
                  </div>
                </div>
                <StepButtons area="si" actions={s.actions} onStep={(a) => step(`si.${a}`, () => api.seriousInjuryAction(s.id, a), `Assessment ${s.id}`)} />
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel
        title="Undertakings" description="A promise to pay for future treatment within a stated scope. Providers bill against an active undertaking." flush
        actions={<AddButton permKey="undertaking.create" onClick={() => { setUt({ origin: "SETTLEMENT", scope: "" }); open({ kind: "undertaking-new" }); }}>Issue undertaking</AddButton>}
      >
        {wf.undertakings.length === 0 ? <EmptyState title="No undertaking" body="Issue one when future treatment is to be paid for as it arises." /> : (
          <ul className="divide-y divide-line">
            {wf.undertakings.map((u) => (
              <li key={u.id} className="px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 text-sm font-medium text-ink-900">Undertaking {u.id} {statusBadge(`undertaking.${u.status}`)}</div>
                    <div className="mt-0.5 text-[13px] text-ink-600">{u.origin === "EMERGENCY" ? "Emergency treatment" : "From a settlement"} · covers <Ref>{u.scope_dx.length ? u.scope_dx.join(", ") : "no diagnosis codes"}</Ref></div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <StepButtons area="undertaking" actions={u.actions} onStep={(a) => step(`undertaking.${a}`, () => api.undertakingAction(u.id, a), `Undertaking ${u.id}`)} />
                    {u.status === "ACTIVE" && <AddButton permKey="invoice.submit" onClick={() => { setInv({ billed: "", dx: u.scope_dx[0] ?? "" }); open({ kind: "invoice-new", undertaking: u.id }); }}>Invoice</AddButton>}
                  </div>
                </div>
                {u.invoices.length > 0 && (
                  <div className="mt-3 overflow-x-auto rounded-md border border-line">
                    <table className="min-w-full border-collapse text-sm">
                      <thead><tr className="border-b border-line bg-ink-50/70 text-left text-xs text-ink-500"><th className="px-3 py-2 font-medium">Invoice</th><th className="px-3 py-2 text-right font-medium">Billed</th><th className="px-3 py-2 text-right font-medium">Payable</th><th className="px-3 py-2 font-medium">Status</th><th className="px-3 py-2" /></tr></thead>
                      <tbody className="divide-y divide-line">
                        {u.invoices.map((i) => (
                          <tr key={i.id} className="align-top">
                            <td className="px-3 py-2 text-ink-800">Invoice {i.id}</td>
                            <td className="tnum px-3 py-2 text-right text-ink-600">{rand(i.billed)}</td>
                            <td className="tnum px-3 py-2 text-right font-medium text-ink-900">{rand(i.payable)}</td>
                            <td className="px-3 py-2">{statusBadge(`invoice.${i.status}`)}{i.reasons.length > 0 && <div className="mt-1 text-xs text-ink-500">{i.reasons.map(reasonLabel).join("; ")}</div>}</td>
                            <td className="px-3 py-2"><div className="flex justify-end"><StepButtons area="invoice" actions={i.actions} onStep={(a) => a === "adjudicate" ? (setApproved(String(i.billed)), open({ kind: "adjudicate", invoice: i })) : step(`invoice.${a}`, () => api.invoiceAction(i.id, a), `Invoice ${i.id}`)} /></div></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel
        title="Litigation" description="Court matters on this claim." flush
        actions={<AddButton permKey="litigation.create" onClick={() => open({ kind: "step", key: "litigation.create", run: () => api.createLitigation(claimId) })}>Open a matter</AddButton>}
      >
        {wf.litigation.length === 0 ? <EmptyState title="No court matter" body="A legal officer opens one when summons is served." /> : (
          <ul className="divide-y divide-line">
            {wf.litigation.map((l) => (
              <li key={l.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="flex items-center gap-2 text-sm font-medium text-ink-900">Matter {l.id} {statusBadge(`litigation.${l.status}`)}{l.default_judgment && <Badge tone="bad">Default judgment</Badge>}</div>
                <StepButtons area="litigation" actions={l.actions} onStep={(a) => step(`litigation.${a}`, () => api.litigationAction(l.id, a), `Matter ${l.id}`)} />
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Workflow history" description="Every step taken on this claim, with who took it." flush>
        {history.length === 0 ? <EmptyState title="No steps yet" body="Steps are listed here as they are taken." /> : (
          <ol className="divide-y divide-line">
            {history.map((h, i) => (
              <li key={i} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 px-4 py-2.5">
                <span className="text-sm text-ink-900">{describe(h)}</span>
                <span className="text-[13px] text-ink-500">{h.actor} · {dateTime(h.at)}</span>
              </li>
            ))}
          </ol>
        )}
      </Panel>

      {/* one confirmation for every step that needs no further input */}
      {pending?.kind === "step" && (
        <ConfirmDialog
          open onClose={() => setPending(null)} busy={busy} danger={STEPS[pending.key]?.danger}
          title={pending.key === "litigation.create" ? "Open a litigation matter?" : `${STEPS[pending.key]?.label ?? "Take this step"}${pending.subject ? `: ${pending.subject}` : ""}?`}
          description={formError ?? (pending.key === "litigation.create" ? "Records that summons was served on the Fund for this claim." : STEPS[pending.key]?.help)}
          confirmLabel={pending.key === "litigation.create" ? "Open matter" : STEPS[pending.key]?.label ?? "Confirm"}
          onConfirm={() => run(pending.run, pending.key === "litigation.create" ? "Litigation matter opened." : `Recorded: ${(STEPS[pending.key]?.label ?? "step").toLowerCase()}.`)}
        />
      )}

      <Dialog
        open={pending?.kind === "merits-accept"} onClose={() => setPending(null)} title="Accept liability" description={STEPS["merits.accept"].help}
        footer={<><Button onClick={() => setPending(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (fault !== "" && Number(fault) >= 0 && Number(fault) <= 100) void run(() => api.meritsAction(claimId, "accept", { fault_pct: Number(fault) }), "Liability accepted."); }}>Accept liability</Button></>}
      >
        <div className="space-y-3">
          <Field label="Claimant's share of fault (%)" required error={attempted && !(fault !== "" && Number(fault) >= 0 && Number(fault) <= 100) ? "Enter a percentage from 0 to 100." : null} hint="0 means the claimant was not at fault.">
            <Input type="number" min={0} max={100} value={fault} onChange={(e) => setFault(e.target.value)} />
          </Field>
          {alertBox(formError)}
        </div>
      </Dialog>

      <Dialog
        open={pending?.kind === "merits-ground"} onClose={() => setPending(null)}
        title={pending?.kind === "merits-ground" && pending.action === "dismiss" ? "Dismiss the appeal" : "Reject liability"}
        description={pending?.kind === "merits-ground" ? STEPS[`merits.${pending.action}`].help : undefined}
        footer={<><Button onClick={() => setPending(null)}>Cancel</Button><Button variant="danger" loading={busy} onClick={() => pending?.kind === "merits-ground" && run(() => api.meritsAction(claimId, pending.action, { ground }), pending.action === "dismiss" ? "Appeal dismissed." : "Liability rejected.")}>{pending?.kind === "merits-ground" && pending.action === "dismiss" ? "Dismiss appeal" : "Reject liability"}</Button></>}
      >
        <div className="space-y-3">
          <Field label="Ground" required>
            <Select value={ground} onChange={(e) => setGround(e.target.value)}>{Object.entries(GROUNDS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}</Select>
          </Field>
          {alertBox(formError)}
        </div>
      </Dialog>

      <Dialog
        open={pending?.kind === "offer"} onClose={() => setPending(null)} wide title={o ? "Rebuild the offer" : "Build the offer"}
        description="Past medical expenses come from the adjudicated account. Tick the other heads that apply. The statutory cap and the claimant's share of fault are applied for you."
        footer={<><Button onClick={() => setPending(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={buildOffer}>{o ? "Rebuild offer" : "Build offer"}</Button></>}
      >
        <div className="space-y-4">
          <div>
            <Checkbox label="Loss of earnings" checked={offer.loe} onChange={(e) => setOffer({ ...offer, loe: e.target.checked })} />
            {offer.loe && <Field label="Loss for each year (R)" required error={attempted ? offerErrors.loe : null} hint="One amount per year, separated by commas or new lines. Each year is capped separately." className="mt-2"><Textarea rows={2} className="font-mono text-xs" value={offer.loeYears} onChange={(e) => setOffer({ ...offer, loeYears: e.target.value })} placeholder="100000, 100000, 100000" /></Field>}
          </div>
          <div>
            <Checkbox label="Loss of support" checked={offer.los} onChange={(e) => setOffer({ ...offer, los: e.target.checked })} />
            {offer.los && <Field label="Loss for each year (R)" required error={attempted ? offerErrors.los : null} hint="One amount per year." className="mt-2"><Textarea rows={2} className="font-mono text-xs" value={offer.losYears} onChange={(e) => setOffer({ ...offer, losYears: e.target.value })} placeholder="120000, 120000" /></Field>}
          </div>
          <div>
            <Checkbox label="General damages" hint="Payable only once the injury is accepted as serious." checked={offer.gd} onChange={(e) => setOffer({ ...offer, gd: e.target.checked })} />
            {offer.gd && (
              <div className="mt-2 grid gap-3 sm:grid-cols-3">
                <Field label="Amount proposed (R)" required error={attempted ? offerErrors.gd : null} className="sm:col-span-3"><Input type="number" min={0} value={offer.proposed} onChange={(e) => setOffer({ ...offer, proposed: e.target.value })} /></Field>
                <Field label="Injury" hint="Compared with past awards for this injury." className="sm:col-span-2">
                  <Select value={offer.injury} onChange={(e) => setOffer({ ...offer, injury: e.target.value, severity: "" })}>
                    <option value="">Enter the range by hand</option>
                    {classes.map((c) => <option key={c.injury_class} value={c.injury_class}>{humanise(c.injury_class)}</option>)}
                  </Select>
                </Field>
                {offer.injury ? (
                  <Field label="Severity"><Select value={offer.severity} onChange={(e) => setOffer({ ...offer, severity: e.target.value })}><option value="">Any</option>{tiers.map((t) => <option key={t} value={t}>{humanise(t)}</option>)}</Select></Field>
                ) : <div className="hidden sm:block" />}
                {!offer.injury && (
                  <>
                    <Field label="Comparable awards, from (R)"><Input type="number" min={0} value={offer.from} onChange={(e) => setOffer({ ...offer, from: e.target.value })} /></Field>
                    <Field label="To (R)"><Input type="number" min={0} value={offer.to} onChange={(e) => setOffer({ ...offer, to: e.target.value })} /></Field>
                  </>
                )}
              </div>
            )}
          </div>
          <div>
            <Checkbox label="Funeral expenses" checked={offer.fun} onChange={(e) => setOffer({ ...offer, fun: e.target.checked })} />
            {offer.fun && (
              <div className="mt-2 grid gap-3 sm:grid-cols-2">
                <Field label="Necessary costs (R)" required error={attempted ? offerErrors.fun : null}><Input type="number" min={0} value={offer.necessary} onChange={(e) => setOffer({ ...offer, necessary: e.target.value })} /></Field>
                <Field label="Other costs claimed (R)" hint="Not payable. Recorded and flagged."><Input type="number" min={0} value={offer.other} onChange={(e) => setOffer({ ...offer, other: e.target.value })} /></Field>
              </div>
            )}
          </div>
          {attempted && offerErrors.none && alertBox(offerErrors.none)}
          {alertBox(formError)}
        </div>
      </Dialog>

      <Dialog
        open={pending?.kind === "si-new"} onClose={() => setPending(null)} title="New serious-injury assessment" description="Record what the RAF 4 report says. A medical officer then accepts or rejects it."
        footer={<><Button onClick={() => setPending(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (si.wpi === "" || (Number(si.wpi) >= 0 && Number(si.wpi) <= 100)) void run(() => api.createSeriousInjury({ claim_id: claimId, list_match: si.list_match, wpi: si.wpi === "" ? null : Number(si.wpi), narrative: si.narrative }), "Assessment opened."); }}>Open assessment</Button></>}
      >
        <div className="space-y-3">
          <Checkbox label="The injury is on the list of serious injuries" checked={si.list_match} onChange={(e) => setSi({ ...si, list_match: e.target.checked })} />
          <Field label="Whole-person impairment (%)" hint="30% or more qualifies as serious. Leave blank if not assessed." error={attempted && si.wpi !== "" && !(Number(si.wpi) >= 0 && Number(si.wpi) <= 100) ? "Enter a percentage from 0 to 100." : null}>
            <Input type="number" min={0} max={100} value={si.wpi} onChange={(e) => setSi({ ...si, wpi: e.target.value })} />
          </Field>
          <Checkbox label="The narrative test is met" hint="Serious long-term impairment, disfigurement or mental disturbance." checked={si.narrative} onChange={(e) => setSi({ ...si, narrative: e.target.checked })} />
          {alertBox(formError)}
        </div>
      </Dialog>

      <Dialog
        open={pending?.kind === "undertaking-new"} onClose={() => setPending(null)} title="Issue an undertaking" description="It starts as issued. Activate it when providers may begin to bill against it."
        footer={<><Button onClick={() => setPending(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); const scope = ut.scope.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean); if (scope.length) void run(() => api.createUndertaking({ claim_id: claimId, origin: ut.origin, scope_dx: scope }), "Undertaking issued."); }}>Issue undertaking</Button></>}
      >
        <div className="space-y-3">
          <Field label="Arises from" required>
            <Select value={ut.origin} onChange={(e) => setUt({ ...ut, origin: e.target.value as "SETTLEMENT" | "EMERGENCY" })}><option value="SETTLEMENT">A settlement</option><option value="EMERGENCY">Emergency treatment</option></Select>
          </Field>
          <Field label="Diagnosis codes covered" required hint="ICD-10 codes, separated by commas. An invoice for another diagnosis is flagged as out of scope." error={attempted && !ut.scope.trim() ? "Enter at least one diagnosis code." : null}>
            <Input className="font-mono" value={ut.scope} onChange={(e) => setUt({ ...ut, scope: e.target.value })} placeholder="S72, S82" />
          </Field>
          {alertBox(formError)}
        </div>
      </Dialog>

      <Dialog
        open={pending?.kind === "invoice-new"} onClose={() => setPending(null)} title={pending?.kind === "invoice-new" ? `Invoice against undertaking ${pending.undertaking}` : ""} description="The invoice is checked against the undertaking's scope when it is captured."
        footer={<><Button onClick={() => setPending(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (pending?.kind === "invoice-new" && Number(inv.billed) > 0 && inv.dx.trim()) void run(() => api.submitInvoice(pending.undertaking, { billed: Number(inv.billed), dx: inv.dx.trim() }), "Invoice captured."); }}>Capture invoice</Button></>}
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Amount billed (R)" required error={attempted && !(Number(inv.billed) > 0) ? "Enter the amount billed." : null}><Input type="number" min={0} step="0.01" value={inv.billed} onChange={(e) => setInv({ ...inv, billed: e.target.value })} /></Field>
          <Field label="Diagnosis code" required error={attempted && !inv.dx.trim() ? "Enter the diagnosis code." : null}><Input className="font-mono" value={inv.dx} onChange={(e) => setInv({ ...inv, dx: e.target.value })} /></Field>
          {formError && <div className="sm:col-span-2">{alertBox(formError)}</div>}
        </div>
      </Dialog>

      <Dialog
        open={pending?.kind === "adjudicate"} onClose={() => setPending(null)} title={pending?.kind === "adjudicate" ? `Adjudicate invoice ${pending.invoice.id}` : ""} description={pending?.kind === "adjudicate" ? `Billed ${rand(pending.invoice.billed)}. Record the amount approved after checking it.` : undefined}
        footer={<><Button onClick={() => setPending(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (pending?.kind === "adjudicate" && approved !== "" && Number(approved) >= 0 && Number(approved) <= pending.invoice.billed) void run(() => api.adjudicateInvoice(pending.invoice.id, Number(approved)), "Invoice adjudicated."); }}>Save adjudication</Button></>}
      >
        <div className="space-y-3">
          <Field label="Amount approved (R)" required error={attempted && pending?.kind === "adjudicate" && !(approved !== "" && Number(approved) >= 0 && Number(approved) <= pending.invoice.billed) ? "Enter an amount from zero up to the amount billed." : null}>
            <Input type="number" min={0} step="0.01" value={approved} onChange={(e) => setApproved(e.target.value)} />
          </Field>
          {alertBox(formError)}
        </div>
      </Dialog>
    </div>
  );
}
