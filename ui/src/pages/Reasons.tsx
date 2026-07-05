// The reason register — every rule the engine can fire, and how much authority
// each one carries (domain-logic §10/§11).
//
// Two gradings sit on each reason. MATURITY is the evidentiary grade of the
// basis: GROUNDED = statute- or case-cited (the law-backed hard gates);
// HEURISTIC = a measured, calibrated feature; UNVALIDATED = a new signal not
// yet proven. MODE is where the reason sits on the promotion lifecycle
// (§11): SHADOW (computed and stored, zero points, invisible) → ADVISORY
// (shown on the claim, still zero points) → SCORED (adds to the band) —
// earned, not asserted, via a measured precision floor. So only SCORED
// reasons move the score; a hard gate repudiates regardless of score; and an
// endogenous reason is derived from the claim's own data, not an external
// authority. A text filter spans code / category / basis / maturity / mode.

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError, api } from "../api";
import {
  Card,
  Empty,
  ErrorBox,
  Loading,
  MaturityChip,
  ModeChip,
  Pagination,
  SearchInput,
  usePaged,
} from "../components/ui";
import type { Reason } from "../types";

// A one-line reading of each maturity / mode value, shown as a legend so the
// chips in the table are self-explanatory (§10 maturity, §11 mode).
const MATURITY_LEGEND: { key: string; note: string }[] = [
  { key: "GROUNDED", note: "statute- or case-cited — the law-backed hard gates" },
  { key: "HEURISTIC", note: "a measured, calibrated feature (corpus percentiles)" },
  { key: "UNVALIDATED", note: "a new signal, not yet proven — shadow-only" },
];
const MODE_LEGEND: { key: string; note: string }[] = [
  { key: "SHADOW", note: "computed & stored, zero points, invisible to handlers" },
  { key: "ADVISORY", note: "shown on the claim, still zero points" },
  { key: "SCORED", note: "earned the precision floor — adds to the band" },
];

export default function ReasonsPage() {
  const [rows, setRows] = useState<Reason[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .reasons()
      .then((r) => alive && setRows(r))
      .catch((e) =>
        alive && setError(e instanceof ApiError ? e.message : "Failed to load"),
      );
    return () => {
      alive = false;
    };
  }, []);

  const filtered = useMemo(() => {
    if (!rows) return null;
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(
      (r) =>
        r.code.toLowerCase().includes(needle) ||
        r.category.toLowerCase().includes(needle) ||
        r.basis.toLowerCase().includes(needle) ||
        r.maturity.toLowerCase().includes(needle) ||
        r.mode.toLowerCase().includes(needle),
    );
  }, [rows, q]);

  const { page, setPage, pageCount, total, slice } = usePaged(
    filtered ?? [],
    25,
  );

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">
          Reason catalogue
        </h1>
        <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
          Every reason the engine can fire, graded twice. Maturity is the
          evidentiary grade — GROUNDED is a law-cited hard gate, HEURISTIC is a
          measured feature, UNVALIDATED is shadow-only (§10). Mode is the
          promotion lifecycle: SHADOW → ADVISORY → SCORED, earned via a measured
          precision floor, never asserted (§11). Only SCORED reasons add points;
          hard gates repudiate regardless of score; endogenous reasons derive
          from the claim's own data.
        </p>
      </header>

      {error ? (
        <ErrorBox message={error} />
      ) : filtered === null ? (
        <Loading label="Loading catalogue…" />
      ) : (
        <Card
          title="Reason register"
          sub="One row per rule. Read the columns together: Maturity is how the basis is grounded, Mode is whether it scores today, Hard marks a gate that repudiates on its own, Points is the band weight (nonzero only when SCORED), Endogenous marks a reason derived from the claim's own data, and Basis is the citation or method behind it. A GROUNDED + SCORED + hard row is a law-cited gate; a SHADOW row is computed but invisible and contributes nothing yet."
          right={
            <SearchInput
              value={q}
              onChange={setQ}
              placeholder="Filter code, category, basis…"
              className="w-72"
            />
          }
        >
          {/* How to read the maturity / mode chips (§10, §11). */}
          <div className="mb-3 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
            <Legend title="Maturity — how the basis is grounded" items={MATURITY_LEGEND}>
              {(k) => <MaturityChip maturity={k} />}
            </Legend>
            <Legend title="Mode — whether it scores (§11 lifecycle)" items={MODE_LEGEND}>
              {(k) => <ModeChip mode={k} />}
            </Legend>
          </div>

          {filtered.length === 0 ? (
            <Empty label="No reason codes match your filter." />
          ) : (
            <div className="overflow-hidden rounded-md border border-slate-100">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100 text-sm">
                  <thead className="bg-slate-50">
                    <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                      <th className="px-4 py-2">Code</th>
                      <th className="px-4 py-2">Category</th>
                      <th className="px-4 py-2">Maturity</th>
                      <th className="px-4 py-2">Mode</th>
                      <th className="px-4 py-2 text-center">Hard</th>
                      <th className="px-4 py-2 text-right">Points</th>
                      <th className="px-4 py-2 text-center">Endo.</th>
                      <th className="px-4 py-2">Basis</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {slice.map((r) => (
                      <tr key={r.code} className="align-top transition hover:bg-slate-50">
                        <td className="px-4 py-2 font-mono text-[13px] font-medium text-slate-900">
                          {r.code}
                        </td>
                        <td className="px-4 py-2 text-slate-600">{r.category}</td>
                        <td className="px-4 py-2">
                          <MaturityChip maturity={r.maturity} />
                        </td>
                        <td className="px-4 py-2">
                          <ModeChip mode={r.mode} />
                        </td>
                        <td className="px-4 py-2 text-center">
                          {r.hard ? (
                            <span className="text-rose-600" title="hard gate — repudiates regardless of score">
                              ●
                            </span>
                          ) : (
                            <span className="text-slate-200" title="soft — contributes to the score only">
                              ○
                            </span>
                          )}
                        </td>
                        <td className="tnum px-4 py-2 text-right text-slate-700">
                          {r.mode === "SCORED" ? (
                            r.points
                          ) : (
                            <span className="text-slate-300" title="not SCORED — contributes zero points">
                              {r.points}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-center">
                          {r.endogenous ? (
                            <span className="text-slate-500" title="endogenous — derived from the claim's own data">
                              ✓
                            </span>
                          ) : (
                            <span className="text-slate-200" title="exogenous — from an external authority">
                              —
                            </span>
                          )}
                        </td>
                        <td className="max-w-md px-4 py-2 text-xs leading-relaxed text-slate-500">
                          {r.basis || "—"}
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
                unit={`of ${rows?.length ?? 0} reason codes`}
              />
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

// A compact chip → meaning key for a set of enum values, so the coloured chips
// in the table can be read without leaving the page.
function Legend({
  title,
  items,
  children,
}: {
  title: string;
  items: { key: string; note: string }[];
  children: (key: string) => ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </div>
      <dl className="space-y-1">
        {items.map((it) => (
          <div key={it.key} className="flex items-baseline gap-2">
            <dt className="shrink-0">{children(it.key)}</dt>
            <dd className="text-[11px] leading-relaxed text-slate-500">
              {it.note}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
