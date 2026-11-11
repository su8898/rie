// Negotiated rates: a price agreed for one code that the Fund pays instead of the reference
// tariff. A code that has dated versions is maintained under Dated rates, and says so here.

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { DataTable, type Column } from "../../ds/DataTable";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Button, EmptyState, ErrorBlock, Field, Input, Ref, Select } from "../../ds/primitives";
import { rand } from "../../format";
import type { NegotiatedRate } from "../../types";
import { RecentChanges, SectionHeader, errorText, useList } from "./shared";

const KINDS: Record<string, string> = { TARIFF: "Tariff code", NAPPI: "Medicine or material" };
const key = (r: NegotiatedRate) => `${r.kind}:${r.code}`;

export default function NegotiatedRatesAdmin() {
  const toast = useToast();
  const { rows, loading, error, reload } = useList(api.adminNegotiated, "The negotiated rates could not be loaded.");
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [editing, setEditing] = useState<{ kind: string; code: string; rate: string; existing: boolean } | null>(null);
  const [removing, setRemoving] = useState<NegotiatedRate | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const shown = useMemo(() => rows.filter((r) => (!kind || r.kind === kind) && r.code.toLowerCase().includes(q.trim().toLowerCase())), [rows, q, kind]);
  const open = (r?: NegotiatedRate) => { setAttempted(false); setFormError(null); setEditing(r ? { kind: r.kind, code: r.code, rate: String(r.rate), existing: true } : { kind: "TARIFF", code: "", rate: "", existing: false }); };
  const done = async (message: string) => { toast.success(message); setEditing(null); setRemoving(null); setVersion((v) => v + 1); await reload(); };
  const dated = (m: string) => m.includes("dated versions");

  const codeError = !editing?.code.trim() ? "Enter the code." : !editing.existing && rows.some((r) => r.kind === editing.kind && r.code === editing.code.trim()) ? "That code already has a negotiated rate. Edit it instead." : null;
  const rateError = !(Number(editing?.rate) > 0) ? "Enter the agreed rate in rand." : null;
  async function save() {
    setAttempted(true);
    if (!editing || codeError || rateError) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.upsertNegotiated({ kind: editing.kind, code: editing.code.trim(), rate: Number(editing.rate) });
      await done(`Negotiated rate for ${editing.code.trim()} saved.`);
    } catch (e) {
      const m = errorText(e, "The rate could not be saved.");
      setFormError(dated(m) ? "This code has dated versions, so its rate is maintained under Dated rates." : m);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api.deleteNegotiated(removing.kind, removing.code);
      await done(`Negotiated rate for ${removing.code} removed.`);
    } catch (e) {
      const m = errorText(e, "The rate could not be removed.");
      toast.error(dated(m) ? "This code has dated versions, so it is maintained under Dated rates." : m);
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<NegotiatedRate>[] = [
    { key: "code", header: "Code", render: (r) => <div><Ref className="font-medium text-ink-900">{r.code}</Ref><div className="text-xs text-ink-500">{KINDS[r.kind] ?? r.kind}</div></div> },
    { key: "rate", header: "Agreed rate", align: "right", render: (r) => <span className="tnum font-medium text-ink-900">{rand(r.rate)}</span> },
    { key: "actions", header: "", align: "right", render: (r) => (
      <div className="flex justify-end gap-1">
        <Button size="sm" variant="ghost" icon={Pencil} onClick={() => open(r)}>Edit</Button>
        <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setRemoving(r)}>Remove</Button>
      </div>
    ) },
  ];

  return (
    <div>
      <SectionHeader
        title="Negotiated rates" description={<>A price agreed for one code. The Fund pays it instead of the reference tariff. To give a rate a start date or keep its history, use <Link to="/admin/rates" className="text-brand-700 hover:underline">Dated rates</Link>.</>}
        actions={<Button variant="primary" icon={Plus} onClick={() => open()}>Add rate</Button>}
      />
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-4">
        <Input className="sm:col-span-2" placeholder="Code" aria-label="Search negotiated rates" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select aria-label="Kind" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">Any kind</option>
          {Object.entries(KINDS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </Select>
      </div>
      {error ? <ErrorBlock message={error} onRetry={reload} /> : (
        <DataTable
          columns={columns} rows={shown} rowKey={key} loading={loading}
          empty={<EmptyState title={q || kind ? "No rate matches" : "No negotiated rates"} body={q || kind ? "Change the search or the filter." : "Add a rate when the Fund has agreed a price for a code."} />}
          footer={<span className="text-[13px] text-ink-500">{shown.length} of {rows.length} rates</span>}
        />
      )}
      <RecentChanges area="negotiated" version={version} />

      <Dialog
        open={editing !== null} onClose={() => setEditing(null)} title={editing?.existing ? "Edit negotiated rate" : "Add negotiated rate"} description="Applies to claims received from now on."
        footer={<><Button onClick={() => setEditing(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Save rate</Button></>}
      >
        {editing && (
          <div className="space-y-4">
            <Field label="Kind" required>
              <Select value={editing.kind} disabled={editing.existing} onChange={(e) => setEditing({ ...editing, kind: e.target.value })}>
                {Object.entries(KINDS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </Select>
            </Field>
            <Field label="Code" required error={attempted ? codeError : null} hint={editing.existing ? "The code identifies the rate and cannot be changed." : undefined}>
              <Input className="font-mono" value={editing.code} disabled={editing.existing} invalid={attempted && Boolean(codeError)} onChange={(e) => setEditing({ ...editing, code: e.target.value })} />
            </Field>
            <Field label="Agreed rate (R)" required error={attempted ? rateError : null}>
              <Input type="number" min={0} step="0.01" value={editing.rate} invalid={attempted && Boolean(rateError)} onChange={(e) => setEditing({ ...editing, rate: e.target.value })} />
            </Field>
            {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
          </div>
        )}
      </Dialog>
      <ConfirmDialog
        open={removing !== null} onClose={() => setRemoving(null)} busy={busy} danger title={`Remove the negotiated rate for ${removing?.code ?? ""}?`} confirmLabel="Remove rate"
        description="The code goes back to being priced from the reference tariff." onConfirm={remove}
      />
    </div>
  );
}
