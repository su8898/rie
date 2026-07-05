// Reference data — the L0 layer as its own front door.
//
// The stores every medical claim is priced and validated against: the RAF tariff
// (RPL), NAPPI single-exit prices, the ICD-10 diagnosis vocabulary, and the
// comparable-awards quantum store — plus the edition provenance that stamps each
// determination. Read-only here (the enforcement overlays — statutory caps,
// negotiated rates, pre-auth gates — are edited in Admin). Built to grow: new
// datasets slot in as their own tab, and the Overview reflects whatever's loaded.

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../api";
import {
  Card,
  CodePill,
  Empty,
  ErrorBox,
  Loading,
  Pagination,
  SearchInput,
  YesNo,
  matchQ,
  usePaged,
} from "../components/ui";
import { num, rand } from "../format";
import type {
  AwardBand,
  AwardClass,
  Icd10Row,
  NappiRow,
  RefEdition,
  TariffRate,
} from "../types";

const LIMIT = 200; // server cap per reference search
type Tab = "overview" | "tariffs" | "nappi" | "icd10" | "awards";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "tariffs", label: "Tariff (RPL)" },
  { key: "nappi", label: "NAPPI" },
  { key: "icd10", label: "ICD-10" },
  { key: "awards", label: "Comparable awards" },
];

const th =
  "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";

// A debounced server search over one reference dataset. Empty query returns the
// first page; a full page (=LIMIT rows) means the result was truncated.
function useRefSearch<T>(fetcher: (q: string) => Promise<T[]>) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<T[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const handle = setTimeout(
      () => {
        setRows(null);
        setError(null);
        fetcher(q)
          .then((r) => alive && setRows(r))
          .catch(
            (e) =>
              alive &&
              setError(e instanceof ApiError ? e.message : "Failed to load"),
          );
      },
      q ? 250 : 0,
    );
    return () => {
      alive = false;
      clearTimeout(handle);
    };
  }, [q, fetcher]);
  return { q, setQ, rows, error };
}

export default function ReferencePage() {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Reference data</h1>
        <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
          The L0 layer every medical claim is priced and validated against —
          payable = min(billed, reference). Read-only here; the enforcement
          overlays (caps, negotiated rates, pre-auth) are edited in Admin. Built
          to grow: new datasets appear as they're loaded.
        </p>
      </header>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition ${
              tab === t.key
                ? "border-slate-900 text-slate-900"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "tariffs" && <TariffsTab />}
      {tab === "nappi" && <NappiTab />}
      {tab === "icd10" && <Icd10Tab />}
      {tab === "awards" && <AwardsTab />}
    </div>
  );
}

// ── Overview — provenance + how pricing reads each store ──────────────────────
function OverviewTab() {
  const [editions, setEditions] = useState<RefEdition[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .editions()
      .then((e) => alive && setEditions(e))
      .catch(
        (e) =>
          alive &&
          setError(e instanceof ApiError ? e.message : "Failed to load"),
      );
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="space-y-4">
      <Card
        title="Loaded editions"
        sub="Every reference dataset the engine reads, with the version stamped onto each determination it produces (provenance, P5). As new sources are ingested — hospital tariff, PMB list, gap rates — they appear here."
      >
        {error ? (
          <ErrorBox message={error} />
        ) : editions === null ? (
          <Loading label="Loading editions…" />
        ) : editions.length === 0 ? (
          <Empty label="No reference editions loaded." />
        ) : (
          <div className="overflow-x-auto rounded-md border border-slate-100">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>Dataset</th>
                  <th className={`${th} text-left`}>Version</th>
                  <th className={`${th} text-right`}>Rows</th>
                  <th className={`${th} text-left`}>Synced</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {editions.map((e) => (
                  <tr key={`${e.kind}:${e.version}`} className="hover:bg-slate-50">
                    <td className="px-3 py-2">
                      <CodePill>{e.kind}</CodePill>
                    </td>
                    <td className="px-3 py-2 font-mono text-[13px] text-slate-700">
                      {e.version}
                    </td>
                    <td className="tnum px-3 py-2 text-right text-slate-700">
                      {num(e.n)}
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">
                      {e.synced_at ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title="How pricing reads these stores"
        sub="Each dataset plays a defined role in the assessment — this is the map from store to rule."
      >
        <dl className="grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">
          <Role
            k="Tariff (RPL)"
            v="the billing benchmark"
            note="payable = min(billed, reference) per discipline; a line billed above its RPL rate is repriced, not rejected."
          />
          <Role
            k="NAPPI"
            v="medicine & consumable cap"
            note="each item's Single Exit Price is the ceiling for a medicine or consumable line."
          />
          <Role
            k="ICD-10"
            v="the diagnosis vocabulary"
            note="claims are coded in ICD-10; only valid-primary codes may head a claim, and the dx must match the accident regions."
          />
          <Role
            k="Comparable awards"
            v="general-damages benchmark"
            note="a CPI-adjusted p25–p75 band per injury class benchmarks the general-damages head (§5d)."
          />
          <Role
            k="Statutory caps · negotiated · pre-auth"
            v="enforcement overlays (Admin)"
            note="the s17(4)(c) annual cap, negotiated ENFORCEABLE rates and pre-auth gates sit on top of the tariff — edited in Admin, applied by the engine."
          />
        </dl>
      </Card>
    </div>
  );
}

function Role({ k, v, note }: { k: string; v: string; note: string }) {
  return (
    <div>
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {k}
      </dt>
      <dd className="mt-0.5 text-sm font-medium text-slate-800">{v}</dd>
      <dd className="mt-0.5 text-xs leading-relaxed text-slate-500">{note}</dd>
    </div>
  );
}

// ── Tariff (RPL) ──────────────────────────────────────────────────────────────
function TariffsTab() {
  const { q, setQ, rows, error } = useRefSearch<TariffRate>(api.tariffSearch);
  const [disciplines, setDisciplines] = useState<string[]>([]);
  const [discipline, setDiscipline] = useState("");

  useEffect(() => {
    let alive = true;
    api.disciplines().then((d) => alive && setDisciplines(d));
    return () => {
      alive = false;
    };
  }, []);

  const filtered = useMemo(
    () => (rows ?? []).filter((r) => !discipline || r.discipline === discipline),
    [rows, discipline],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 25);
  const capped = rows != null && rows.length >= LIMIT;

  return (
    <Card
      title="RAF tariff — Recommended Price List (RPL)"
      sub="The authoritative billing reference: payable = min(billed, reference); the payment path reads THESE numbers. Search by code prefix, filter by discipline."
      right={
        <div className="flex items-center gap-2">
          <SearchInput
            value={q}
            onChange={setQ}
            placeholder="Tariff code prefix…"
            className="w-44"
          />
          <select
            value={discipline}
            onChange={(e) => setDiscipline(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
          >
            <option value="">All disciplines</option>
            {disciplines.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
      }
    >
      {error ? (
        <ErrorBox message={error} />
      ) : rows === null ? (
        <Loading label="Loading tariff…" />
      ) : total === 0 ? (
        <Empty label={q || discipline ? "No tariff codes match." : "No tariff rows."} />
      ) : (
        <div className="overflow-hidden rounded-md border border-slate-100">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>Code</th>
                  <th className={`${th} text-left`}>Discipline</th>
                  <th className={`${th} text-right`}>Rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((r) => (
                  <tr key={`${r.code}:${r.discipline}`} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-mono text-[13px] font-medium text-slate-900">
                      {r.code}
                    </td>
                    <td className="px-3 py-2 text-slate-600">{r.discipline}</td>
                    <td className="tnum px-3 py-2 text-right font-medium text-slate-800">
                      {rand(r.rate)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            pageCount={pageCount}
            total={total}
            onPage={setPage}
            unit="rates"
          />
        </div>
      )}
      {capped && <CappedHint />}
    </Card>
  );
}

// ── NAPPI ─────────────────────────────────────────────────────────────────────
function NappiTab() {
  const { q, setQ, rows, error } = useRefSearch<NappiRow>(api.nappiSearch);
  const { page, setPage, pageCount, total, slice } = usePaged(rows ?? [], 25);
  const capped = rows != null && rows.length >= LIMIT;

  return (
    <Card
      title="NAPPI — medicines & consumables"
      sub="Items priced at Single Exit Price (SEP) — the ceiling for a medicine or consumable line. A large table (hundreds of thousands of items); search by NAPPI code prefix to narrow."
      right={
        <SearchInput
          value={q}
          onChange={setQ}
          placeholder="NAPPI code prefix…"
          className="w-44"
        />
      }
    >
      {error ? (
        <ErrorBox message={error} />
      ) : rows === null ? (
        <Loading label="Loading NAPPI…" />
      ) : total === 0 ? (
        <Empty label={q ? "No NAPPI codes match." : "No NAPPI rows."} />
      ) : (
        <div className="overflow-hidden rounded-md border border-slate-100">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>NAPPI code</th>
                  <th className={`${th} text-right`}>SEP</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((r) => (
                  <tr key={r.nappi_code} className="hover:bg-slate-50">
                    <td className="px-3 py-2 font-mono text-[13px] font-medium text-slate-900">
                      {r.nappi_code}
                    </td>
                    <td className="tnum px-3 py-2 text-right font-medium text-slate-800">
                      {rand(r.sep)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            pageCount={pageCount}
            total={total}
            onPage={setPage}
            unit="items"
          />
        </div>
      )}
      {capped && <CappedHint />}
    </Card>
  );
}

// ── ICD-10 ────────────────────────────────────────────────────────────────────
function Icd10Tab() {
  const { q, setQ, rows, error } = useRefSearch<Icd10Row>(api.icd10Search);
  const { page, setPage, pageCount, total, slice } = usePaged(rows ?? [], 25);
  const capped = rows != null && rows.length >= LIMIT;

  return (
    <Card
      title="ICD-10 — diagnosis vocabulary"
      sub="The codes claims are diagnosed in; only a valid-primary code may head a claim, and the diagnosis must corroborate the accident regions. Search by code or description."
      right={
        <SearchInput
          value={q}
          onChange={setQ}
          placeholder="Code or description…"
          className="w-52"
        />
      }
    >
      {error ? (
        <ErrorBox message={error} />
      ) : rows === null ? (
        <Loading label="Loading ICD-10…" />
      ) : total === 0 ? (
        <Empty label={q ? "No diagnosis codes match." : "No ICD-10 rows."} />
      ) : (
        <div className="overflow-hidden rounded-md border border-slate-100">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className={`${th} text-left`}>Code</th>
                  <th className={`${th} text-left`}>Description</th>
                  <th className={`${th} text-left`}>Chapter</th>
                  <th className={`${th} text-center`}>Primary</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((r) => (
                  <tr key={r.code} className="align-top hover:bg-slate-50">
                    <td className="px-3 py-2 font-mono text-[13px] font-medium text-slate-900">
                      {r.code}
                    </td>
                    <td className="px-3 py-2 text-slate-700">{r.description}</td>
                    <td className="max-w-xs px-3 py-2 text-xs text-slate-500">
                      {r.chapter}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <YesNo value={r.valid_primary} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            pageCount={pageCount}
            total={total}
            onPage={setPage}
            unit="codes"
          />
        </div>
      )}
      {capped && <CappedHint />}
    </Card>
  );
}

// ── Comparable awards ─────────────────────────────────────────────────────────
function AwardsTab() {
  const [classes, setClasses] = useState<AwardClass[] | null>(null);
  const [injuryClass, setInjuryClass] = useState("");
  const [severity, setSeverity] = useState("");
  const [band, setBand] = useState<AwardBand | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .awardClasses()
      .then((c) => {
        if (!alive) return;
        setClasses(c);
        if (c.length && !injuryClass) setInjuryClass(c[0].injury_class);
      })
      .catch(
        (e) =>
          alive &&
          setError(e instanceof ApiError ? e.message : "Failed to load"),
      );
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async (cls: string, sev: string) => {
    if (!cls) {
      setBand(null);
      return;
    }
    try {
      setBand(await api.awardBand(cls, sev || undefined));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load band");
    }
  }, []);

  useEffect(() => {
    void load(injuryClass, severity);
  }, [injuryClass, severity, load]);

  const tiers =
    classes?.find((c) => c.injury_class === injuryClass)?.severity_tiers ?? [];

  const classList = useMemo(
    () => (classes ?? []).filter((c) => matchQ(q, c.injury_class)),
    [classes, q],
  );

  if (error) return <ErrorBox message={error} />;
  if (classes === null) return <Loading label="Loading award classes…" />;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="lg:col-span-1">
        <Card
          title="Injury classes"
          sub="Pick a class to see its CPI-adjusted quantum band and the authorities behind it."
          right={
            <SearchInput
              value={q}
              onChange={setQ}
              placeholder="Filter…"
              className="w-32"
            />
          }
        >
          {classList.length === 0 ? (
            <Empty label="No classes match." />
          ) : (
            <ul className="max-h-[28rem] space-y-1 overflow-y-auto">
              {classList.map((c) => (
                <li key={c.injury_class}>
                  <button
                    onClick={() => {
                      setInjuryClass(c.injury_class);
                      setSeverity("");
                    }}
                    className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm transition ${
                      c.injury_class === injuryClass
                        ? "border-slate-900 bg-slate-50"
                        : "border-slate-200 hover:bg-slate-50"
                    }`}
                  >
                    <span className="font-mono text-[13px] text-slate-800">
                      {c.injury_class}
                    </span>
                    <span className="text-[11px] text-slate-400">
                      {c.severity_tiers.length} tier
                      {c.severity_tiers.length === 1 ? "" : "s"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="lg:col-span-2">
        <Card
          title={`Comparable awards — ${injuryClass || "—"}`}
          sub="CPI-adjusted general-damages authorities; a p25–p75 band is only published when the class clears the robustness floor (§5d small-n guard). This is what a general-damages offer is benchmarked against."
          right={
            tiers.length > 0 ? (
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
                className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
              >
                <option value="">All tiers</option>
                {tiers.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            ) : undefined
          }
        >
          {band === null ? (
            <Loading label="Computing band…" />
          ) : (
            <div className="space-y-4">
              {band.robust &&
              band.band_p25 != null &&
              band.band_p75 != null ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <BandStat label="p25" value={rand(band.band_p25)} />
                  <BandStat
                    label="median"
                    value={rand(band.band_median ?? 0)}
                    accent="text-slate-900"
                  />
                  <BandStat label="p75" value={rand(band.band_p75)} />
                  <BandStat
                    label="range"
                    value={`${rand(band.band_min ?? 0)} – ${rand(band.band_max ?? 0)}`}
                    small
                  />
                </div>
              ) : (
                <div className="rounded-md border border-amber-200 bg-amber-50/60 p-3 text-xs text-amber-800">
                  Too few authorities for a robust band ({band.n} found; the §5d
                  guard needs more). The individual awards still show below.
                </div>
              )}

              <div className="text-xs text-slate-400">
                {band.n} authorit{band.n === 1 ? "y" : "ies"} · CPI-adjusted to{" "}
                {band.current_year}
                {band.robust ? " · robust" : " · small-n"}
              </div>

              {band.awards.length === 0 ? (
                <Empty label="No authorities for this class." />
              ) : (
                <div className="overflow-x-auto rounded-md border border-slate-100">
                  <table className="min-w-full divide-y divide-slate-100 text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className={`${th} text-left`}>Citation</th>
                        <th className={`${th} text-left`}>Court</th>
                        <th className={`${th} text-left`}>Tier</th>
                        <th className={`${th} text-right`}>Year</th>
                        <th className={`${th} text-right`}>Award</th>
                        <th className={`${th} text-right`}>Adjusted</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {band.awards.map((a, i) => (
                        <tr key={`${a.citation}-${i}`} className="align-top hover:bg-slate-50">
                          <td className="px-3 py-2 text-slate-800">
                            {a.citation}
                            {a.notes && (
                              <div className="mt-0.5 text-[11px] text-slate-400">
                                {a.notes}
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-2 text-slate-600">{a.court}</td>
                          <td className="px-3 py-2 text-slate-600">
                            {a.severity_tier}
                          </td>
                          <td className="tnum px-3 py-2 text-right text-slate-600">
                            {a.award_year}
                          </td>
                          <td className="tnum px-3 py-2 text-right text-slate-600">
                            {rand(a.award_rand)}
                          </td>
                          <td className="tnum px-3 py-2 text-right font-medium text-slate-800">
                            {rand(a.adjusted)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function BandStat({
  label,
  value,
  accent = "text-slate-800",
  small,
}: {
  label: string;
  value: string;
  accent?: string;
  small?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">
        {label}
      </div>
      <div
        className={`tnum mt-0.5 font-semibold ${small ? "text-sm" : "text-xl"} ${accent}`}
      >
        {value}
      </div>
    </div>
  );
}

function CappedHint() {
  return (
    <p className="mt-2 text-xs text-slate-400">
      Showing the first {LIMIT} matches — refine your search to narrow.
    </p>
  );
}
