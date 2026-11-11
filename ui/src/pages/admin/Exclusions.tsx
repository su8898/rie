// Flat-rate exclusions: tariff codes that are not compared with a flat rate, because the code is
// a percentage of another fee, an item paid at cost, or not a priced service. A line under one of
// them is sent for review instead of being priced. A code is on the list or not: add or remove.

import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../api";
import { DataTable, type Column } from "../../ds/DataTable";
import { shortDate } from "../../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, Ref } from "../../ds/primitives";
import type { Exclusion } from "../../types";
import { RecentChanges, SectionHeader, errorText, useList } from "./shared";

const same = (a: string, b: string) => (a.replace(/^0+/, "") || "0") === (b.replace(/^0+/, "") || "0");

export default function ExclusionsAdmin() {
  const toast = useToast();
  const { rows, loading, error, reload } = useList(api.adminExclusions, "The excluded codes could not be loaded.");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const [code, setCode] = useState("");
  const [reason, setReason] = useState("");
  const [removing, setRemoving] = useState<Exclusion | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const shown = useMemo(() => {
    const text = q.trim().toLowerCase();
    return rows.filter((r) => r.code.toLowerCase().includes(text) || r.reason.toLowerCase().includes(text));
  }, [rows, q]);
  const codeError = !code.trim() ? "Enter the tariff code." : rows.some((r) => same(r.code, code.trim())) ? "That code is already excluded." : null;
  const reasonError = !reason.trim() ? "Say why the code is not priced at a flat rate." : null;
  const done = async (message: string) => { toast.success(message); setAdding(false); setRemoving(null); setVersion((v) => v + 1); await reload(); };

  async function add() {
    setAttempted(true);
    if (codeError || reasonError) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.addExclusion(code.trim(), reason.trim());
      await done(`Code ${code.trim()} is no longer priced at a flat rate.`);
    } catch (e) {
      setFormError(errorText(e, "The code could not be added."));
    } finally {
      setBusy(false);
    }
  }
  async function remove(why: string) {
    if (!removing) return;
    setBusy(true);
    try {
      await api.removeExclusion(removing.code, why);
      await done(`Code ${removing.code} is priced at its tariff rate again.`);
    } catch (e) {
      toast.error(errorText(e, "The code could not be removed."));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<Exclusion>[] = [
    { key: "code", header: "Tariff code", render: (r) => <Ref className="font-medium text-ink-900">{r.code}</Ref> },
    { key: "reason", header: "Why it is excluded", render: (r) => (
      <div>
        <div className="text-ink-800">{r.reason || <span className="text-ink-500">No reason recorded</span>}</div>
        {r.has_rate && <div className="mt-0.5"><Badge tone="warn">A rate is loaded for this code and is not used</Badge></div>}
      </div>
    ) },
    { key: "added", header: "Added", render: (r) => r.origin === "manual"
      ? <div><div className="text-ink-700">{shortDate(r.created_at)}</div><div className="text-xs text-ink-500">by {r.created_by}</div></div>
      : <span className="text-ink-500">Installed with the reference data</span> },
    { key: "actions", header: "", align: "right", render: (r) => <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setRemoving(r)}>Remove</Button> },
  ];

  return (
    <div>
      <SectionHeader
        title="Flat-rate exclusions"
        description="Tariff codes that are not compared with a flat rate: a percentage of another fee, an item paid at cost, or not a priced service. A line under one of these codes is sent for review instead of being priced."
        actions={<Button variant="primary" icon={Plus} onClick={() => { setCode(""); setReason(""); setAttempted(false); setFormError(null); setAdding(true); }}>Exclude a code</Button>}
      />
      <div className="mb-3 rounded-lg border border-line bg-white p-3 shadow-panel"><div className="sm:w-80"><Input placeholder="Tariff code or reason" aria-label="Search excluded codes" value={q} onChange={(e) => setQ(e.target.value)} /></div></div>
      {error ? <ErrorBlock message={error} onRetry={reload} /> : (
        <DataTable
          columns={columns} rows={shown} rowKey={(r) => r.code} loading={loading}
          empty={<EmptyState title={q ? "No code matches" : "No code is excluded"} body={q ? "Change the search." : "Every tariff code with a rate is priced at it."} />}
          footer={<span className="text-[13px] text-ink-500">{shown.length} of {rows.length} codes</span>}
        />
      )}
      <RecentChanges area="non_bench" version={version} />

      <Dialog
        open={adding} onClose={() => setAdding(false)} title="Exclude a code from flat-rate pricing"
        description="From the next claim assessed, a line under this code is sent for review instead of being priced. Claims already decided do not change."
        footer={<><Button onClick={() => setAdding(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={add}>Exclude code</Button></>}
      >
        <div className="space-y-4">
          <Field label="Tariff code" required error={attempted ? codeError : null}>
            <Input className="font-mono" value={code} maxLength={32} invalid={attempted && Boolean(codeError)} onChange={(e) => setCode(e.target.value)} />
          </Field>
          <Field label="Why" required error={attempted ? reasonError : null} hint="For example: assistant fee, a percentage of the surgeon's fee.">
            <Input value={reason} maxLength={300} invalid={attempted && Boolean(reasonError)} onChange={(e) => setReason(e.target.value)} />
          </Field>
          {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
        </div>
      </Dialog>
      <ConfirmDialog
        open={removing !== null} onClose={() => setRemoving(null)} busy={busy} danger onConfirm={remove}
        title={`Remove the exclusion on code ${removing?.code ?? ""}?`} confirmLabel="Remove exclusion"
        description={removing?.has_rate ? "From the next claim assessed, lines under this code are priced at its loaded tariff rate." : "No rate is loaded for this code, so its lines stay unpriced until one is."}
        reason={{ label: "Reason (optional)", placeholder: "For example: the tariff now gives it a flat rate" }}
      />
    </div>
  );
}
