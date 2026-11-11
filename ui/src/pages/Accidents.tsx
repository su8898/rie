// Accidents. Every claim is tied to the accident it arose from. Seeing the claims on one accident
// together is how duplicate claims, staged accidents and overfull vehicles are noticed.

import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { DataTable, Pager, type Column, type Sort } from "../ds/DataTable";
import { shortDate } from "../ds/labels";
import { Dialog } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Facts, Input, PageHeader, Ref, Select, Stat } from "../ds/primitives";
import type { Accident } from "../types";
import { useListParams } from "./work/shared";

/** The engine's own floor: below this an accident raises the "thinly corroborated" finding. */
const THIN = 20;
/** More claimants than the accident report says were in the vehicles. */
const overfull = (a: Accident) => a.oar_occupants != null && a.parties.length > a.oar_occupants;
const strength = (c: number) => (c >= THIN ? { label: "Supported", tone: "ok" as const } : { label: "Thinly supported", tone: "warn" as const });

export default function AccidentsPage() {
  const { value, page, pageSize, set } = useListParams();
  const [rows, setRows] = useState<Accident[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Accident | null>(null);
  useEffect(() => { api.accidents().then(setRows).catch((e) => setError(e instanceof ApiError ? e.message : "The accidents could not be loaded.")); }, []);

  const sort: Sort = { key: value("sort") || "when", direction: value("dir") === "asc" ? "asc" : "desc" };
  const filtered = Boolean(value("q") || value("show"));
  const all = rows ?? [];
  const shown = useMemo(() => {
    const needle = value("q").trim().toLowerCase();
    const list = all.filter((a) =>
      (!needle || a.accident_id.toLowerCase().includes(needle) || (a.case_number ?? "").toLowerCase().includes(needle) || a.where.toLowerCase().includes(needle) || a.claims.some((c) => c.toLowerCase().includes(needle)))
      && (value("show") === "" || (value("show") === "many" ? a.n_claims > 1 : value("show") === "thin" ? a.convergence < THIN : overfull(a))));
    const key = (a: Accident) => sort.key === "claims" ? a.n_claims : sort.key === "support" ? a.convergence : a.when;
    return [...list].sort((x, y) => (key(x) < key(y) ? -1 : key(x) > key(y) ? 1 : 0) * (sort.direction === "asc" ? 1 : -1));
    // the URL carries the filter and the sort
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, value("q"), value("show"), sort.key, sort.direction]);
  const pageRows = shown.slice((page - 1) * pageSize, page * pageSize);

  const columns: Column<Accident>[] = [
    { key: "when", header: "Accident", sortable: true, render: (a) => <div><div className="font-medium text-ink-900">{shortDate(a.when)}</div><div className="max-w-[36ch] truncate text-xs text-ink-500" title={a.where}>{a.where || "Place not recorded"}</div></div> },
    { key: "case", header: "Police case number", render: (a) => a.case_number ? <Ref className="text-ink-800">{a.case_number}</Ref> : <Badge tone="warn">None</Badge> },
    { key: "claims", header: "Claims", align: "right", sortable: true, render: (a) => <span className="tnum font-medium text-ink-900">{a.n_claims}</span> },
    { key: "people", header: "Claimants", align: "right", render: (a) => (
      <div><span className="tnum text-ink-800">{a.parties.length}</span>{a.oar_occupants != null && <span className="tnum text-ink-500"> of {a.oar_occupants} reported</span>}{overfull(a) && <div><Badge tone="bad">More than reported</Badge></div>}</div>
    ) },
    { key: "support", header: "Independent support", sortable: true, render: (a) => { const s = strength(a.convergence); return <div><Badge tone={s.tone}>{s.label}</Badge><div className="tnum mt-1 text-xs text-ink-500">{a.convergence} of 100</div></div>; } },
  ];

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Integrity" }, { label: "Accidents" }]}
        title="Accidents"
        subtitle="Each claim is tied to the accident it arose from. Claims on the same accident are checked against each other and against what independent sources say happened."
      />
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Accidents" value={rows ? all.length : "…"} />
        <Stat label="With more than one claim" value={rows ? all.filter((a) => a.n_claims > 1).length : "…"} />
        <Stat label="Thinly supported" value={rows ? all.filter((a) => a.convergence < THIN).length : "…"} tone="warn" hint={`Below ${THIN} of 100, the engine's floor`} />
        <Stat label="More claimants than reported" value={rows ? all.filter(overfull).length : "…"} tone={rows && all.some(overfull) ? "bad" : undefined} />
      </div>
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-4">
        <Input className="sm:col-span-2" placeholder="Accident, police case number, place or claim" aria-label="Search accidents" value={value("q")} onChange={(e) => set({ q: e.target.value })} />
        <Select aria-label="Show" value={value("show")} onChange={(e) => set({ show: e.target.value })}>
          <option value="">All accidents</option>
          <option value="many">With more than one claim</option>
          <option value="thin">Thinly supported</option>
          <option value="overfull">More claimants than reported</option>
        </Select>
        {filtered && <div className="flex items-center"><Button size="sm" variant="ghost" icon={X} onClick={() => set({ q: null, show: null })}>Clear filters</Button></div>}
      </div>
      {error ? <ErrorBlock message={error} /> : (
        <DataTable
          columns={columns} rows={pageRows} rowKey={(a) => a.accident_id} loading={rows === null} onRowClick={setOpen}
          sort={sort} onSort={(s) => set({ sort: s.key === "when" ? null : s.key, dir: s.direction === "asc" ? "asc" : null }, true)}
          empty={<EmptyState title={filtered ? "No accident matches" : "No accidents yet"} body={filtered ? "Change or clear the filters." : "An accident record is created when the first claim for it is received."} />}
          footer={<Pager page={page} pageSize={pageSize} total={shown.length} unit="accidents" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
        />
      )}

      <Dialog open={open !== null} onClose={() => setOpen(null)} wide title={open ? `Accident on ${shortDate(open.when)}` : ""} description={open?.where || undefined}>
        {open && (
          <div className="space-y-4">
            <Facts items={[
              { label: "Accident record", value: <Ref>{open.accident_id}</Ref> },
              { label: "Police case number", value: open.case_number ? <Ref>{open.case_number}</Ref> : "None recorded" },
              { label: "Vehicles", value: open.vehicles.length ? <Ref>{open.vehicles.join(", ")}</Ref> : "None recorded" },
              { label: "Occupants on the accident report", value: open.oar_occupants ?? "Not recorded" },
              { label: "Independent support", value: `${strength(open.convergence).label}, ${open.convergence} of 100` },
              { label: "Claimants", value: `${open.parties.length}${overfull(open) ? ", more than the report says were present" : ""}` },
            ]} />
            <div>
              <div className="mb-1.5 text-xs font-medium text-ink-500">Claims on this accident</div>
              <ul className="divide-y divide-line rounded-md border border-line">
                {open.claims.map((c) => <li key={c} className="px-3 py-2"><Link to={`/claims/${encodeURIComponent(c)}`} className="text-brand-700 hover:underline"><Ref>{c}</Ref></Link></li>)}
                {open.claims.length === 0 && <li className="px-3 py-2 text-sm text-ink-500">No claims are linked.</li>}
              </ul>
            </div>
            <p className="text-[13px] text-ink-500">Independent support counts the separate sources that confirm the accident (ambulance, hospital, police, employer and others). Sources from one attorney or provider network count once.</p>
          </div>
        )}
      </Dialog>
    </div>
  );
}
