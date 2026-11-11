// The reason catalogue: every finding the engine can raise on a claim, what it does when it
// fires, and the basis it rests on. Read-only here; administrators change a finding's weight
// under Administration, Signal modes.

import { Lock, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, type Column } from "../ds/DataTable";
import { DISPOSITIONS, MATURITY, SIGNAL_MODES, reasonLabel } from "../ds/labels";
import { Badge, Button, EmptyState, ErrorBlock, Input, PageHeader, Ref, Select, Stat } from "../ds/primitives";
import type { Disposition, Reason } from "../types";

const FILTERS = ["q", "category", "mode", "maturity", "effect"];
const basis = (r: Reason) => r.basis.replace(/^§\S+\s*[—-]\s*/, "");
const effect = (r: Reason) => (r.category === "ADJUSTED" ? "reduce" : r.hard ? "block" : "score");
const EFFECTS: Record<string, string> = { block: "Blocks payment", reduce: "Reduces payment", score: "Adds to the risk score" };

export default function ReasonsPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState<Reason[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.reasons().then(setRows).catch((e) => setError(e instanceof ApiError ? e.message : "The catalogue could not be loaded.")); }, []);

  const value = (k: string) => params.get(k) ?? "";
  const set = (k: string, v: string) => { const next = new URLSearchParams(params); if (v) next.set(k, v); else next.delete(k); setParams(next, { replace: true }); };
  const filtered = FILTERS.some((k) => value(k));
  const all = rows ?? [];
  const shown = useMemo(() => all.filter((r) => {
    const needle = value("q").trim().toLowerCase();
    return (!needle || r.code.toLowerCase().includes(needle) || reasonLabel(r.code).toLowerCase().includes(needle) || r.basis.toLowerCase().includes(needle))
      && (!value("category") || r.category === value("category")) && (!value("mode") || r.mode === value("mode"))
      && (!value("maturity") || r.maturity === value("maturity")) && (!value("effect") || effect(r) === value("effect"));
    // `params` carries every filter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [all, params]);
  const categories = [...new Set(all.map((r) => r.category))];

  const columns: Column<Reason>[] = [
    { key: "finding", header: "Finding", render: (r) => <div><div className="font-medium text-ink-900">{reasonLabel(r.code)}</div><Ref className="text-xs text-ink-400">{r.code}</Ref></div> },
    { key: "leads", header: "Leads to", render: (r) => { const d = DISPOSITIONS[r.category as Disposition]; return d ? <Badge tone={d.tone}>{d.label}</Badge> : <span>{r.category}</span>; } },
    { key: "effect", header: "When it fires", render: (r) => (
      <div>
        <div className="text-ink-800">{EFFECTS[effect(r)]}</div>
        {effect(r) === "score" && <div className="tnum text-xs text-ink-500">{r.mode === "SCORED" ? `${r.points} point${r.points === 1 ? "" : "s"}` : "No points in its current mode"}</div>}
      </div>
    ) },
    { key: "mode", header: "Mode", render: (r) => (
      <div className="flex items-center gap-1.5">
        <Badge tone={SIGNAL_MODES[r.mode]?.tone ?? "neutral"} dot>{SIGNAL_MODES[r.mode]?.label ?? r.mode}</Badge>
        {r.maturity === "GROUNDED" && <Lock size={12} className="text-ink-400" aria-label="Set by law" />}
      </div>
    ) },
    { key: "evidence", header: "Evidence", render: (r) => <div><div className="text-ink-700">{MATURITY[r.maturity] ?? r.maturity}</div><div className="text-xs text-ink-500">{r.endogenous ? "From the claim's own data" : "Checked against other records"}</div></div> },
    { key: "basis", header: "Basis", render: (r) => <span className="block max-w-[44ch] text-[13px] text-ink-600">{basis(r) || "—"}</span> },
  ];

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Reference" }, { label: "Reason catalogue" }]}
        title="Reason catalogue"
        subtitle="Every finding the engine can raise on a claim: what it does when it fires, and the basis it rests on."
        actions={user?.role === "ADMIN" && <Link to="/admin/signals" className="inline-flex h-9 items-center rounded-md border border-line-strong bg-white px-3 text-sm font-medium text-ink-800 transition hover:bg-ink-50">Change signal modes</Link>}
      />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Findings" value={rows ? all.length : "…"} />
        <Stat label="Block payment" value={rows ? all.filter((r) => effect(r) === "block").length : "…"} tone="bad" hint="Held until resolved" />
        <Stat label="Set by law" value={rows ? all.filter((r) => r.maturity === "GROUNDED").length : "…"} hint="Always scored" />
        <Stat label="Not scored yet" value={rows ? all.filter((r) => r.mode !== "SCORED").length : "…"} hint="Advisory or shadow" />
      </div>
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-2 lg:grid-cols-6">
        <Input className="lg:col-span-2" placeholder="Finding, code or basis" aria-label="Search findings" value={value("q")} onChange={(e) => set("q", e.target.value)} />
        <Select aria-label="Leads to" value={value("category")} onChange={(e) => set("category", e.target.value)}>
          <option value="">Any outcome</option>
          {categories.map((c) => <option key={c} value={c}>{DISPOSITIONS[c as Disposition]?.label ?? c}</option>)}
        </Select>
        <Select aria-label="When it fires" value={value("effect")} onChange={(e) => set("effect", e.target.value)}>
          <option value="">Any effect</option>
          {Object.entries(EFFECTS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </Select>
        <Select aria-label="Mode" value={value("mode")} onChange={(e) => set("mode", e.target.value)}>
          <option value="">Any mode</option>
          {Object.entries(SIGNAL_MODES).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
        </Select>
        <Select aria-label="Evidence" value={value("maturity")} onChange={(e) => set("maturity", e.target.value)}>
          <option value="">Any evidence</option>
          {Object.entries(MATURITY).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </Select>
        {filtered && <div className="flex items-center lg:col-span-6"><Button size="sm" variant="ghost" icon={X} onClick={() => setParams({}, { replace: true })}>Clear filters</Button></div>}
      </div>
      {error ? <ErrorBlock message={error} /> : (
        <DataTable
          columns={columns} rows={shown} rowKey={(r) => r.code} loading={rows === null}
          empty={<EmptyState title="No finding matches" body="Change or clear the filters." />}
          footer={<span className="text-[13px] text-ink-500">{shown.length} of {all.length} findings</span>}
        />
      )}
    </div>
  );
}
