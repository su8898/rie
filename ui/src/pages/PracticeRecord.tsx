// One practice. What the register records about it and whether it may bill, what it has billed
// and been paid, who may sign for it on the provider channel, and every change to its entry.
// A practice number that is billing without an entry opens here too, ready to be added.

import { Ban, CircleSlash, Pencil, Plus, RotateCcw, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, Pager, type Column } from "../ds/DataTable";
import {
  CLAIM_TYPES, PARTY_RATING, PRACTICE_FIELDS, PRACTICE_SETTINGS, PRACTICE_SOURCES, PRACTICE_STATUS, PRACTICE_TYPES,
  REMITTANCE_STATUS, claimStatus, dateTime, shortDate,
} from "../ds/labels";
import { ConfirmDialog, useToast } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Facts, LoadingBlock, PageHeader, Panel, Ref, Stat, Tabs } from "../ds/primitives";
import { rand } from "../format";
import type { ClaimRow, PracticeActivity, PracticeRecord, RemittanceSummary } from "../types";
import { PracticeFormDialog, blankPractice, draftOf } from "./practices/PracticeForm";

type Tab = "overview" | "claims" | "advice" | "channel" | "history";
type StatusChange = "SUSPENDED" | "DEREGISTERED" | "ACTIVE" | null;

const STATUS_DIALOG: Record<Exclude<StatusChange, null>, { title: string; body: string; confirm: string; done: string }> = {
  SUSPENDED: { title: "Suspend this practice?", body: "Claims from this practice are refused until it is reinstated. Claims already decided do not change.", confirm: "Suspend practice", done: "Practice suspended." },
  DEREGISTERED: { title: "Deregister this practice?", body: "Claims from this practice are refused. Use this when the practice no longer exists or has lost its registration.", confirm: "Deregister practice", done: "Practice deregistered." },
  ACTIVE: { title: "Reinstate this practice?", body: "The practice may bill the Fund again from now on.", confirm: "Reinstate practice", done: "Practice reinstated." },
};

function describe(h: PracticeActivity["history"][number]): { title: string; note?: string } {
  const d = h.detail;
  if (h.action === "add") return { title: "Added to the register" };
  if (h.action === "status") {
    const to = PRACTICE_STATUS[String(d.to)]?.label ?? String(d.to);
    const from = PRACTICE_STATUS[String(d.from)]?.label ?? String(d.from);
    return { title: `Status changed from ${from} to ${to}`, note: d.reason ? String(d.reason) : undefined };
  }
  const fields = Object.keys(d).map((k) => PRACTICE_FIELDS[k] ?? k);
  return { title: "Details changed", note: fields.length ? `Recorded: ${fields.join(", ")}` : undefined };
}

export default function PracticeRecordPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const [practice, setPractice] = useState<PracticeRecord | null>(null);
  const [activity, setActivity] = useState<PracticeActivity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [editing, setEditing] = useState<"add" | "edit" | null>(null);
  const [change, setChange] = useState<StatusChange>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [p, a] = await Promise.all([api.practice(id), api.practiceActivity(id)]);
      setPractice(p);
      setActivity(a);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The practice could not be loaded.");
    }
  }, [id]);
  useEffect(() => { setPractice(null); setActivity(null); setTab("overview"); void load(); }, [load]);

  const crumbs = [{ label: "Providers" }, { label: "Practices", to: "/practices" }, { label: id }];
  if (error) return <div><PageHeader crumbs={crumbs} title={`Practice ${id}`} /><ErrorBlock message={error} onRetry={load} /></div>;
  if (!practice || !activity) return <div><PageHeader crumbs={crumbs} title={`Practice ${id}`} /><LoadingBlock /></div>;

  const status = practice.known ? PRACTICE_STATUS[practice.status ?? "ACTIVE"] : null;
  const neverSeen = !practice.known && activity.billing.n_claims === 0;
  const risk = activity.risk;

  async function changeStatus(reason: string) {
    if (!change) return;
    setBusy(true);
    try {
      await api.setPracticeStatus(id, change, reason);
      toast.success(STATUS_DIALOG[change].done);
      setChange(null);
      await load();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "The status could not be changed.");
    } finally {
      setBusy(false);
    }
  }

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "overview", label: "Overview" },
    { key: "claims", label: "Claims", count: activity.billing.n_claims },
    { key: "advice", label: "Remittance advice", count: activity.payments.n_advices },
    { key: "channel", label: "Channel access", count: activity.parties.length },
    { key: "history", label: "History", count: activity.history.length },
  ];

  return (
    <div>
      <PageHeader
        crumbs={crumbs}
        title={practice.known ? practice.practice_name || `Practice ${id}` : `Practice ${id}`}
        meta={<><Ref className="text-ink-500">{id}</Ref>{status ? <Badge tone={status.tone} dot>{status.label}</Badge> : <Badge tone="warn">Not in the register</Badge>}</>}
        subtitle={practice.known
          ? [practice.discipline, PRACTICE_SETTINGS[practice.setting ?? ""], PRACTICE_TYPES[practice.practice_type ?? ""]].filter(Boolean).join(" · ") || "No discipline or setting recorded"
          : neverSeen ? "This practice number is not in the register and has not billed the Fund." : "This practice number is billing the Fund but has no register entry."}
        actions={isAdmin && (
          practice.known ? (
            <>
              <Button icon={Pencil} onClick={() => setEditing("edit")}>Edit details</Button>
              {practice.status === "ACTIVE" && <Button icon={CircleSlash} onClick={() => setChange("SUSPENDED")}>Suspend</Button>}
              {practice.status !== "DEREGISTERED" && <Button variant="danger" icon={Ban} onClick={() => setChange("DEREGISTERED")}>Deregister</Button>}
              {practice.status !== "ACTIVE" && <Button variant="primary" icon={RotateCcw} onClick={() => setChange("ACTIVE")}>Reinstate</Button>}
            </>
          ) : <Button variant="primary" icon={Plus} onClick={() => setEditing("add")}>Add to register</Button>
        )}
      />

      {practice.known && practice.status !== "ACTIVE" && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-bad-line bg-bad-bg px-4 py-3 text-sm text-bad-fg">
          <ShieldAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
          <div><span className="font-medium">This practice cannot bill the Fund.</span> {practice.status_reason ? `Reason: ${practice.status_reason}` : "No reason was recorded."}</div>
        </div>
      )}
      {!practice.known && !neverSeen && (
        <div className="mb-4 flex items-start gap-2 rounded-lg border border-warn-line bg-warn-bg px-4 py-3 text-sm text-warn-fg">
          <ShieldAlert size={16} className="mt-0.5 shrink-0" aria-hidden />
          <div>{practice.may_bill ? "Its claims are accepted as submitted because enforcement is off. Its discipline and setting are taken from each claim." : "Its claims are refused because enforcement is on."} {isAdmin ? "Check the practice and add it to the register." : "An administrator can add it to the register."}</div>
        </div>
      )}

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Claims" value={activity.billing.n_claims} hint={activity.billing.last_service ? `Last service ${shortDate(activity.billing.last_service)}` : activity.billing.n_claims ? "No service dates recorded" : "Has not billed"} />
        <Stat label="Billed" value={rand(activity.billing.billed)} hint={`${activity.billing.n_lines} line${activity.billing.n_lines === 1 ? "" : "s"}`} />
        <Stat label="Paid" value={rand(activity.payments.paid)} tone={activity.payments.paid > 0 ? "ok" : undefined} hint={`${activity.payments.n_advices} remittance advice`} />
        <Stat label="Risk rating" value={risk ? PARTY_RATING[risk.rating]?.label ?? risk.rating : "None"} tone={risk ? PARTY_RATING[risk.rating]?.tone : undefined} hint={risk ? (risk.confidence === "LOW_N" ? "Too few claims to be reliable" : `Score ${risk.score} of 100`) : "No claims to rate"} />
      </div>

      <Tabs<Tab> tabs={tabs} value={tab} onChange={setTab} />

      <div className="mt-4">
        {tab === "overview" && (
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <Panel title="Register entry">
                {practice.known ? (
                  <Facts items={[
                    { label: "Practice number", value: <Ref>{id}</Ref> },
                    { label: "Practice name", value: practice.practice_name || "—" },
                    { label: "Discipline", value: practice.discipline || "—" },
                    { label: "Setting", value: PRACTICE_SETTINGS[practice.setting ?? ""] ?? "—" },
                    { label: "Type", value: PRACTICE_TYPES[practice.practice_type ?? ""] ?? "—" },
                    { label: "Council registration number", value: practice.professional_nr ? <Ref>{practice.professional_nr}</Ref> : "—" },
                    { label: "Details verified", value: practice.verified ? "Yes" : <Badge tone="warn">Not verified</Badge> },
                    { label: "Source", value: PRACTICE_SOURCES[practice.source ?? ""] ?? practice.source ?? "—" },
                    { label: "Last updated", value: `${dateTime(practice.updated_at)}${practice.updated_by ? ` by ${practice.updated_by}` : ""}` },
                    { label: "Notes", value: practice.notes || "—" },
                  ]} />
                ) : <EmptyState title="No register entry" body="Nothing is recorded about this practice number." action={isAdmin ? <Button variant="primary" icon={Plus} onClick={() => setEditing("add")}>Add to register</Button> : undefined} />}
              </Panel>
              <Panel title="What the register decides" description="Applied when a claim arrives, whatever the claim itself says.">
                <ul className="space-y-2 text-sm text-ink-700">
                  <li><span className="font-medium text-ink-900">Whether it may bill.</span> A suspended or deregistered practice is refused.</li>
                  <li><span className="font-medium text-ink-900">How its lines are priced.</span> Lines are priced under the registered discipline, so a practice cannot claim a dearer one.</li>
                  <li><span className="font-medium text-ink-900">Whether a claim is a hospital account.</span> A hospital or emergency-unit setting makes it one.</li>
                </ul>
              </Panel>
            </div>
            <div className="space-y-4">
              <Panel title="Billing risk" description="How this practice's claims compare with similar practices.">
                {risk ? (
                  <>
                    <Facts items={[
                      { label: "Rating", value: <Badge tone={PARTY_RATING[risk.rating]?.tone ?? "neutral"} dot>{PARTY_RATING[risk.rating]?.label ?? risk.rating}</Badge> },
                      { label: "Score", value: <span className="tnum">{risk.score} of 100</span> },
                      { label: "High-risk claims", value: <span className="tnum">{risk.red_rate}%</span> },
                      { label: "Claims with a finding", value: <span className="tnum">{risk.flag_rate}%</span> },
                    ]} />
                    {risk.confidence === "LOW_N" && <p className="mt-3 text-[13px] text-ink-500">Based on {risk.n_claims} claim{risk.n_claims === 1 ? "" : "s"}, which is too few to rely on.</p>}
                    <Link to="/intelligence" className="mt-3 inline-block text-[13px] text-brand-700 hover:underline">Open party intelligence</Link>
                  </>
                ) : <p className="text-sm text-ink-500">This practice has no claims to rate.</p>}
              </Panel>
              <Panel title="Billing period">
                <Facts items={[
                  { label: "First service", value: shortDate(activity.billing.first_service) },
                  { label: "Last service", value: shortDate(activity.billing.last_service) },
                  { label: "Payable on its lines", value: <span className="tnum">{rand(activity.billing.payable)}</span> },
                  { label: "Reduced on advice", value: <span className="tnum">{activity.payments.reduced > 0 ? rand(activity.payments.reduced) : "None"}</span> },
                ]} />
              </Panel>
            </div>
          </div>
        )}

        {tab === "claims" && <PracticeClaims providerId={id} />}
        {tab === "advice" && <PracticeAdvice providerId={id} />}

        {tab === "channel" && (
          <Panel title="Channel access" description="The systems that may submit claims and fetch remittance advice for this practice over the provider channel." flush>
            {activity.parties.length === 0 ? (
              <EmptyState title="No system may act for this practice" body="An administrator registers a provider's own system or its switch under Administration, Channel access." />
            ) : (
              <ul className="divide-y divide-line">
                {activity.parties.map((p) => (
                  <li key={p.party_id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                    <div>
                      <div className="text-sm font-medium text-ink-900">{p.name || p.party_id}</div>
                      <div className="text-[13px] text-ink-500"><Ref>{p.party_id}</Ref> · {p.kind === "SWITCH" ? "Switch" : "Provider system"}{p.all_providers ? " · acts for every practice" : ""}</div>
                    </div>
                    <Badge tone={p.status === "ACTIVE" ? "ok" : "neutral"} dot>{p.status === "ACTIVE" ? "Active" : "Suspended"}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        )}

        {tab === "history" && (
          <Panel title="History" description="Every change to this practice's register entry, with who made it." flush>
            {activity.history.length === 0 ? <EmptyState title="No changes recorded" /> : (
              <ol className="divide-y divide-line">
                {activity.history.map((h, i) => {
                  const { title, note } = describe(h);
                  return (
                    <li key={i} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-ink-900">{title}</div>
                        {note && <div className="text-[13px] text-ink-600">{note}</div>}
                      </div>
                      <div className="text-[13px] text-ink-500">{h.actor} · {dateTime(h.at)}</div>
                    </li>
                  );
                })}
              </ol>
            )}
          </Panel>
        )}
      </div>

      {editing && (
        <PracticeFormDialog
          open mode={editing} initial={practice.known ? draftOf(practice) : blankPractice(id)} onClose={() => setEditing(null)}
          onSaved={(p) => { setEditing(null); if (p.provider_id !== id) navigate(`/practices/${encodeURIComponent(p.provider_id)}`); else void load(); }}
        />
      )}
      {change && (
        <ConfirmDialog
          open onClose={() => setChange(null)} busy={busy} danger={change !== "ACTIVE"}
          title={STATUS_DIALOG[change].title} description={STATUS_DIALOG[change].body} confirmLabel={STATUS_DIALOG[change].confirm}
          reason={{ label: change === "ACTIVE" ? "Reason (optional)" : "Reason", required: change !== "ACTIVE", placeholder: change === "ACTIVE" ? "For example: registration renewed" : "For example: council registration lapsed" }}
          onConfirm={changeStatus}
        />
      )}
    </div>
  );
}

function PracticeClaims({ providerId }: { providerId: string }) {
  const navigate = useNavigate();
  const [rows, setRows] = useState<ClaimRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.claimsWorklist({ provider_id: providerId, sort: "received", direction: "desc", limit: 25, offset: (page - 1) * 25 });
      setRows(res.rows);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The claims could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [providerId, page]);
  useEffect(() => { void load(); }, [load]);

  const columns: Column<ClaimRow>[] = [
    { key: "claim", header: "Claim", render: (r) => <div><Ref className="font-medium text-brand-700">{r.claim_id}</Ref><div className="text-xs text-ink-500">{r.claim_type ? CLAIM_TYPES[r.claim_type] ?? r.claim_type : ""}</div></div> },
    { key: "lodged", header: "Lodged", render: (r) => <span className="text-ink-700">{shortDate(r.lodged_on)}</span> },
    { key: "status", header: "Status", render: (r) => { const s = claimStatus(r); return <Badge tone={s.tone} dot>{s.label}</Badge>; } },
    { key: "billed", header: "Billed", align: "right", render: (r) => <span className="tnum text-ink-600">{rand(r.billed)}</span> },
    { key: "payable", header: "Payable", align: "right", render: (r) => <span className="tnum font-medium text-ink-900">{rand(r.net_payable)}</span> },
  ];
  if (error) return <ErrorBlock message={error} onRetry={load} />;
  return (
    <DataTable
      columns={columns} rows={rows} rowKey={(r) => r.claim_id} loading={loading} onRowClick={(r) => navigate(`/claims/${encodeURIComponent(r.claim_id)}`)}
      empty={<EmptyState title="No claims" body="This practice has not billed the Fund." />}
      footer={<div className="flex flex-wrap items-center justify-between gap-3"><Link to={`/claims?provider_id=${encodeURIComponent(providerId)}`} className="text-[13px] text-brand-700 hover:underline">Open in the claims worklist</Link><div className="grow"><Pager page={page} pageSize={25} total={total} unit="claims" onPage={setPage} /></div></div>}
    />
  );
}

function PracticeAdvice({ providerId }: { providerId: string }) {
  const navigate = useNavigate();
  const [rows, setRows] = useState<RemittanceSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.remittanceSearch({ provider_id: providerId, limit: 25, offset: (page - 1) * 25 });
      setRows(res.rows);
      setTotal(res.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The remittance advice could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [providerId, page]);
  useEffect(() => { void load(); }, [load]);

  const columns: Column<RemittanceSummary>[] = [
    { key: "ref", header: "Advice", render: (r) => <div><Ref className="font-medium text-brand-700">{r.ref}</Ref><div className="text-xs text-ink-500">Issued {dateTime(r.issued_at)}</div></div> },
    { key: "run", header: "Payment run", render: (r) => <span className="tnum text-ink-700">{r.batch_id}</span> },
    { key: "claims", header: "Claims", align: "right", render: (r) => <span className="tnum">{r.n_claims}</span> },
    { key: "billed", header: "Billed", align: "right", render: (r) => <span className="tnum text-ink-600">{rand(r.total_billed)}</span> },
    { key: "paid", header: "Paid", align: "right", render: (r) => <span className="tnum font-medium text-ink-900">{rand(r.total_paid)}</span> },
    { key: "status", header: "Status", render: (r) => <Badge tone={REMITTANCE_STATUS[r.status]?.tone ?? "neutral"} dot>{REMITTANCE_STATUS[r.status]?.label ?? r.status}</Badge> },
  ];
  if (error) return <ErrorBlock message={error} onRetry={load} />;
  return (
    <DataTable
      columns={columns} rows={rows} rowKey={(r) => r.ref} loading={loading} onRowClick={(r) => navigate(`/payments/remittances/${encodeURIComponent(r.ref)}`)}
      empty={<EmptyState title="No remittance advice" body="An advice is issued when a payment run that pays this practice is released." />}
      footer={<Pager page={page} pageSize={25} total={total} unit="advices" onPage={setPage} />}
    />
  );
}
