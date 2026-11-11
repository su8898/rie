// Pre-authorisation codes: the tariff codes the Fund pays only when treatment was authorised
// beforehand. A code is either on the list or not, so there is nothing to edit: add or remove.

import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../api";
import { DataTable, type Column } from "../../ds/DataTable";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Button, EmptyState, ErrorBlock, Field, Input, Ref } from "../../ds/primitives";
import { RecentChanges, SectionHeader, errorText, useList } from "./shared";

export default function PreauthCodesAdmin() {
  const toast = useToast();
  const { rows, loading, error, reload } = useList(api.adminPreauth, "The codes could not be loaded.");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const [code, setCode] = useState("");
  const [removing, setRemoving] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const shown = useMemo(() => rows.filter((c) => c.toLowerCase().includes(q.trim().toLowerCase())).map((c) => ({ code: c })), [rows, q]);
  const codeError = !code.trim() ? "Enter the tariff code." : rows.includes(code.trim()) ? "That code is already on the list." : null;
  const done = async (message: string) => { toast.success(message); setAdding(false); setRemoving(null); setVersion((v) => v + 1); await reload(); };

  async function add() {
    setAttempted(true);
    if (codeError) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.addPreauth(code.trim());
      await done(`Code ${code.trim()} now needs pre-authorisation.`);
    } catch (e) {
      setFormError(errorText(e, "The code could not be added."));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api.removePreauth(removing);
      await done(`Code ${removing} no longer needs pre-authorisation.`);
    } catch (e) {
      toast.error(errorText(e, "The code could not be removed."));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<{ code: string }>[] = [
    { key: "code", header: "Tariff code", render: (r) => <Ref className="font-medium text-ink-900">{r.code}</Ref> },
    { key: "actions", header: "", align: "right", render: (r) => <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setRemoving(r.code)}>Remove</Button> },
  ];

  return (
    <div>
      <SectionHeader
        title="Pre-authorisation codes" description="Treatment under these tariff codes is paid only when it was authorised beforehand. A line billed without authorisation is held."
        actions={<Button variant="primary" icon={Plus} onClick={() => { setCode(""); setAttempted(false); setFormError(null); setAdding(true); }}>Add code</Button>}
      />
      <div className="mb-3 rounded-lg border border-line bg-white p-3 shadow-panel"><div className="sm:w-72"><Input placeholder="Tariff code" aria-label="Search codes" value={q} onChange={(e) => setQ(e.target.value)} /></div></div>
      {error ? <ErrorBlock message={error} onRetry={reload} /> : (
        <DataTable
          columns={columns} rows={shown} rowKey={(r) => r.code} loading={loading}
          empty={<EmptyState title={q ? "No code matches" : "No code needs pre-authorisation"} body={q ? "Change the search." : "Add the tariff codes that must be authorised before treatment."} />}
          footer={<span className="text-[13px] text-ink-500">{shown.length} of {rows.length} codes</span>}
        />
      )}
      <RecentChanges area="preauth" version={version} />

      <Dialog
        open={adding} onClose={() => setAdding(false)} title="Add a pre-authorisation code" description="Applies to claims received from now on."
        footer={<><Button onClick={() => setAdding(false)}>Cancel</Button><Button variant="primary" loading={busy} onClick={add}>Add code</Button></>}
      >
        <div className="space-y-3">
          <Field label="Tariff code" required error={attempted ? codeError : null}>
            <Input className="font-mono" value={code} invalid={attempted && Boolean(codeError)} onChange={(e) => setCode(e.target.value)} />
          </Field>
          {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
        </div>
      </Dialog>
      <ConfirmDialog
        open={removing !== null} onClose={() => setRemoving(null)} busy={busy} danger title={`Remove code ${removing ?? ""}?`} confirmLabel="Remove code"
        description="Lines under this code will be paid without pre-authorisation from now on." onConfirm={remove}
      />
    </div>
  );
}
