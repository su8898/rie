// Reference data. The lists claims are priced and coded against: the tariff, medicine prices,
// the diagnosis codes and comparable awards. A lookup for every operator; administrators
// maintain prices under Administration.

import { Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { DataTable, type Column } from "../ds/DataTable";
import { shortDate } from "../ds/labels";
import { Badge, EmptyState, ErrorBlock, Input, PageHeader, Panel, Ref, Select, Stat, Tabs } from "../ds/primitives";
import { rand } from "../format";
import type { AwardAuthority, AwardBand, AwardClass, Icd10Row, NappiRow, RefEdition, TariffRate } from "../types";

type Tab = "overview" | "tariff" | "medicines" | "diagnoses" | "awards";
const LIMIT = 200;
const DATASETS: Record<string, { label: string; help: string }> = {
  tariffs: { label: "Tariff", help: "The gazetted rate per code and discipline." },
  materials: { label: "Medicines and materials", help: "The single exit price per NAPPI code." },
  icd10: { label: "Diagnosis codes", help: "The ICD-10 code list." },
  awards: { label: "Comparable awards", help: "Past general-damages awards by injury." },
};
const USES: { list: string; role: string; note: string }[] = [
  { list: "Tariff", role: "The billing benchmark", note: "A line is paid at the lower of what was billed and the tariff rate for its discipline. A line billed above the tariff is reduced, not rejected." },
  { list: "Medicines and materials", role: "The price ceiling", note: "A medicine or material line is paid up to its single exit price." },
  { list: "Diagnosis codes", role: "The coding vocabulary", note: "Claims are coded in ICD-10. Only a code that may be a primary diagnosis can head a claim, and the diagnosis must fit the accident." },
  { list: "Comparable awards", role: "The general-damages benchmark", note: "The middle half of past awards for an injury, adjusted for inflation, is the range an offer is measured against." },
  { list: "Statutory cap, negotiated rates, pre-authorisation codes", role: "Rules on top of the tariff", note: "Maintained by administrators under Administration and applied by the engine." },
];
const INJURIES: Record<string, string> = { TBI: "Traumatic brain injury" };
/** "AMPUTATION_LOWER_LIMB" reads as "Amputation lower limb". */
const plain = (code: string) => INJURIES[code] ?? code.charAt(0) + code.slice(1).toLowerCase().replace(/_/g, " ");
const message = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback);

/** Search a list as the user types, with a short pause so each keystroke is not a request. */
function useLookup<T>(fetcher: (q: string, limit: number) => Promise<T[]>, q: string, fallback: string) {
  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    const t = window.setTimeout(() => {
      fetcher(q.trim(), LIMIT)
        .then((r) => { if (alive) { setRows(r); setError(null); } })
        .catch((e) => { if (alive) setError(message(e, fallback)); })
        .finally(() => { if (alive) setLoading(false); });
    }, 250);
    return () => { alive = false; window.clearTimeout(t); };
    // The fetcher is a stable API call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);
  return { rows, loading, error };
}

const capped = (n: number, unit: string) => (
  <span className="text-[13px] text-ink-500">{n >= LIMIT ? `Showing the first ${LIMIT} ${unit}. Narrow the search to see others.` : `${n} ${unit}`}</span>
);

export default function ReferencePage() {
  const [params, setParams] = useSearchParams();
  const t = params.get("tab");
  const tab: Tab = t === "tariff" || t === "medicines" || t === "diagnoses" || t === "awards" ? t : "overview";
  const q = params.get("q") ?? "";
  const setQ = (v: string) => { const next = new URLSearchParams(params); if (v) next.set("q", v); else next.delete("q"); setParams(next, { replace: true }); };

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Reference" }, { label: "Reference data" }]}
        title="Reference data"
        subtitle="The lists claims are priced and coded against. Look up a tariff rate, a medicine price, a diagnosis code or the awards for an injury."
      />
      <Tabs<Tab>
        tabs={[{ key: "overview", label: "Overview" }, { key: "tariff", label: "Tariff" }, { key: "medicines", label: "Medicines and materials" }, { key: "diagnoses", label: "Diagnosis codes" }, { key: "awards", label: "Comparable awards" }]}
        value={tab} onChange={(k) => setParams(k === "overview" ? {} : { tab: k }, { replace: true })}
      />
      <div className="mt-4">
        {tab === "overview" && <Overview />}
        {tab === "tariff" && <Tariff q={q} setQ={setQ} />}
        {tab === "medicines" && <Medicines q={q} setQ={setQ} />}
        {tab === "diagnoses" && <Diagnoses q={q} setQ={setQ} />}
        {tab === "awards" && <Awards />}
      </div>
    </div>
  );
}

function SearchBar({ value, onChange, placeholder, children }: { value: string; onChange: (v: string) => void; placeholder: string; children?: React.ReactNode }) {
  return (
    <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-4">
      <div className="relative sm:col-span-2">
        <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden />
        <Input className="pl-8" placeholder={placeholder} aria-label={placeholder} value={value} onChange={(e) => onChange(e.target.value)} autoFocus />
      </div>
      {children}
    </div>
  );
}

function Overview() {
  const [editions, setEditions] = useState<RefEdition[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.editions().then(setEditions).catch((e) => setError(message(e, "The loaded lists could not be read."))); }, []);
  const columns: Column<RefEdition>[] = [
    { key: "list", header: "List", render: (e) => <div><div className="font-medium text-ink-900">{DATASETS[e.kind]?.label ?? e.kind}</div><div className="text-xs text-ink-500">{DATASETS[e.kind]?.help}</div></div> },
    { key: "rows", header: "Entries", align: "right", render: (e) => <span className="tnum text-ink-900">{e.n.toLocaleString("en-ZA")}</span> },
    { key: "loaded", header: "Loaded", render: (e) => <span className="text-ink-700">{shortDate(e.synced_at)}</span> },
    { key: "edition", header: "Edition", render: (e) => <Ref className="block max-w-[38ch] truncate text-xs text-ink-500">{e.version}</Ref> },
  ];
  return (
    <div className="space-y-4">
      {error ? <ErrorBlock message={error} /> : (
        <DataTable columns={columns} rows={editions ?? []} rowKey={(e) => e.kind} loading={editions === null} empty={<EmptyState title="No reference list is loaded" body="The lists are loaded when the system is set up." />} />
      )}
      <Panel title="How each list is used" flush>
        <ul className="divide-y divide-line">
          {USES.map((u) => (
            <li key={u.list} className="grid gap-1 px-4 py-3 sm:grid-cols-3 sm:gap-4">
              <div className="text-sm font-medium text-ink-900">{u.list}</div>
              <div className="text-sm text-ink-700 sm:col-span-2"><span className="font-medium">{u.role}.</span> {u.note}</div>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

function Tariff({ q, setQ }: { q: string; setQ: (v: string) => void }) {
  const { user } = useAuth();
  const { rows, loading, error } = useLookup<TariffRate>(api.tariffSearch, q, "The tariff could not be searched.");
  const [discipline, setDiscipline] = useState("");
  const disciplines = useMemo(() => [...new Set(rows.map((r) => r.discipline))].sort(), [rows]);
  const shown = discipline ? rows.filter((r) => r.discipline === discipline) : rows;
  const columns: Column<TariffRate>[] = [
    { key: "code", header: "Tariff code", render: (r) => <Ref className="font-medium text-ink-900">{r.code}</Ref> },
    { key: "discipline", header: "Discipline", render: (r) => <span className="text-ink-700">{r.discipline}</span> },
    { key: "rate", header: "Rate", align: "right", render: (r) => <span className="tnum font-medium text-ink-900">{rand(r.rate)}</span> },
  ];
  return (
    <>
      <SearchBar value={q} onChange={setQ} placeholder="Tariff code starts with">
        <Select aria-label="Discipline" value={discipline} onChange={(e) => setDiscipline(e.target.value)}>
          <option value="">Any discipline</option>
          {disciplines.map((d) => <option key={d} value={d}>{d}</option>)}
        </Select>
        {user?.role === "ADMIN" && <div className="flex items-center"><Link to={`/admin/rates${q ? `?q=${encodeURIComponent(q)}` : ""}`} className="text-[13px] text-brand-700 hover:underline">Maintain under Dated rates</Link></div>}
      </SearchBar>
      {error ? <ErrorBlock message={error} /> : (
        <DataTable columns={columns} rows={shown} rowKey={(r) => `${r.code}:${r.discipline}`} loading={loading} empty={<EmptyState title="No tariff code matches" body="Search by the start of the code." />} footer={capped(rows.length, "rates")} />
      )}
    </>
  );
}

function Medicines({ q, setQ }: { q: string; setQ: (v: string) => void }) {
  const { rows, loading, error } = useLookup<NappiRow>(api.nappiSearch, q, "The medicine list could not be searched.");
  const columns: Column<NappiRow>[] = [
    { key: "code", header: "NAPPI code", render: (r) => <Ref className="font-medium text-ink-900">{r.nappi_code}</Ref> },
    { key: "price", header: "Single exit price", align: "right", render: (r) => <span className="tnum font-medium text-ink-900">{rand(r.sep)}</span> },
  ];
  return (
    <>
      <SearchBar value={q} onChange={setQ} placeholder="NAPPI code starts with" />
      {error ? <ErrorBlock message={error} /> : (
        <DataTable columns={columns} rows={rows} rowKey={(r) => r.nappi_code} loading={loading} empty={<EmptyState title="No medicine or material matches" body="Search by the start of the NAPPI code." />} footer={capped(rows.length, "items")} />
      )}
    </>
  );
}

function Diagnoses({ q, setQ }: { q: string; setQ: (v: string) => void }) {
  const { rows, loading, error } = useLookup<Icd10Row>(api.icd10Search, q, "The diagnosis codes could not be searched.");
  const [primary, setPrimary] = useState("");
  const shown = primary ? rows.filter((r) => String(r.valid_primary) === primary) : rows;
  const columns: Column<Icd10Row>[] = [
    { key: "code", header: "Code", render: (r) => <Ref className="font-medium text-ink-900">{r.code}</Ref> },
    { key: "description", header: "Diagnosis", render: (r) => <div><div className="text-ink-900">{r.description}</div><div className="text-xs text-ink-500">{r.chapter}</div></div> },
    { key: "primary", header: "Primary diagnosis", render: (r) => r.valid_primary ? <Badge tone="ok">May head a claim</Badge> : <Badge>Secondary only</Badge> },
  ];
  return (
    <>
      <SearchBar value={q} onChange={setQ} placeholder="Code, or words in the diagnosis">
        <Select aria-label="Primary diagnosis" value={primary} onChange={(e) => setPrimary(e.target.value)}>
          <option value="">Primary or secondary</option><option value="true">May head a claim</option><option value="false">Secondary only</option>
        </Select>
      </SearchBar>
      {error ? <ErrorBlock message={error} /> : (
        <DataTable columns={columns} rows={shown} rowKey={(r) => r.code} loading={loading} empty={<EmptyState title="No diagnosis matches" body="Search by code or by a word in the diagnosis." />} footer={capped(rows.length, "codes")} />
      )}
    </>
  );
}

function Awards() {
  const [classes, setClasses] = useState<AwardClass[] | null>(null);
  const [injury, setInjury] = useState("");
  const [severity, setSeverity] = useState("");
  const [band, setBand] = useState<AwardBand | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.awardClasses().then((c) => { setClasses(c); if (c.length) setInjury(c[0].injury_class); }).catch((e) => { setClasses([]); setError(message(e, "The awards could not be loaded.")); });
  }, []);
  useEffect(() => {
    if (!injury) return;
    setLoading(true);
    api.awardBand(injury, severity || undefined).then((b) => { setBand(b); setError(null); }).catch((e) => setError(message(e, "The awards could not be loaded."))).finally(() => setLoading(false));
  }, [injury, severity]);
  const tiers = classes?.find((c) => c.injury_class === injury)?.severity_tiers ?? [];
  const columns: Column<AwardAuthority>[] = [
    { key: "case", header: "Case", render: (a) => <div><div className="font-medium text-ink-900">{a.citation}</div>{a.notes && <div className="max-w-[52ch] text-xs text-ink-500">{a.notes}</div>}</div> },
    { key: "court", header: "Court", render: (a) => <span className="text-ink-700">{a.court}</span> },
    { key: "severity", header: "Severity", render: (a) => <span className="text-ink-700">{plain(a.severity_tier)}</span> },
    { key: "year", header: "Year", align: "right", render: (a) => <span className="tnum">{a.award_year}</span> },
    { key: "award", header: "Award", align: "right", render: (a) => <span className="tnum text-ink-600">{rand(a.award_rand)}</span> },
    { key: "today", header: band ? `In ${band.current_year} money` : "Adjusted", align: "right", render: (a) => <span className="tnum font-medium text-ink-900">{rand(a.adjusted)}</span> },
  ];
  if (classes !== null && classes.length === 0) return error ? <ErrorBlock message={error} /> : <div className="rounded-lg border border-line bg-white shadow-panel"><EmptyState title="No comparable awards are loaded" body="Awards are loaded with the reference data." /></div>;
  return (
    <>
      <div className="mb-3 grid gap-2 rounded-lg border border-line bg-white p-3 shadow-panel sm:grid-cols-4">
        <Select className="sm:col-span-2" aria-label="Injury" value={injury} onChange={(e) => { setInjury(e.target.value); setSeverity(""); }}>
          {(classes ?? []).map((c) => <option key={c.injury_class} value={c.injury_class}>{plain(c.injury_class)}</option>)}
        </Select>
        <Select aria-label="Severity" value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="">Any severity</option>
          {tiers.map((s) => <option key={s} value={s}>{plain(s)}</option>)}
        </Select>
      </div>
      {error ? <ErrorBlock message={error} /> : band && (
        <>
          {band.robust && band.band_p25 != null ? (
            <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Stat label="Usual range, from" value={rand(band.band_p25)} hint="A quarter of awards are below this" />
              <Stat label="Middle award" value={rand(band.band_median ?? 0)} tone="ok" />
              <Stat label="Usual range, to" value={rand(band.band_p75 ?? 0)} hint="A quarter of awards are above this" />
              <Stat label="Lowest to highest" value={`${rand(band.band_min ?? 0)} to ${rand(band.band_max ?? 0)}`} hint={`${band.n} awards, in ${band.current_year} money`} />
            </div>
          ) : (
            <div className="mb-3 rounded-lg border border-warn-line bg-warn-bg px-4 py-3 text-sm text-warn-fg">
              There {band.n === 1 ? "is 1 award" : `are ${band.n} awards`} for this injury, which is too few to give a reliable range. Use the cases below as individual guides.
            </div>
          )}
          <DataTable columns={columns} rows={band.awards} rowKey={(a) => `${a.citation}:${a.award_year}:${a.award_rand}`} loading={loading} empty={<EmptyState title="No award for this injury and severity" body="Choose another severity." />} />
        </>
      )}
    </>
  );
}
