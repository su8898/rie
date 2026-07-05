// Accident graph table. Convergence shown as a 0–100 bar; plus n_claims,
// case number, and parties.

import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import {
  ConvergenceBar,
  Empty,
  ErrorBox,
  Loading,
  Pagination,
  usePaged,
} from "../components/ui";
import type { Accident } from "../types";

export default function AccidentsPage() {
  const [rows, setRows] = useState<Accident[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { page, setPage, pageCount, total, slice } = usePaged(rows ?? [], 25);

  useEffect(() => {
    let alive = true;
    api
      .accidents()
      .then((r) => alive && setRows(r))
      .catch((e) =>
        alive && setError(e instanceof ApiError ? e.message : "Failed to load"),
      );
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-slate-900">Accidents</h1>

      {error ? (
        <ErrorBox message={error} />
      ) : rows === null ? (
        <Loading label="Loading accident graph…" />
      ) : rows.length === 0 ? (
        <Empty label="No accidents in the graph yet." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-2.5">Accident</th>
                  <th className="px-4 py-2.5">Case number</th>
                  <th className="px-4 py-2.5">When</th>
                  <th className="px-4 py-2.5">Convergence</th>
                  <th className="px-4 py-2.5 text-right">Claims</th>
                  <th className="px-4 py-2.5">Parties</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {slice.map((a) => (
                  <tr key={a.accident_id} className="align-top transition hover:bg-slate-50">
                    <td className="px-4 py-2.5 font-mono text-[13px] text-slate-800">
                      {a.accident_id}
                      {a.where && (
                        <div className="text-[11px] text-slate-400">
                          {a.where}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-slate-600">
                      {a.case_number ?? "—"}
                    </td>
                    <td className="px-4 py-2.5 text-slate-600">{a.when}</td>
                    <td className="px-4 py-2.5">
                      <ConvergenceBar value={a.convergence} />
                    </td>
                    <td className="tnum px-4 py-2.5 text-right font-medium text-slate-800">
                      {a.n_claims}
                    </td>
                    <td className="px-4 py-2.5">
                      {a.parties.length === 0 ? (
                        <span className="text-slate-300">—</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {a.parties.map((p) => (
                            <span
                              key={p}
                              className="inline-flex items-center rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600"
                            >
                              {p}
                            </span>
                          ))}
                        </div>
                      )}
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
            unit="accidents"
          />
        </div>
      )}
    </div>
  );
}
