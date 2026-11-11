// Channel access: the systems allowed to send claims and fetch remittance advice over the
// provider channel. Each holds a private signing key; the Fund keeps only the public half.

import { KeyRound, ListChecks, Pause, Play, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../api";
import { DataTable, type Column } from "../../ds/DataTable";
import { shortDate } from "../../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, Ref, Select, Textarea } from "../../ds/primitives";
import type { RailsParty } from "../../types";
import { RecentChanges, SectionHeader, errorText, useList } from "./shared";

type Open = { kind: "register" } | { kind: "practices" | "key" | "status"; party: RailsParty } | null;
const KINDS: Record<string, string> = { PROVIDER: "Provider system", SWITCH: "Switch" };
const split = (text: string) => [...new Set(text.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean))];
const acts = (p: RailsParty) => p.providers.includes("*") ? "Every practice" : `${p.providers.length} practice${p.providers.length === 1 ? "" : "s"}`;

export default function ChannelAccessAdmin() {
  const toast = useToast();
  const { rows, loading, error, reload } = useList(api.railsParties, "The channel parties could not be loaded.");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Open>(null);
  const [form, setForm] = useState({ party_id: "", name: "", kind: "PROVIDER", providers: "", jwk: "" });
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const shown = useMemo(() => rows.filter((p) => {
    const needle = q.trim().toLowerCase();
    return !needle || p.party_id.toLowerCase().includes(needle) || p.name.toLowerCase().includes(needle) || p.providers.some((x) => x.toLowerCase().includes(needle));
  }), [rows, q]);
  const start = (o: Open) => {
    setForm({ party_id: "", name: "", kind: "PROVIDER", providers: o && "party" in o ? o.party.providers.join("\n") : "", jwk: "" });
    setAttempted(false);
    setFormError(null);
    setOpen(o);
  };
  async function run(fn: () => Promise<unknown>, done: string) {
    setBusy(true);
    setFormError(null);
    try {
      await fn();
      toast.success(done);
      setOpen(null);
      setVersion((v) => v + 1);
      await reload();
    } catch (e) {
      setFormError(errorText(e, "The change could not be saved."));
    } finally {
      setBusy(false);
    }
  }

  const party = open && "party" in open ? open.party : null;
  const kind = party?.kind ?? form.kind;
  const list = split(form.providers);
  const idError = !/^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/.test(form.party_id.trim()) ? "Use 3 to 64 letters, digits, dots, dashes or underscores." : rows.some((p) => p.party_id === form.party_id.trim()) ? "That identifier is already registered." : null;
  const listError = list.length === 0 ? "List at least one practice number." : list.includes("*") && (kind !== "SWITCH" || list.length > 1) ? "The * (every practice) is for a switch only, and must stand alone." : null;
  const jwkError = (() => {
    if (!form.jwk.trim()) return "Paste the public key.";
    try {
      const k = JSON.parse(form.jwk);
      if (!k || typeof k !== "object") return "This is not a key in JWK form.";
      if ("d" in k) return "This is a private key. Ask the party for its public key only.";
      return null;
    } catch {
      return "This is not valid JSON. Paste the key exactly as it was sent.";
    }
  })();
  const alert = formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>;
  const practicesField = (
    <Field label="Practices it may act for" required error={attempted ? listError : null} hint={kind === "SWITCH" ? "One practice number per line, or * for every practice." : "The practice numbers this system bills under, one per line."}>
      <Textarea rows={4} className="font-mono text-xs" value={form.providers} onChange={(e) => setForm({ ...form, providers: e.target.value })} />
    </Field>
  );
  const keyField = (
    <Field label="Public key (JWK)" required error={attempted ? jwkError : null} hint="The public half of the party's ES256 signing key, as JSON. Never the private key.">
      <Textarea rows={5} className="font-mono text-xs" value={form.jwk} onChange={(e) => setForm({ ...form, jwk: e.target.value })} placeholder={'{"kty":"EC","crv":"P-256","x":"…","y":"…"}'} />
    </Field>
  );

  const columns: Column<RailsParty>[] = [
    { key: "party", header: "System", render: (p) => <div><div className="font-medium text-ink-900">{p.name || p.party_id}</div><Ref className="text-xs text-ink-500">{p.party_id}</Ref></div> },
    { key: "kind", header: "Kind", render: (p) => KINDS[p.kind] ?? p.kind },
    { key: "acts", header: "Acts for", render: (p) => <div><div className="text-ink-800">{acts(p)}</div>{!p.providers.includes("*") && <Ref className="block max-w-[30ch] truncate text-xs text-ink-500">{p.providers.join(", ")}</Ref>}</div> },
    { key: "key", header: "Key fingerprint", render: (p) => <Ref className="text-xs text-ink-600" >{p.key_thumbprint.slice(0, 16)}…</Ref> },
    { key: "status", header: "Status", render: (p) => p.status === "ACTIVE" ? <Badge tone="ok" dot>Active</Badge> : <Badge tone="warn" dot>Suspended</Badge> },
    { key: "since", header: "Registered", render: (p) => <div><div className="text-ink-700">{shortDate(p.created_at)}</div><div className="text-xs text-ink-500">by {p.created_by}</div></div> },
    { key: "actions", header: "", align: "right", render: (p) => (
      <div className="flex justify-end gap-1 whitespace-nowrap">
        <Button size="sm" variant="ghost" icon={ListChecks} onClick={() => start({ kind: "practices", party: p })}>Practices</Button>
        <Button size="sm" variant="ghost" icon={KeyRound} onClick={() => start({ kind: "key", party: p })}>Replace key</Button>
        <Button size="sm" variant="ghost" icon={p.status === "ACTIVE" ? Pause : Play} onClick={() => start({ kind: "status", party: p })}>{p.status === "ACTIVE" ? "Suspend" : "Reactivate"}</Button>
      </div>
    ) },
  ];

  return (
    <div>
      <SectionHeader
        title="Channel access" description="The provider systems and switches that may send claims and fetch remittance advice. Each signs its requests with its own key, so a request shows who sent it. A system is never deleted: suspend it to cut it off."
        actions={<Button variant="primary" icon={Plus} onClick={() => start({ kind: "register" })}>Register a system</Button>}
      />
      <div className="mb-3 rounded-lg border border-line bg-white p-3 shadow-panel"><div className="sm:w-80"><Input placeholder="System, identifier or practice number" aria-label="Search systems" value={q} onChange={(e) => setQ(e.target.value)} /></div></div>
      {error ? <ErrorBlock message={error} onRetry={reload} /> : (
        <DataTable
          columns={columns} rows={shown} rowKey={(p) => p.party_id} loading={loading}
          empty={<EmptyState title={q ? "No system matches" : "No system is registered"} body={q ? "Change the search." : "Register a provider's system or its switch to let it use the channel."} />}
          footer={<span className="text-[13px] text-ink-500">{shown.length} of {rows.length} systems</span>}
        />
      )}
      <RecentChanges area="rails_party" version={version} />

      <Dialog
        open={open?.kind === "register"} onClose={() => setOpen(null)} wide title="Register a system" description="It can use the channel as soon as it is registered."
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (!idError && !listError && !jwkError) void run(() => api.registerRailsParty({ party_id: form.party_id.trim(), name: form.name.trim(), kind: form.kind, providers: list, public_jwk: form.jwk.trim() }), `${form.name.trim() || form.party_id.trim()} registered.`); }}>Register</Button></>}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Identifier" required error={attempted ? idError : null} hint="The key id the system puts on every request.">
            <Input className="font-mono" value={form.party_id} invalid={attempted && Boolean(idError)} onChange={(e) => setForm({ ...form, party_id: e.target.value })} />
          </Field>
          <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Kind" required className="sm:col-span-2" hint={form.kind === "SWITCH" ? "A switch sends claims on behalf of many practices." : "A practice's own billing system."}>
            <Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
              {Object.entries(KINDS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </Select>
          </Field>
          <div className="sm:col-span-2">{practicesField}</div>
          <div className="sm:col-span-2">{keyField}</div>
          {alert && <div className="sm:col-span-2">{alert}</div>}
        </div>
      </Dialog>

      <Dialog
        open={open?.kind === "practices"} onClose={() => setOpen(null)} title={`Practices: ${party?.name || party?.party_id || ""}`} description="The change applies to its next request."
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (party && !listError) void run(() => api.setRailsPartyProviders(party.party_id, list), "Practices saved."); }}>Save practices</Button></>}
      >
        <div className="space-y-3">{practicesField}{alert}</div>
      </Dialog>

      <Dialog
        open={open?.kind === "key"} onClose={() => setOpen(null)} wide title={`Replace key: ${party?.name || party?.party_id || ""}`} description="Requests signed with the old key are refused at once."
        footer={<><Button onClick={() => setOpen(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={() => { setAttempted(true); if (party && !jwkError) void run(() => api.rotateRailsPartyKey(party.party_id, form.jwk.trim()), "Signing key replaced."); }}>Replace key</Button></>}
      >
        <div className="space-y-3">{keyField}{alert}</div>
      </Dialog>

      <ConfirmDialog
        open={open?.kind === "status"} onClose={() => setOpen(null)} busy={busy} danger={party?.status === "ACTIVE"}
        title={party?.status === "ACTIVE" ? `Suspend ${party.name || party.party_id}?` : `Reactivate ${party?.name || party?.party_id || ""}?`}
        description={formError ?? (party?.status === "ACTIVE" ? "Its requests are refused until it is reactivated. Nothing it has already sent is affected." : "It can use the channel again with its registered key.")}
        confirmLabel={party?.status === "ACTIVE" ? "Suspend system" : "Reactivate system"}
        onConfirm={() => party && run(() => api.setRailsPartyStatus(party.party_id, party.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE"), party.status === "ACTIVE" ? "System suspended." : "System reactivated.")}
      />
    </div>
  );
}
