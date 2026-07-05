// The full reason-code catalogue. Colour-coded maturity (GROUNDED / HEURISTIC
// / UNVALIDATED) and mode (SHADOW / ADVISORY / SCORED) chips, with a text
// filter across code / category / basis.

import { useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../api";
import {
  Empty,
  ErrorBox,
  Loading,
  MaturityChip,
  ModeChip,
} from "../components/ui";
import type { Reason } from "../types";

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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900">
          Reason catalogue
        </h1>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter code, category, basis…"
          className="w-72 rounded-md border border-slate-300 px-3 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500"
        />
      </div>

      {error ? (
        <ErrorBox message={error} />
      ) : filtered === null ? (
        <Loading label="Loading catalogue…" />
      ) : filtered.length === 0 ? (
        <Empty label="No reason codes match your filter." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-2.5">Code</th>
                  <th className="px-4 py-2.5">Category</th>
                  <th className="px-4 py-2.5">Maturity</th>
                  <th className="px-4 py-2.5">Mode</th>
                  <th className="px-4 py-2.5 text-center">Hard</th>
                  <th className="px-4 py-2.5 text-right">Points</th>
                  <th className="px-4 py-2.5 text-center">Endo.</th>
                  <th className="px-4 py-2.5">Basis</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((r) => (
                  <tr key={r.code} className="align-top transition hover:bg-slate-50">
                    <td className="px-4 py-2.5 font-mono text-[13px] font-medium text-slate-900">
                      {r.code}
                    </td>
                    <td className="px-4 py-2.5 text-slate-600">{r.category}</td>
                    <td className="px-4 py-2.5">
                      <MaturityChip maturity={r.maturity} />
                    </td>
                    <td className="px-4 py-2.5">
                      <ModeChip mode={r.mode} />
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      {r.hard ? (
                        <span className="text-rose-600" title="hard gate">
                          ●
                        </span>
                      ) : (
                        <span className="text-slate-200">○</span>
                      )}
                    </td>
                    <td className="tnum px-4 py-2.5 text-right text-slate-700">
                      {r.points}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      {r.endogenous ? (
                        <span className="text-slate-500" title="endogenous">
                          ✓
                        </span>
                      ) : (
                        <span className="text-slate-200">—</span>
                      )}
                    </td>
                    <td className="max-w-md px-4 py-2.5 text-xs leading-relaxed text-slate-500">
                      {r.basis || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-slate-100 px-4 py-2 text-xs text-slate-400">
            {filtered.length} of {rows?.length ?? 0} reason codes
          </div>
        </div>
      )}
    </div>
  );
}
