// The statutory cap on loss of income and support. Each entry takes effect on its date; the
// engine uses the entry in force on the date of the accident.

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../../api";
import { DataTable, type Column } from "../../ds/DataTable";
import { shortDate } from "../../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input } from "../../ds/primitives";
import { rand } from "../../format";
import type { StatutoryCap } from "../../types";
import { RecentChanges, SectionHeader, errorText, useList } from "./shared";

export default function StatutoryCapAdmin() {
  const toast = useToast();
  const { rows, loading, error, reload } = useList(api.adminCaps, "The statutory cap could not be loaded.");
  const [editing, setEditing] = useState<{ effective_from: string; annual_cap: string; existing: boolean } | null>(null);
  const [removing, setRemoving] = useState<StatutoryCap | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const today = new Date().toISOString().slice(0, 10);
  const sorted = [...rows].sort((a, b) => b.effective_from.localeCompare(a.effective_from));
  const inForce = sorted.find((c) => c.effective_from <= today)?.effective_from;
  const open = (c?: StatutoryCap) => { setAttempted(false); setFormError(null); setEditing(c ? { effective_from: c.effective_from, annual_cap: String(c.annual_cap), existing: true } : { effective_from: "", annual_cap: "", existing: false }); };
  const done = async (message: string) => { toast.success(message); setEditing(null); setRemoving(null); setVersion((v) => v + 1); await reload(); };

  const dateError = !editing?.effective_from ? "Enter the date it takes effect." : !editing.existing && rows.some((c) => c.effective_from === editing.effective_from) ? "There is already an entry for that date. Edit it instead." : null;
  const amountError = !(Number(editing?.annual_cap) > 0) ? "Enter the annual cap in rand." : null;
  async function save() {
    setAttempted(true);
    if (!editing || dateError || amountError) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.upsertCap(editing.effective_from, Number(editing.annual_cap));
      await done(`Statutory cap from ${shortDate(editing.effective_from)} saved.`);
    } catch (e) {
      setFormError(errorText(e, "The cap could not be saved."));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api.deleteCap(removing.effective_from);
      await done("Statutory cap entry removed.");
    } catch (e) {
      toast.error(errorText(e, "The entry could not be removed."));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<StatutoryCap>[] = [
    { key: "from", header: "Takes effect", render: (c) => <span className="font-medium text-ink-900">{shortDate(c.effective_from)}</span> },
    { key: "cap", header: "Annual cap", align: "right", render: (c) => <span className="tnum font-medium text-ink-900">{rand(c.annual_cap)}</span> },
    { key: "state", header: "", render: (c) => c.effective_from === inForce ? <Badge tone="ok" dot>In force today</Badge> : c.effective_from > today ? <Badge tone="info">Not yet in force</Badge> : <Badge>Superseded</Badge> },
    { key: "actions", header: "", align: "right", render: (c) => (
      <div className="flex justify-end gap-1">
        <Button size="sm" variant="ghost" icon={Pencil} onClick={() => open(c)}>Edit</Button>
        <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setRemoving(c)}>Remove</Button>
      </div>
    ) },
  ];

  return (
    <div>
      <SectionHeader
        title="Statutory cap" description="The annual limit on loss of income and loss of support, as gazetted. A claim uses the cap in force on the date of its accident, so earlier entries must stay."
        actions={<Button variant="primary" icon={Plus} onClick={() => open()}>Add cap</Button>}
      />
      {error ? <ErrorBlock message={error} onRetry={reload} /> : (
        <DataTable columns={columns} rows={sorted} rowKey={(c) => c.effective_from} loading={loading} empty={<EmptyState title="No cap recorded" body="Add the gazetted annual cap and the date it takes effect." />} />
      )}
      <RecentChanges area="cap" version={version} />

      <Dialog
        open={editing !== null} onClose={() => setEditing(null)} title={editing?.existing ? "Edit statutory cap" : "Add statutory cap"}
        description={editing?.existing ? "Changing an amount changes what claims with accidents from this date are capped at." : undefined}
        footer={<><Button onClick={() => setEditing(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Save cap</Button></>}
      >
        {editing && (
          <div className="space-y-4">
            <Field label="Takes effect on" required error={attempted ? dateError : null} hint={editing.existing ? "The date identifies the entry and cannot be changed." : undefined}>
              <Input type="date" value={editing.effective_from} disabled={editing.existing} invalid={attempted && Boolean(dateError)} onChange={(e) => setEditing({ ...editing, effective_from: e.target.value })} />
            </Field>
            <Field label="Annual cap (R)" required error={attempted ? amountError : null}>
              <Input type="number" min={0} step="1" value={editing.annual_cap} invalid={attempted && Boolean(amountError)} onChange={(e) => setEditing({ ...editing, annual_cap: e.target.value })} />
            </Field>
            {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
          </div>
        )}
      </Dialog>
      <ConfirmDialog
        open={removing !== null} onClose={() => setRemoving(null)} busy={busy} danger title="Remove this cap entry?" confirmLabel="Remove entry"
        description={removing ? `The cap of ${rand(removing.annual_cap)} from ${shortDate(removing.effective_from)} is removed. Claims with accidents from that date fall back to the entry before it.` : undefined}
        onConfirm={remove}
      />
    </div>
  );
}
