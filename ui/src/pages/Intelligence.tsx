// Party intelligence. How each practice and attorney compares with others like it, which
// claimants appear on more than one accident, and whether the findings fall evenly across kinds
// of practice. A rating is a prompt to look closer. It starts nothing by itself.

import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { DataTable, Pager, type Column, type Sort } from "../ds/DataTable";
import { CLAIM_TYPES, PARTY_RATING, humanise } from "../ds/labels";
import { Dialog } from "../ds/overlays";
import { Badge, Button, EmptyState, ErrorBlock, Field, Input, PageHeader, Panel, Ref, Select, Stat, Tabs } from "../ds/primitives";
import { rand } from "../format";
import type { Attorney, Claimant, Fairness, Provider, RiskComponents, RiskSweep } from "../types";
import { useListParams } from "./work/shared";

type Tab = "practices" | "attorneys" | "claimants" | "fairness" | "list";
const GROUPS: Record<string, string> = { GENERAL: "General practice", SPECIALIST: "Specialist", MATERIALS: "Mostly medicines and materials" };
const COMPONENTS: { key: keyof RiskComponents; label: string; help: string; weight: number }[] = [
  { key: "behavioural", label: "Findings on its claims", help: "How many of its claims are rated high or medium risk.", weight: 40 },
  { key: "cohort_outlier", label: "Prices against similar parties", help: "How far its average line value sits above others in its group.", weight: 20 },
  { key: "over_servicing", label: "Over-servicing", help: "How often its claims carry a finding that is not about price.", weight: 20 },
  { key: "history", label: "History", help: "Past recoveries and open cases. Not fed yet, so this is zero for now.", weight: 20 },
];
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);
const rating = (r: { rating: string; score: number; confidence: string; n_claims: number }) => r.confidence === "LOW_N"
  ? <div><Badge>Too few claims</Badge><div className="mt-1 text-xs text-ink-500">{r.n_claims} claim{r.n_claims === 1 ? "" : "s"}; 5 are needed</div></div>
  : <div><Badge tone={PARTY_RATING[r.rating]?.tone ?? "neutral"} dot>{PARTY_RATING[r.rating]?.label ?? r.rating}</Badge><div className="tnum mt-1 text-xs text-ink-500">Score {r.score} of 100</div></div>;

function useData<T>(loader: () => Promise<T>, fallback: string, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setData(null);
    loader().then((d) => { setData(d); setError(null); }).catch((e) => setError(message(e, fallback)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}

function Breakdown({ title, components, score, onClose }: { title: string; components: RiskComponents; score: number; onClose: () => void }) {
  return (
    <Dialog open onClose={onClose} title={title} description={`Score ${score} of 100. The score is a weighted sum of four parts.`}>
      <ul className="space-y-3">
        {COMPONENTS.map((c) => (
          <li key={c.key}>
            <div className="flex items-baseline justify-between text-sm"><span className="font-medium text-ink-900">{c.label}</span><span className="tnum text-ink-700">{components[c.key]} of 100 <span className="text-ink-400">· weight {c.weight}%</span></span></div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink-100"><div className="h-full rounded-full bg-ink-700" style={{ width: `${Math.min(100, components[c.key])}%` }} /></div>
            <div className="mt-1 text-xs text-ink-500">{c.help}</div>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-[13px] text-ink-500">Pricing and duplicate billing are left out on purpose: they are corrected when the claim is assessed and are not evidence of fraud.</p>
    </Dialog>
  );
}

export default function IntelligencePage() {
  const { value, reset } = useListParams();
  const t = value("tab");
  const tab: Tab = t === "attorneys" || t === "claimants" || t === "fairness" || t === "list" ? t : "practices";
  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Integrity" }, { label: "Party intelligence" }]}
        title="Party intelligence"
        subtitle="How each practice and attorney compares with others like it. A rating is a reason to look closer; it holds no claim and opens no case by itself."
      />
      <Tabs<Tab>
        tabs={[{ key: "practices", label: "Practices" }, { key: "attorneys", label: "Attorneys" }, { key: "claimants", label: "Repeat claimants" }, { key: "fairness", label: "Fairness" }, { key: "list", label: "High-risk list" }]}
        value={tab} onChange={(k) => reset(k === "practices" ? {} : { tab: k })}
      />
      <div className="mt-4">
        {tab === "practices" && <Practices />}
        {tab === "attorneys" && <Attorneys />}
        {tab === "claimants" && <Claimants />}
        {tab === "fairness" && <FairnessView />}
        {tab === "list" && <HighRisk />}
      </div>
    </div>
  );
}

function Practices() {
  const navigate = useNavigate();
  const { value, page, pageSize, set } = useListParams();
  const { data, error } = useData<Provider[]>(api.providers, "The practices could not be loaded.");
  const [open, setOpen] = useState<Provider | null>(null);
  const sort: Sort = { key: value("sort") || "score", direction: value("dir") === "asc" ? "asc" : "desc" };
  const all = data ?? [];
  const shown = useMemo(() => {
    const needle = value("q").trim().toLowerCase();
    const list = all.filter((p) => (!needle || p.provider_id.toLowerCase().includes(needle)) && (!value("rating") || (p.confidence === "OK" && p.rating === value("rating"))) && (!value("group") || p.cohort === value("group")) && (value("rated") !== "yes" || p.confidence === "OK"));
    const key = (p: Provider) => sort.key === "billed" ? p.billed : sort.key === "claims" ? p.n_claims : sort.key === "value" ? p.avg_value : p.score;
    return [...list].sort((a, b) => (key(a) - key(b)) * (sort.direction === "asc" ? 1 : -1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [all, value("q"), value("rating"), value("group"), value("rated"), sort.key, sort.direction]);
  const filtered = ["q", "rating", "group", "rated"].some((k) => value(k));
  const rated = all.filter((p) => p.confidence === "OK");

  const columns: Column<Provider>[] = [
    { key: "practice", header: "Practice", render: (p) => <div><Ref className="font-medium text-brand-700">{p.provider_id}</Ref><div className="text-xs text-ink-500">{GROUPS[p.cohort] ?? humanise(p.cohort)}</div></div> },
    { key: "claims", header: "Claims", align: "right", sortable: true, render: (p) => <span className="tnum">{p.n_claims}</span> },
    { key: "billed", header: "Billed", align: "right", sortable: true, render: (p) => <span className="tnum text-ink-800">{rand(p.billed)}</span> },
    { key: "value", header: "Average line", align: "right", sortable: true, render: (p) => <div><div className="tnum text-ink-800">{rand(p.avg_value)}</div><div className="tnum text-xs text-ink-500">Above {Math.round(p.value_percentile)}% of its group</div></div> },
    { key: "findings", header: "Claims with a finding", align: "right", render: (p) => <div><div className="tnum text-ink-800">{p.flag_rate}%</div>{p.red_rate > 0 && <div className="tnum text-xs text-bad-fg">{p.red_rate}% high risk</div>}</div> },
    { key: "score", header: "Rating", sortable: true, render: (p) => rating(p) },
    { key: "why", header: "", align: "right", render: (p) => p.confidence === "OK" ? <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setOpen(p); }}>How it is scored</Button> : null },
  ];
  if (error) return <ErrorBlock message={error} />;
  return (
    <>
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Practices billing" value={data ? all.length : "…"} />
        <Stat label="With enough claims to rate" value={data ? rated.length : "…"} hint="5 claims or more" />
        <Stat label="Rated high or critical" value={data ? rated.filter((p) => p.rating === "HIGH" || p.rating === "CRITICAL").length : "…"} tone={rated.some((p) => p.rating === "HIGH" || p.rating === "CRITICAL") ? "bad" : undefined} />
        <Stat label="On watch or elevated" value={data ? rated.filter((p) => p.rating === "WATCH" || p.rating === "ELEVATED").length : "…"} tone="warn" />
      </div>
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-2 lg:grid-cols-5">
        <Input className="lg:col-span-2" placeholder="Practice number" aria-label="Search practices" value={value("q")} onChange={(e) => set({ q: e.target.value })} />
        <Select aria-label="Rating" value={value("rating")} onChange={(e) => set({ rating: e.target.value })}>
          <option value="">Any rating</option>
          {Object.entries(PARTY_RATING).map(([k, r]) => <option key={k} value={k}>{r.label}</option>)}
        </Select>
        <Select aria-label="Group" value={value("group")} onChange={(e) => set({ group: e.target.value })}>
          <option value="">Any group</option>
          {Object.entries(GROUPS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </Select>
        <Select aria-label="Show" value={value("rated")} onChange={(e) => set({ rated: e.target.value })}>
          <option value="">Rated or not</option><option value="yes">Only those with a rating</option>
        </Select>
        {filtered && <div className="flex items-center lg:col-span-5"><Button size="sm" variant="ghost" icon={X} onClick={() => set({ q: null, rating: null, group: null, rated: null })}>Clear filters</Button></div>}
      </div>
      <DataTable
        columns={columns} rows={shown.slice((page - 1) * pageSize, page * pageSize)} rowKey={(p) => p.provider_id} loading={data === null}
        sort={sort} onSort={(s) => set({ sort: s.key === "score" ? null : s.key, dir: s.direction === "asc" ? "asc" : null }, true)}
        onRowClick={(p) => navigate(`/practices/${encodeURIComponent(p.provider_id)}`)}
        empty={<EmptyState title={filtered ? "No practice matches" : "No practice has billed yet"} body={filtered ? "Change or clear the filters." : "Practices appear here once they bill the Fund."} />}
        footer={<Pager page={page} pageSize={pageSize} total={shown.length} unit="practices" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
      />
      {open && <Breakdown title={`How practice ${open.provider_id} is scored`} components={open.components} score={open.score} onClose={() => setOpen(null)} />}
    </>
  );
}

function Attorneys() {
  const { value, page, pageSize, set } = useListParams();
  const { data, error } = useData<Attorney[]>(api.attorneys, "The attorneys could not be loaded.");
  const [open, setOpen] = useState<Attorney | null>(null);
  const all = data ?? [];
  const shown = useMemo(() => all.filter((a) => a.attorney.toLowerCase().includes(value("q").trim().toLowerCase())), [all, value("q")]); // eslint-disable-line react-hooks/exhaustive-deps
  const columns: Column<Attorney>[] = [
    { key: "attorney", header: "Attorney", render: (a) => <div><div className="font-medium text-ink-900">{a.attorney}</div><div className="text-xs text-ink-500">{humanise(a.cohort)}</div></div> },
    { key: "claims", header: "Claims", align: "right", render: (a) => <span className="tnum">{a.n_claims}</span> },
    { key: "mix", header: "Kinds of claim", render: (a) => <span className="text-[13px] text-ink-700">{Object.entries(a.claim_type_mix).map(([k, n]) => `${n} ${(CLAIM_TYPES[k] ?? humanise(k)).toLowerCase()}`).join(", ") || "—"}</span> },
    { key: "late", header: "Lodged late", align: "right", render: (a) => <span className={a.late_lodgement_share > 0 ? "tnum text-warn-fg" : "tnum text-ink-700"}>{a.late_lodgement_share}%</span> },
    { key: "score", header: "Rating", render: (a) => rating(a) },
    { key: "why", header: "", align: "right", render: (a) => a.confidence === "OK" ? <Button size="sm" variant="ghost" onClick={() => setOpen(a)}>How it is scored</Button> : null },
  ];
  if (error) return <ErrorBlock message={error} />;
  return (
    <>
      <div className="mb-3 rounded-lg border border-line bg-white p-3 shadow-panel"><div className="sm:w-80"><Input placeholder="Attorney" aria-label="Search attorneys" value={value("q")} onChange={(e) => set({ q: e.target.value })} /></div></div>
      <DataTable
        columns={columns} rows={shown.slice((page - 1) * pageSize, page * pageSize)} rowKey={(a) => a.attorney} loading={data === null}
        empty={<EmptyState title={value("q") ? "No attorney matches" : "No claim names an attorney yet"} body={value("q") ? "Change the search." : "Attorneys appear here once claims they lodged are received."} />}
        footer={<Pager page={page} pageSize={pageSize} total={shown.length} unit="attorneys" onPage={(p) => set({ page: p > 1 ? String(p) : null }, true)} onPageSize={(n) => set({ size: n === 25 ? null : String(n) })} />}
      />
      {open && <Breakdown title={`How ${open.attorney} is scored`} components={open.components} score={open.score} onClose={() => setOpen(null)} />}
    </>
  );
}

function Claimants() {
  const { data, error } = useData<Claimant[]>(api.claimants, "The claimants could not be loaded.");
  const columns: Column<Claimant>[] = [
    { key: "who", header: "Claimant reference", render: (c) => <Link to={`/claims?q=${encodeURIComponent(c.party_token)}`} className="font-medium text-brand-700 hover:underline"><Ref>{c.party_token}</Ref></Link> },
    { key: "n", header: "Accidents", align: "right", render: (c) => <span className="tnum font-medium text-ink-900">{c.n_accidents}</span> },
    { key: "which", header: "Accident records", render: (c) => <Ref className="text-[13px] text-ink-700">{c.accidents.join(", ")}</Ref> },
  ];
  if (error) return <ErrorBlock message={error} />;
  return (
    <DataTable
      columns={columns} rows={data ?? []} rowKey={(c) => c.party_token} loading={data === null}
      empty={<EmptyState title="No claimant appears on more than one accident" body="A claimant is listed here when the same person is a party to two or more accidents." />}
      footer={<span className="text-[13px] text-ink-500">{(data ?? []).length} claimants on two or more accidents. The reference stands in for the person's identity, which is never shown here.</span>}
    />
  );
}

function FairnessView() {
  const { data, error } = useData<Fairness>(api.fairness, "The fairness figures could not be loaded.");
  if (error) return <ErrorBlock message={error} />;
  const columns: Column<Fairness["by_cohort"][number]>[] = [
    { key: "group", header: "Group of practices", render: (c) => <span className="font-medium text-ink-900">{GROUPS[c.cohort] ?? humanise(c.cohort)}</span> },
    { key: "claims", header: "Claims", align: "right", render: (c) => <span className="tnum">{c.n_claims}</span> },
    { key: "rate", header: "Claims with a finding", align: "right", render: (c) => <span className="tnum text-ink-800">{c.flag_rate}%</span> },
    { key: "impact", header: "Against the overall rate", align: "right", render: (c) => <span className="tnum text-ink-800">{c.impact == null ? "—" : `${c.impact} times`}</span> },
    { key: "verdict", header: "", render: (c) => c.small ? <Badge>Too few claims to judge</Badge> : c.review ? <Badge tone="warn">Needs a look</Badge> : <Badge tone="ok">Within range</Badge> },
  ];
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <Stat label="Overall" value={data ? `${data.overall_flag_rate ?? 0}%` : "…"} hint="Of claims carry a finding" />
        <Stat label="Lowest group against highest" value={data ? data.four_fifths_ratio : "…"} tone={data ? (data.pass ? "ok" : "bad") : undefined} hint={data ? (data.pass ? "At or above 0.8: findings fall evenly" : "Below 0.8: one group is flagged far more") : undefined} />
        <Stat label="Groups needing a look" value={data ? data.by_cohort.filter((c) => c.review).length : "…"} />
      </div>
      <DataTable columns={columns} rows={data?.by_cohort ?? []} rowKey={(c) => c.cohort} loading={data === null} empty={<EmptyState title="Nothing to compare yet" body="Figures appear once practices have billed." />} />
      <Panel title="How to read this">
        <p className="text-sm text-ink-700">Practices are grouped by how they bill, and each group's share of claims with a finding is compared with the overall share. A group flagged much more often than the rest may be over-scrutinised; one flagged much less may be under-scrutinised. Either is marked for a look once the group has at least {data?.min_group ?? 5} claims and its rate falls below {data?.impact_low ?? 0.8} times or above {data?.impact_high ?? 1.25} times the overall rate.</p>
      </Panel>
    </div>
  );
}

function HighRisk() {
  const { value, set } = useListParams();
  const threshold = value("score") !== "" && Number(value("score")) >= 0 && Number(value("score")) <= 100 ? Number(value("score")) : 55;
  const [draft, setDraft] = useState(String(threshold));
  const { data, error } = useData<RiskSweep>(() => api.riskSweep(threshold), "The list could not be loaded.", [threshold]);
  const columns: Column<RiskSweep["flagged"][number]>[] = [
    { key: "who", header: "Party", render: (h) => h.type === "provider"
      ? <div><Link to={`/practices/${encodeURIComponent(h.id)}`} className="font-medium text-brand-700 hover:underline"><Ref>{h.id}</Ref></Link><div className="text-xs text-ink-500">Practice</div></div>
      : <div><div className="font-medium text-ink-900">{h.id}</div><div className="text-xs text-ink-500">Attorney</div></div> },
    { key: "claims", header: "Claims", align: "right", render: (h) => <span className="tnum">{h.n_claims}</span> },
    { key: "score", header: "Rating", render: (h) => rating(h) },
    { key: "next", header: "", align: "right", render: (h) => <Link to={h.type === "provider" ? `/claims?provider_id=${encodeURIComponent(h.id)}` : `/claims?q=${encodeURIComponent(h.id)}`} className="text-[13px] text-brand-700 hover:underline">See its claims</Link> },
  ];
  return (
    <>
      <div className="mb-3 flex flex-wrap items-end gap-3 rounded-lg border border-line bg-white p-3 shadow-panel">
        <Field label="Score at or above" hint="0 to 100. 55 is where a rating becomes High.">
          <Input type="number" min={0} max={100} className="w-32" value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") set({ score: draft === "55" ? null : draft }); }} />
        </Field>
        <Button onClick={() => set({ score: draft === "55" ? null : draft })}>Show</Button>
      </div>
      <div className="mb-3 rounded-lg border border-info-line bg-info-bg px-4 py-3 text-sm text-info-fg">
        This list is for looking, not acting. Being on it holds no claim and opens no case. To act on a party, open a case in <Link to="/cases" className="font-medium underline">Cases</Link> so a person makes and records the decision.
      </div>
      {error ? <ErrorBlock message={error} /> : (
        <DataTable
          columns={columns} rows={data?.flagged ?? []} rowKey={(h) => `${h.type}:${h.id}`} loading={data === null}
          empty={<EmptyState title={`No party scores ${threshold} or more`} body="Lower the score to see more." />}
          footer={<span className="text-[13px] text-ink-500">{data?.n ?? 0} practices and attorneys score {threshold} or more, highest first</span>}
        />
      )}
    </>
  );
}
