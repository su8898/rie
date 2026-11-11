// Coding rules: the tariff's own billing rules for a code. Once per encounter, or one of the
// time rules that turn minutes into payable units. One rule per code.

import { Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../api";
import { DataTable, type Column } from "../../ds/DataTable";
import { CODE_RULE_KINDS } from "../../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, Ref, Select, Textarea } from "../../ds/primitives";
import type { CodeRule, CodeRuleKind } from "../../types";
import { RecentChanges, SectionHeader, errorText, useList } from "./shared";

const ORIGINS: Record<string, string> = { tariff: "From the tariff", standard: "Standard rule", manual: "Set by an administrator" };
const paramText = (r: CodeRule) => r.rule === "TIME_BLOCK" ? `${r.param} minutes a block` : r.rule === "PCT_OF_TIME" ? `${Math.round(r.param * 100)}% of the time` : "";

export default function CodingRulesAdmin() {
  const toast = useToast();
  const { rows, loading, error, reload } = useList(api.adminCodeRules, "The coding rules could not be loaded.");
  const [q, setQ] = useState("");
  const [rule, setRule] = useState("");
  const [editing, setEditing] = useState<{ code: string; rule: CodeRuleKind; param: string; basis: string; existing: boolean } | null>(null);
  const [removing, setRemoving] = useState<CodeRule | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const shown = useMemo(() => rows.filter((r) => (!rule || r.rule === rule) && (r.code.toLowerCase().includes(q.trim().toLowerCase()) || r.basis.toLowerCase().includes(q.trim().toLowerCase()))), [rows, q, rule]);
  const open = (r?: CodeRule) => { setAttempted(false); setFormError(null); setEditing(r ? { code: r.code, rule: r.rule, param: r.param ? String(r.param) : "", basis: r.basis, existing: true } : { code: "", rule: "ONCE_PER_ENCOUNTER", param: "", basis: "", existing: false }); };
  const done = async (message: string) => { toast.success(message); setEditing(null); setRemoving(null); setVersion((v) => v + 1); await reload(); };

  const meta = editing ? CODE_RULE_KINDS[editing.rule] : null;
  const p = Number(editing?.param);
  const codeError = !editing?.code.trim() ? "Enter the tariff code." : !editing.existing && rows.some((r) => r.code === editing.code.trim()) ? "That code already has a rule. Edit it instead." : null;
  const paramError = !meta?.param ? null : editing?.rule === "TIME_BLOCK" ? (!(p >= 1 && p <= 1440) ? "Enter the block length, from 1 to 1440 minutes." : null) : (!(p > 0 && p <= 1) ? "Enter a share above 0 and up to 1." : null);
  async function save() {
    setAttempted(true);
    if (!editing || codeError || paramError) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.upsertCodeRule({ code: editing.code.trim(), rule: editing.rule, param: meta?.param ? p : 0, basis: editing.basis.trim() });
      await done(`Coding rule for ${editing.code.trim()} saved.`);
    } catch (e) {
      setFormError(errorText(e, "The rule could not be saved."));
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api.deleteCodeRule(removing.code);
      await done(`Coding rule for ${removing.code} removed.`);
    } catch (e) {
      toast.error(errorText(e, "The rule could not be removed."));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<CodeRule>[] = [
    { key: "code", header: "Tariff code", render: (r) => <Ref className="font-medium text-ink-900">{r.code}</Ref> },
    { key: "rule", header: "Rule", render: (r) => <div><div className="text-ink-800">{CODE_RULE_KINDS[r.rule]?.label ?? r.rule}</div>{paramText(r) && <div className="text-xs text-ink-500">{paramText(r)}</div>}</div> },
    { key: "basis", header: "Basis", render: (r) => <span className="block max-w-[46ch] text-[13px] text-ink-600">{r.basis || "—"}</span> },
    { key: "origin", header: "Source", render: (r) => r.origin === "manual" ? <Badge tone="info">{ORIGINS.manual}</Badge> : <span className="text-[13px] text-ink-600">{ORIGINS[r.origin] ?? r.origin}</span> },
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
        title="Coding rules" description="The tariff's own billing rules for a code. A code billed against its rule is reduced or not paid, and the claim says why. One rule per code."
        actions={<Button variant="primary" icon={Plus} onClick={() => open()}>Add rule</Button>}
      />
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-4">
        <Input className="sm:col-span-2" placeholder="Tariff code or basis" aria-label="Search coding rules" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select className="sm:col-span-2" aria-label="Rule" value={rule} onChange={(e) => setRule(e.target.value)}>
          <option value="">Any rule</option>
          {Object.entries(CODE_RULE_KINDS).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}
        </Select>
      </div>
      {error ? <ErrorBlock message={error} onRetry={reload} /> : (
        <DataTable
          columns={columns} rows={shown} rowKey={(r) => r.code} loading={loading}
          empty={<EmptyState title={q || rule ? "No rule matches" : "No coding rules"} body={q || rule ? "Change the search or the filter." : "Add a rule for a code the tariff limits."} />}
          footer={<span className="text-[13px] text-ink-500">{shown.length} of {rows.length} rules</span>}
        />
      )}
      <RecentChanges area="code_rule" version={version} />

      <Dialog
        open={editing !== null} onClose={() => setEditing(null)} wide title={editing?.existing ? "Edit coding rule" : "Add coding rule"} description="Applies to claims received from now on. Claims already decided do not change."
        footer={<><Button onClick={() => setEditing(null)}>Cancel</Button><Button variant="primary" loading={busy} onClick={save}>Save rule</Button></>}
      >
        {editing && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Tariff code" required error={attempted ? codeError : null} hint={editing.existing ? "The code identifies the rule and cannot be changed." : undefined}>
              <Input className="font-mono" value={editing.code} disabled={editing.existing} invalid={attempted && Boolean(codeError)} onChange={(e) => setEditing({ ...editing, code: e.target.value })} />
            </Field>
            <Field label="Rule" required hint={meta?.help}>
              <Select value={editing.rule} onChange={(e) => setEditing({ ...editing, rule: e.target.value as CodeRuleKind, param: "" })}>
                {Object.entries(CODE_RULE_KINDS).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}
              </Select>
            </Field>
            {meta?.param && (
              <Field label={meta.param} required error={attempted ? paramError : null}>
                <Input type="number" min={0} step="any" value={editing.param} invalid={attempted && Boolean(paramError)} onChange={(e) => setEditing({ ...editing, param: e.target.value })} />
              </Field>
            )}
            <Field label="Basis" hint="Where the rule comes from, for example the tariff note." className="sm:col-span-2">
              <Textarea rows={2} maxLength={300} value={editing.basis} onChange={(e) => setEditing({ ...editing, basis: e.target.value })} />
            </Field>
            {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg sm:col-span-2" role="alert">{formError}</p>}
          </div>
        )}
      </Dialog>
      <ConfirmDialog
        open={removing !== null} onClose={() => setRemoving(null)} busy={busy} danger title={`Remove the rule on code ${removing?.code ?? ""}?`} confirmLabel="Remove rule"
        description="The code is then paid as billed, with no limit from this rule." onConfirm={remove}
      />
    </div>
  );
}
