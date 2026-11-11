// Signal modes: how much weight each finding carries. Shadow (measured only), advisory (shown,
// not scored) or scored. Findings set by law are always scored and cannot be changed here.

import { Lock, RotateCcw, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api";
import { DataTable, type Column } from "../../ds/DataTable";
import { MATURITY, SIGNAL_MODES, reasonLabel, shortDate } from "../../ds/labels";
import { ConfirmDialog, Dialog, useToast } from "../../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, Ref, Select, Textarea } from "../../ds/primitives";
import type { SignalMode } from "../../types";
import { RecentChanges, SectionHeader, errorText, useList } from "./shared";

export default function SignalModesAdmin() {
  const toast = useToast();
  const { rows, loading, error, reload } = useList(api.signalModes, "The signal modes could not be loaded.");
  const [q, setQ] = useState("");
  const [mode, setMode] = useState("");
  const [view, setView] = useState("");
  const [editing, setEditing] = useState<{ row: SignalMode; mode: string; note: string } | null>(null);
  const [clearing, setClearing] = useState<SignalMode | null>(null);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  const shown = useMemo(() => rows.filter((r) => {
    const needle = q.trim().toLowerCase();
    return (!needle || r.signal.toLowerCase().includes(needle) || reasonLabel(r.signal).toLowerCase().includes(needle))
      && (!mode || r.effective_mode === mode)
      && (view === "" || (view === "changed" ? r.overridden : view === "recommended" ? Boolean(r.recommended_mode && r.recommended_mode !== r.effective_mode && r.overridable) : !r.overridable));
  }), [rows, q, mode, view]);
  const done = async (message: string) => { toast.success(message); setEditing(null); setClearing(null); setVersion((v) => v + 1); await reload(); };

  const noteError = !editing?.note.trim() ? "Say why the mode is changing." : null;
  async function save() {
    setAttempted(true);
    if (!editing || noteError) return;
    setBusy(true);
    setFormError(null);
    try {
      await api.setSignalMode({ code: editing.row.signal, mode: editing.mode, note: editing.note.trim() });
      await done(`${reasonLabel(editing.row.signal)} is now ${SIGNAL_MODES[editing.mode].label.toLowerCase()}.`);
    } catch (e) {
      setFormError(errorText(e, "The mode could not be changed."));
    } finally {
      setBusy(false);
    }
  }
  async function clear() {
    if (!clearing) return;
    setBusy(true);
    try {
      await api.clearSignalMode(clearing.signal);
      await done(`${reasonLabel(clearing.signal)} is back to its default.`);
    } catch (e) {
      toast.error(errorText(e, "The mode could not be reset."));
    } finally {
      setBusy(false);
    }
  }

  const columns: Column<SignalMode>[] = [
    { key: "signal", header: "Finding", render: (r) => <div><div className="font-medium text-ink-900">{reasonLabel(r.signal)}</div><Ref className="text-xs text-ink-400">{r.signal}</Ref></div> },
    { key: "maturity", header: "Evidence", render: (r) => (
      <div>
        <div className="text-ink-700">{MATURITY[r.maturity] ?? r.maturity}</div>
        {r.substantiation != null && <div className="tnum text-xs text-ink-500">{Math.round(r.substantiation * 100)}% borne out on closed cases</div>}
      </div>
    ) },
    { key: "mode", header: "In force", render: (r) => (
      <div>
        <Badge tone={SIGNAL_MODES[r.effective_mode]?.tone ?? "neutral"} dot>{SIGNAL_MODES[r.effective_mode]?.label ?? r.effective_mode}</Badge>
        {r.overridden && <div className="mt-1 text-xs text-ink-500">Changed by {r.set_by} from {shortDate(r.effective_from)}{r.note ? `: ${r.note}` : ""}</div>}
        {!r.overridden && r.overridable && <div className="mt-1 text-xs text-ink-500">Default</div>}
      </div>
    ) },
    { key: "recommended", header: "Suggested", render: (r) => !r.overridable ? <span className="text-ink-400">—</span> : r.recommended_mode && r.recommended_mode !== r.effective_mode
      ? <Badge tone="warn">Move to {SIGNAL_MODES[r.recommended_mode]?.label.toLowerCase() ?? r.recommended_mode}</Badge>
      : <span className="text-[13px] text-ink-500">No change</span> },
    { key: "actions", header: "", align: "right", render: (r) => !r.overridable ? (
      <span className="inline-flex items-center gap-1 text-xs text-ink-500"><Lock size={12} aria-hidden /> Set by law</span>
    ) : (
      <div className="flex justify-end gap-1">
        <Button size="sm" variant="ghost" icon={SlidersHorizontal} onClick={() => { setAttempted(false); setFormError(null); setEditing({ row: r, mode: r.recommended_mode && r.recommended_mode !== r.effective_mode ? r.recommended_mode : r.effective_mode, note: "" }); }}>Change</Button>
        {r.overridden && <Button size="sm" variant="ghost" icon={RotateCcw} onClick={() => setClearing(r)}>Reset</Button>}
      </div>
    ) },
  ];

  return (
    <div>
      <SectionHeader
        title="Signal modes" description={<>How much weight each finding carries. A new finding starts in shadow, moves to advisory, and is scored once closed cases show it is reliable. <Link to="/governance" className="text-brand-700 hover:underline">Signal governance</Link> shows the evidence behind each suggestion.</>}
      />
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-4">
        <Input className="sm:col-span-2" placeholder="Finding or code" aria-label="Search findings" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select aria-label="Mode in force" value={mode} onChange={(e) => setMode(e.target.value)}>
          <option value="">Any mode</option>
          {Object.entries(SIGNAL_MODES).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
        </Select>
        <Select aria-label="Show" value={view} onChange={(e) => setView(e.target.value)}>
          <option value="">All findings</option>
          <option value="recommended">With a suggested change</option>
          <option value="changed">Changed from the default</option>
          <option value="locked">Set by law</option>
        </Select>
      </div>
      {error ? <ErrorBlock message={error} onRetry={reload} /> : (
        <DataTable
          columns={columns} rows={shown} rowKey={(r) => r.signal} loading={loading}
          empty={<EmptyState title="No finding matches" body="Change the search or the filters." />}
          footer={<span className="text-[13px] text-ink-500">{shown.length} of {rows.length} findings</span>}
        />
      )}
      <RecentChanges area="signal_mode" version={version} />

      <Dialog
        open={editing !== null} onClose={() => setEditing(null)} title={editing ? `Change mode: ${reasonLabel(editing.row.signal)}` : ""}
        description="Applies to claims assessed from now on. Claims already decided do not change."
        footer={<><Button onClick={() => setEditing(null)}>Cancel</Button><Button variant="primary" loading={busy} disabled={editing?.mode === editing?.row.effective_mode} onClick={save}>Save mode</Button></>}
      >
        {editing && (
          <div className="space-y-4">
            <Field label="Mode" required hint={SIGNAL_MODES[editing.mode]?.help}>
              <Select value={editing.mode} onChange={(e) => setEditing({ ...editing, mode: e.target.value })}>
                {Object.entries(SIGNAL_MODES).map(([k, m]) => <option key={k} value={k}>{m.label}{k === editing.row.default_mode ? " (default)" : ""}{k === editing.row.recommended_mode ? " (suggested)" : ""}</option>)}
              </Select>
            </Field>
            <Field label="Reason" required error={attempted ? noteError : null}>
              <Textarea rows={3} maxLength={300} value={editing.note} onChange={(e) => setEditing({ ...editing, note: e.target.value })} placeholder="For example: precision above the threshold on 60 closed cases" />
            </Field>
            {formError && <p className="rounded-md border border-bad-line bg-bad-bg px-3 py-2 text-[13px] text-bad-fg" role="alert">{formError}</p>}
          </div>
        )}
      </Dialog>
      <ConfirmDialog
        open={clearing !== null} onClose={() => setClearing(null)} busy={busy} title={clearing ? `Reset ${reasonLabel(clearing.signal)}?` : ""} confirmLabel="Reset to default"
        description={clearing ? `It goes back to its default mode, ${SIGNAL_MODES[clearing.default_mode]?.label.toLowerCase() ?? clearing.default_mode}.` : undefined}
        onConfirm={clear}
      />
    </div>
  );
}
