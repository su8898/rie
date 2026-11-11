// Notifications. The messages the Fund sends claimants about their claim, and each claimant's
// consent to be contacted. A message carries only a claim reference and what to do next, never
// a name, an amount or a diagnosis. Nothing is sent to a claimant who has not agreed.

import { Check, Search, ShieldCheck, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { DataTable, Pager, type Column } from "../ds/DataTable";
import { NOTIFICATION_CHANNELS, NOTIFICATION_STATUS, dateTime, humanise } from "../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../ds/overlays";
import { Badge, Button, Checkbox, EmptyState, ErrorBlock, Field, Input, PageHeader, Ref, Select, Stat } from "../ds/primitives";
import type { Notification, NotificationSearch } from "../types";
import { ViewPills, useListParams } from "./work/shared";

const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

export default function NotificationsPage() {
  const toast = useToast();
  const { value, page, pageSize, set, reset, query } = useListParams();
  const [data, setData] = useState<NotificationSearch | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [marking, setMarking] = useState<{ row: Notification; as: "sent" | "failed" } | null>(null);
  const [busy, setBusy] = useState(false);
  const [consentFor, setConsentFor] = useState<string | null>(null);

  const status = value("status");
  const filterKeys = ["q", "channel", "event"];
  const filtered = filterKeys.some((k) => value(k));
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.notificationSearch({ status, q: value("q"), channel: value("channel"), event: value("event"), limit: pageSize, offset: (page - 1) * pageSize }));
    } catch (e) {
      setError(message(e, "The notifications could not be loaded."));
    } finally {
      setLoading(false);
    }
    // `query` is the whole view, filter and page state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query]);
  useEffect(() => { void load(); }, [load]);

  const c = data?.counts;
  const all = c ? Object.values(c).reduce((s, n) => s + n, 0) : undefined;
  const views = [
    { key: "", label: "All", count: all },
    { key: "PENDING", label: "Waiting to send", count: c?.PENDING },
    { key: "FAILED", label: "Failed", count: c?.FAILED, alert: true },
    { key: "SENT", label: "Sent", count: c?.SENT },
    { key: "SUPPRESSED", label: "Not sent", count: c?.SUPPRESSED },
  ];

  async function mark() {
    if (!marking) return;
    setBusy(true);
    try {
      await (marking.as === "sent" ? api.notifMarkSent(marking.row.id) : api.notifMarkFailed(marking.row.id));
      toast.success(marking.as === "sent" ? "Marked as sent." : "Marked as failed.");
      setMarking(null);
      await load();
    } catch (e) {
      toast.error(message(e, "The status could not be changed."));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<Notification>[] = [
    { key: "when", header: "Created", render: (n) => <span className="tnum whitespace-nowrap text-ink-700">{dateTime(n.created_at)}</span> },
    { key: "claim", header: "Claim", render: (n) => <Link to={`/claims/${encodeURIComponent(n.claim_id)}`} className="font-medium text-brand-700 hover:underline"><Ref>{n.claim_id}</Ref></Link> },
    { key: "message", header: "Message", render: (n) => <div><div className="max-w-[52ch] text-ink-900">{n.body}</div><div className="text-xs text-ink-500">{humanise(n.event)}</div></div> },
    { key: "to", header: "To", render: (n) => (
      <div>
        <div className="text-ink-700">{n.channel === "NONE" ? "No channel" : NOTIFICATION_CHANNELS[n.channel] ?? n.channel}</div>
        {n.party_token && <button className="text-xs text-brand-700 hover:underline" onClick={() => setConsentFor(n.party_token)}><Ref>{n.party_token}</Ref></button>}
      </div>
    ) },
    { key: "status", header: "Status", render: (n) => (
      <div>
        <Badge tone={NOTIFICATION_STATUS[n.status]?.tone ?? "neutral"} dot>{NOTIFICATION_STATUS[n.status]?.label ?? n.status}</Badge>
        {n.sent_at && <div className="mt-1 text-xs text-ink-500">{dateTime(n.sent_at)}</div>}
        {n.status === "SUPPRESSED" && <div className="mt-1 text-xs text-ink-500">No consent on record</div>}
      </div>
    ) },
    { key: "actions", header: "", align: "right", render: (n) => n.status === "PENDING" || n.status === "FAILED" ? (
      <div className="flex justify-end gap-1 whitespace-nowrap">
        <Button size="sm" variant="ghost" icon={Check} onClick={() => setMarking({ row: n, as: "sent" })}>Mark sent</Button>
        {n.status === "PENDING" && <Button size="sm" variant="ghost" icon={X} onClick={() => setMarking({ row: n, as: "failed" })}>Mark failed</Button>}
      </div>
    ) : null },
  ];

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Work" }, { label: "Notifications" }]}
        title="Notifications"
        subtitle="Messages to claimants about their claim. A message carries only the claim reference and what to do next. Nothing is sent to a claimant who has not agreed to be contacted."
        actions={<Button icon={ShieldCheck} onClick={() => setConsentFor("")}>Claimant consent</Button>}
      />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Waiting to send" value={c ? c.PENDING : "…"} tone={c?.PENDING ? "warn" : undefined} />
        <Stat label="Failed" value={c ? c.FAILED : "…"} tone={c?.FAILED ? "bad" : undefined} hint="Check the contact details" />
        <Stat label="Sent" value={c ? c.SENT : "…"} tone="ok" />
        <Stat label="Not sent" value={c ? c.SUPPRESSED : "…"} hint="No consent on record" />
      </div>

      <ViewPills views={views} value={status} label="Status" onChange={(k) => reset(k ? { status: k } : {})} />
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-2 lg:grid-cols-5">
        <Input className="lg:col-span-2" placeholder="Claim, claimant reference or words in the message" aria-label="Search notifications" value={value("q")} onChange={(e) => set({ q: e.target.value })} />
        <Select aria-label="About" value={value("event")} onChange={(e) => set({ event: e.target.value })}>
          <option value="">About anything</option>
          {(data?.events ?? []).map((e) => <option key={e} value={e}>{humanise(e)}</option>)}
        </Select>
        <Select aria-label="Channel" value={value("channel")} onChange={(e) => set({ channel: e.target.value })}>
          <option value="">Any channel</option>
          {Object.entries(NOTIFICATION_CHANNELS).map(([k, label]) => <option key={k} value={k}>{k === "NONE" ? "No channel" : label}</option>)}
        </Select>
        {filtered && <div className="flex items-center"><Button size="sm" variant="ghost" icon={X} onClick={() => set(Object.fromEntries(filterKeys.map((k) => [k, null])))}>Clear filters</Button></div>}
      </div>
      {error ? <ErrorBlock message={error} onRetry={load} /> : (
        <DataTable
          columns={columns} rows={data?.rows ?? []} rowKey={(n) => String(n.id)} loading={loading}
          empty={<EmptyState title={filtered || status ? "No notification matches" : "No notifications yet"} body={filtered || status ? "Change or clear the filters." : "A message is created when a claim reaches a step the claimant should hear about."} />}
          footer={<Pager page={page} pageSize={pageSize} total={data?.total ?? 0} unit="notifications" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
        />
      )}

      <ConfirmDialog
        open={marking !== null} onClose={() => setMarking(null)} busy={busy} danger={marking?.as === "failed"}
        title={marking?.as === "sent" ? "Mark this message as sent?" : "Mark this message as failed?"}
        confirmLabel={marking?.as === "sent" ? "Mark as sent" : "Mark as failed"}
        description={marking ? <>Claim <Ref>{marking.row.claim_id}</Ref>. {marking.as === "sent" ? "Use this when the delivery service confirms it went out." : "Use this when delivery did not succeed. It can be marked as sent later."}</> : undefined}
        onConfirm={mark}
      />
      {consentFor !== null && <ConsentDialog token={consentFor} onClose={() => setConsentFor(null)} />}
    </div>
  );
}

/** Look up and change one claimant's consent to be contacted, and by which channel. */
function ConsentDialog({ token, onClose }: { token: string; onClose: () => void }) {
  const toast = useToast();
  const [ref, setRef] = useState(token);
  const [loaded, setLoaded] = useState<string | null>(null);
  const [channel, setChannel] = useState("NONE");
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lookup = useCallback(async (t: string) => {
    if (!t.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const p = await api.notifPref(t.trim());
      setLoaded(t.trim()); setChannel(p.channel); setAgreed(p.opted_in);
    } catch (e) {
      setError(message(e, "The consent record could not be read."));
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => { if (token) void lookup(token); }, [token, lookup]);

  const channelError = agreed && channel === "NONE" ? "Choose SMS or email, or untick consent." : null;
  async function save() {
    if (!loaded || channelError) return;
    setBusy(true);
    setError(null);
    try {
      await api.setNotifPref(loaded, agreed ? channel : "NONE", agreed);
      toast.success(agreed ? "Consent recorded." : "Consent withdrawn. Messages to this claimant will not be sent.");
      onClose();
    } catch (e) {
      setError(message(e, "The consent could not be saved."));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open onClose={onClose} title="Claimant consent" description="A claimant is contacted only if they have agreed, and only by the channel they chose. The Fund holds the claimant's reference here, not their phone number or address."
      footer={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" loading={busy} disabled={!loaded || Boolean(channelError)} onClick={save}>Save consent</Button></>}
    >
      <div className="space-y-4">
        <Field label="Claimant reference" required>
          <div className="flex gap-2">
            <Input className="font-mono" value={ref} onChange={(e) => { setRef(e.target.value); setLoaded(null); }} onKeyDown={(e) => { if (e.key === "Enter") void lookup(ref); }} />
            <Button icon={Search} loading={busy && !loaded} disabled={!ref.trim()} onClick={() => lookup(ref)}>Look up</Button>
          </div>
        </Field>
        {loaded && (
          <>
            <Checkbox label="The claimant has agreed to be contacted" hint="Untick to withdraw consent. Messages are then recorded but not sent." checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
            <Field label="Channel" error={channelError}>
              <Select value={agreed ? channel : "NONE"} disabled={!agreed} onChange={(e) => setChannel(e.target.value)}>
                <option value="NONE">None</option><option value="SMS">SMS</option><option value="EMAIL">Email</option>
              </Select>
            </Field>
          </>
        )}
        {error && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{error}</p>}
      </div>
    </Dialog>
  );
}
