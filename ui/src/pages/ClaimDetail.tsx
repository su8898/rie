// The claim record. A handler opens it to answer three things: can this be paid, how much, and
// what is in the way. The header and the summary row answer those; the tabs hold the evidence —
// each adjudicated line, the documents, the payment trail, the workflow and the history.

import { AlertTriangle, CheckCircle2, Printer, RefreshCcw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import MedicalReports from "./claim/MedicalReports";
import ClaimWorkflow from "./claim/Workflow";
import { DataTable, type Column } from "../ds/DataTable";
import {
  CLAIM_TYPES, claimStatus, DISPOSITIONS, DOCUMENTS, HOLDS, PAYMENT_STATUS, reasonLabel, REQUIRED_DOCUMENTS, RISK, shortDate,
} from "../ds/labels";
import { ConfirmDialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Facts, LoadingBlock, PageHeader, Panel, Ref, Stat, Tabs } from "../ds/primitives";
import { rand } from "../format";
import type { AdjudicatedLine, ClaimDetail, DeterminationSummary, Reason } from "../types";

type Tab = "overview" | "lines" | "documents" | "payments" | "workflow" | "history" | "technical";

const LINE_COLUMNS: Column<AdjudicatedLine>[] = [
  { key: "date", header: "Service date", render: (l) => <span className="whitespace-nowrap">{shortDate(l.service_date)}</span> },
  { key: "provider", header: "Practice", render: (l) => <Ref>{l.provider_id || "—"}</Ref> },
  { key: "code", header: "Code", render: (l) => <span><Ref className="font-medium">{l.code}</Ref> <span className="text-xs text-ink-500">{l.kind === "NAPPI" ? "medicine" : "tariff"}</span></span> },
  { key: "billed", header: "Billed", align: "right", render: (l) => <span className="tnum">{rand(l.billed)}</span> },
  { key: "reference", header: "Reference", align: "right", render: (l) => <span className="tnum text-ink-500">{l.reference == null ? "none" : rand(l.reference)}</span> },
  { key: "paid", header: "Payable", align: "right", render: (l) => <span className="tnum font-semibold">{rand(l.payable)}</span> },
  {
    key: "why", header: "Outcome", width: "30%",
    render: (l) =>
      l.reasons.length === 0 ? <span className="text-ok-fg">Paid as billed</span> : (
        <div className="space-y-0.5">
          {l.reduced > 0 && <div className="tnum text-bad-fg">−{rand(l.reduced)}</div>}
          {l.reasons.map((r) => <div key={r} className="text-ink-700">{reasonLabel(r)}</div>)}
          {l.needs_review && <Badge tone="info">Needs a reviewer</Badge>}
        </div>
      ),
  },
];

const HISTORY_COLUMNS: Column<DeterminationSummary>[] = [
  { key: "when", header: "Determined", render: (h) => shortDate(h.created_at) },
  { key: "status", header: "Status", render: (h) => { const s = claimStatus(h); return <Badge tone={s.tone} dot>{s.label}</Badge>; } },
  { key: "risk", header: "Risk", render: (h) => <Badge tone={RISK[h.band].tone}>{RISK[h.band].label}</Badge> },
  { key: "payable", header: "Payable", align: "right", render: (h) => <span className="tnum font-medium">{rand(h.net_payable)}</span> },
  { key: "findings", header: "Findings", width: "36%", render: (h) => h.reasons.length ? h.reasons.map(reasonLabel).join(", ") : "None" },
  { key: "engine", header: "Engine", render: (h) => <Ref className="text-ink-500">{h.engine_version}</Ref> },
];

export default function ClaimDetailPage() {
  const { id = "" } = useParams();
  const { user } = useAuth();
  const toast = useToast();
  const [data, setData] = useState<ClaimDetail | null>(null);
  const [catalogue, setCatalogue] = useState<Record<string, Reason>>({});
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [detail, reasons] = await Promise.all([api.getClaim(id), api.reasons()]);
      setData(detail);
      setCatalogue(Object.fromEntries(reasons.map((r) => [r.code, r])));
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "There is no claim with that reference." : e instanceof ApiError ? e.message : "The claim could not be loaded.");
    }
  }, [id]);

  useEffect(() => { setData(null); void load(); }, [load]);

  async function redetermine(note: string) {
    setBusy(true);
    try {
      await api.rescoreClaim(id, note);
      toast.success("Claim re-determined against the current reference data.");
      setConfirming(false);
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "The claim could not be re-determined.");
    } finally {
      setBusy(false);
    }
  }

  const crumbs = [{ label: "Work" }, { label: "Claims", to: "/claims" }, { label: id }];
  if (error) return <div><PageHeader crumbs={crumbs} title={<Ref className="text-[26px]">{id}</Ref>} /><ErrorBlock message={error} onRetry={load} /></div>;
  if (!data) return <div><PageHeader crumbs={crumbs} title={<Ref className="text-[26px]">{id}</Ref>} /><LoadingBlock label="Loading claim" /></div>;

  const { claim, determination: d, lines, history, payment, billed, practices } = data;
  const status = claimStatus(d);
  const risk = RISK[d.band];
  const pay = PAYMENT_STATUS[payment.status] ?? { label: payment.status, tone: "neutral" as const };
  const documents = claim?.raw.documents ?? {};
  const required = REQUIRED_DOCUMENTS[claim?.claim_type ?? ""] ?? [];
  const missing = required.filter((k) => !documents[k]);
  const reduced = Math.max(0, billed - d.net_payable);
  const advisory = new Set(d.advisory_signals);

  return (
    <div>
      <PageHeader
        crumbs={crumbs}
        title={<Ref className="text-[26px]">{d.claim_id}</Ref>}
        meta={<><Badge tone={status.tone} dot>{status.label}</Badge><Badge tone={risk.tone}>{risk.label} risk</Badge></>}
        subtitle={claim ? `${CLAIM_TYPES[claim.claim_type] ?? claim.claim_type}, lodged ${shortDate(claim.lodged_on)} for an accident on ${shortDate(claim.accident_date)}.` : "This determination has no claim record."}
        actions={user?.role === "ADMIN" && claim ? <Button icon={RefreshCcw} onClick={() => setConfirming(true)}>Re-determine</Button> : undefined}
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Billed" value={rand(billed)} hint={`${lines.length} line${lines.length === 1 ? "" : "s"}`} />
        <Stat label="Payable" value={rand(d.net_payable)} tone={d.eligible_to_pay ? "ok" : undefined} hint={!d.eligible_to_pay ? "Not payable yet" : Number(d.net_payable) > 0 ? "Cleared for payment" : "Nothing to pay after adjustment"} />
        <Stat label="Reduced" value={reduced > 0 ? rand(reduced) : "None"} tone={reduced > 0 ? "bad" : undefined} hint={reduced > 0 ? "See the Lines tab for each reason" : "Paid as billed"} />
        <Stat label="Payment" value={<span className="text-base">{pay.label}</span>} hint={payment.amount != null ? rand(payment.amount) : undefined} />
      </div>

      <Tabs<Tab>
        value={tab} onChange={setTab}
        tabs={[
          { key: "overview", label: "Overview" }, { key: "lines", label: "Lines", count: lines.length },
          { key: "documents", label: "Documents", count: missing.length || undefined }, { key: "payments", label: "Payments" },
          { key: "workflow", label: "Workflow" }, { key: "history", label: "History", count: history.length }, { key: "technical", label: "Technical" },
        ]}
      />

      <div className="mt-4 animate-rise" key={tab}>
        {tab === "overview" && (
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <Panel title={d.eligible_to_pay ? "Nothing is holding this claim" : "What is holding this claim"} description={d.eligible_to_pay ? undefined : DISPOSITIONS[d.disposition]?.help} flush>
                {d.holds.length === 0 ? (
                  <div className="flex items-center gap-2 px-4 py-4 text-sm text-ok-fg"><CheckCircle2 size={16} /> {Number(d.net_payable) > 0 ? "Every gate is cleared. The claim can go into a payment run." : "Every gate is cleared, but nothing is payable after adjustment. See the Lines tab."}</div>
                ) : (
                  <ul className="divide-y divide-line">
                    {d.holds.map((h) => (
                      <li key={h} className="flex items-start gap-3 px-4 py-3">
                        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warn-fg" />
                        <div>
                          <div className="text-sm font-medium text-ink-900">{HOLDS[h]?.label ?? h.replace(/_/g, " ")}</div>
                          <div className="text-[13px] text-ink-500">{HOLDS[h]?.action ?? "Resolve this before payment."}</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>

              <Panel title="Findings" description="Each rule that fired on this claim, with the basis it rests on." flush>
                {d.reasons.length === 0 ? <EmptyState icon={CheckCircle2} title="No findings" body="No rule fired on this claim." /> : (
                  <ul className="divide-y divide-line">
                    {d.reasons.map((code) => {
                      const meta = catalogue[code];
                      return (
                        <li key={code} className="flex flex-wrap items-start justify-between gap-2 px-4 py-3">
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-ink-900">{reasonLabel(code)}</div>
                            <div className="text-[13px] text-ink-500">{(meta?.basis ?? "").replace(/^§\S+\s*[—-]\s*/, "")}</div>
                            <Ref className="text-xs text-ink-400">{code}</Ref>
                          </div>
                          <div className="flex shrink-0 gap-1.5">
                            {meta?.category === "ADJUSTED" ? <Badge tone="warn">Reduces payment</Badge> : meta?.hard && <Badge tone="bad">Blocks payment</Badge>}
                            {advisory.has(code) && <Badge tone="info">Advisory</Badge>}
                            {meta && !meta.hard && !advisory.has(code) && meta.points > 0 && <Badge>{meta.points} points</Badge>}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </Panel>
            </div>

            <div className="space-y-4">
              <Panel title="Claim">
                <Facts items={[
                  { label: "Type", value: claim ? CLAIM_TYPES[claim.claim_type] ?? claim.claim_type : "—" },
                  { label: "Claimant", value: <Ref>{claim?.party_token ?? "—"}</Ref> },
                  { label: "Accident date", value: shortDate(claim?.accident_date) },
                  { label: "Lodged", value: shortDate(claim?.lodged_on) },
                  { label: "Police case number", value: claim?.raw.case_number_raw ?? "Not supplied" },
                  { label: "Accident record", value: <Link className="text-brand-700 hover:underline" to="/accidents"><Ref>{d.accident_id}</Ref></Link> },
                ]} />
              </Panel>
              <Panel title="Billed by" flush>
                {practices.length === 0 ? <EmptyState title="No practice on this claim" /> : (
                  <ul className="divide-y divide-line">
                    {practices.map((p) => (
                      <li key={p.provider_id} className="flex items-start justify-between gap-2 px-4 py-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-ink-900">{p.practice_name || "Not in the practice register"}</div>
                          <div className="text-xs text-ink-500"><Link to={`/practices/${encodeURIComponent(p.provider_id)}`} className="text-brand-700 hover:underline"><Ref>{p.provider_id}</Ref></Link>{p.discipline ? ` · ${p.discipline}` : ""}</div>
                        </div>
                        {p.known ? <Badge tone={p.may_bill ? "ok" : "bad"}>{p.may_bill ? "Active" : p.status === "DEREGISTERED" ? "Deregistered" : "Suspended"}</Badge> : <Badge tone="warn">Not registered</Badge>}
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </div>
          </div>
        )}

        {tab === "lines" && (
          <DataTable
            columns={LINE_COLUMNS} rows={lines} rowKey={(l) => String(l.id)}
            empty={<EmptyState title="No billing lines" body="This claim carries no medical account." />}
            footer={<div className="tnum flex flex-wrap justify-end gap-x-6 gap-y-1 text-[13px] text-ink-600">
              <span>Billed <strong className="text-ink-900">{rand(billed)}</strong></span>
              <span>Line payable <strong className="text-ink-900">{rand(lines.reduce((s, l) => s + l.payable, 0))}</strong></span>
              <span>Net payable <strong className="text-ink-900">{rand(d.net_payable)}</strong></span>
            </div>}
          />
        )}

        {tab === "documents" && (
          <div className="space-y-4">
            <Panel title="Supporting documents" description={required.length ? `A ${(CLAIM_TYPES[claim?.claim_type ?? ""] ?? "claim").toLowerCase()} needs each of these before it can be paid.` : undefined} flush>
              {required.length === 0 ? <EmptyState title="No checklist for this claim" /> : (
                <ul className="divide-y divide-line">
                  {required.map((k) => (
                    <li key={k} className="flex items-center justify-between px-4 py-3">
                      <span className="text-sm text-ink-900">{DOCUMENTS[k] ?? k}</span>
                      <Badge tone={documents[k] ? "ok" : "bad"} dot>{documents[k] ? "Received" : "Outstanding"}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            <MedicalReports claimId={d.claim_id} />
          </div>
        )}

        {tab === "payments" && (
          <Panel title="Payment" flush>
            <div className="px-4 py-4">
              <Facts items={[
                { label: "Status", value: <Badge tone={pay.tone} dot>{pay.label}</Badge> },
                { label: "Payment run", value: payment.batch_id != null ? <Link className="text-brand-700 hover:underline" to={`/payments/runs/${payment.batch_id}`}>Payment run {payment.batch_id}</Link> : "—" },
                { label: "Amount instructed", value: payment.amount != null ? <span className="tnum">{rand(payment.amount)}</span> : "—" },
                { label: "Cleared for payment", value: d.eligible_to_pay ? "Yes" : "No" },
                { label: "Net payable", value: <span className="tnum">{rand(d.net_payable)}</span> },
              ]} />
            </div>
            <div className="border-t border-line">
              {payment.remittances.length === 0 ? <EmptyState title="No remittance advice yet" body="An advice is issued to the practice when the payment run is paid." /> : (
                <ul className="divide-y divide-line">
                  {payment.remittances.map((ref) => (
                    <li key={ref} className="flex items-center justify-between px-4 py-3">
                      <div><div className="text-sm font-medium text-ink-900">Remittance advice</div><Link to={`/payments/remittances/${encodeURIComponent(ref)}`} className="text-brand-700 hover:underline"><Ref>{ref}</Ref></Link></div>
                      <a href={api.remittancePrintUrl(ref)} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong px-2.5 text-[13px] font-medium text-ink-800 hover:bg-ink-50"><Printer size={14} /> Print</a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Panel>
        )}

        {tab === "workflow" && (claim ? <ClaimWorkflow claimId={d.claim_id} claimType={claim.claim_type} /> : <EmptyState title="No workflow" body="This determination has no claim record." />)}

        {tab === "history" && <DataTable columns={HISTORY_COLUMNS} rows={history} rowKey={(h) => String(h.id)} />}

        {tab === "technical" && (
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Determination record" description="What produced this result. The same inputs under these versions give the same answer.">
              <Facts items={[
                { label: "Engine", value: <Ref>{d.engine_version}</Ref> }, { label: "Ruleset effective", value: d.ruleset_effective },
                { label: "Reference edition", value: d.reference_edition }, { label: "Risk score", value: d.score },
                { label: "Accident corroboration", value: `${d.convergence} of 100` }, { label: "Accident match", value: d.accident_action },
                { label: "Silent signals", value: d.shadow_signals.length ? d.shadow_signals.map(reasonLabel).join(", ") : "None" },
                { label: "Disposition code", value: <Ref>{d.disposition}</Ref> },
              ]} />
            </Panel>
            <Panel title="Submitted record" description="The claim exactly as stored. It is never rewritten.">
              <pre className="max-h-96 overflow-auto rounded-md bg-ink-900 p-3 font-mono text-xs leading-relaxed text-ink-100">{JSON.stringify(claim?.raw ?? {}, null, 2)}</pre>
            </Panel>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={confirming} onClose={() => setConfirming(false)} onConfirm={redetermine} busy={busy}
        title="Re-determine this claim" confirmLabel="Re-determine"
        description="The engine runs again over the stored claim, using today's reference data and signal settings. A new determination is added; the claim itself does not change."
        reason={{ label: "Reason for re-determining", required: true, placeholder: "For example: tariff corrected, or signal promoted" }}
      />
    </div>
  );
}
