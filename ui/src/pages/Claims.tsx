// Filterable determination table (band + disposition dropdowns). Each row
// links to /claims/:id. Filters are pushed to the server via query params.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import {
  BandChip,
  DispositionChip,
  Empty,
  ErrorBox,
  Loading,
  YesNo,
} from "../components/ui";
import { rand } from "../format";
import type { Band, Determination, Disposition } from "../types";

const BAND_OPTS: Band[] = ["GREEN", "AMBER", "RED"];
const DISP_OPTS: Disposition[] = [
  "FRAUD",
  "MERITS",
  "COMPLIANCE",
  "PREAUTH",
  "SI_GATE",
  "ADJUSTED",
  "CLEAN",
];

export default function ClaimsPage() {
  const [rows, setRows] = useState<Determination[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [band, setBand] = useState("");
  const [disposition, setDisposition] = useState("");

  useEffect(() => {
    let alive = true;
    setRows(null);
    setError(null);
    api
      .listClaims({
        band: band || undefined,
        disposition: disposition || undefined,
        limit: 200,
      })
      .then((r) => alive && setRows(r))
      .catch((e) =>
        alive && setError(e instanceof ApiError ? e.message : "Failed to load"),
      );
    return () => {
      alive = false;
    };
  }, [band, disposition]);

  const selectCls =
    "rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900">Claims</h1>
        <div className="flex items-center gap-2">
          <select
            value={band}
            onChange={(e) => setBand(e.target.value)}
            className={selectCls}
            aria-label="Filter by band"
          >
            <option value="">All bands</option>
            {BAND_OPTS.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
          <select
            value={disposition}
            onChange={(e) => setDisposition(e.target.value)}
            className={selectCls}
            aria-label="Filter by disposition"
          >
            <option value="">All dispositions</option>
            {DISP_OPTS.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
          {(band || disposition) && (
            <button
              onClick={() => {
                setBand("");
                setDisposition("");
              }}
              className="rounded-md border border-slate-300 px-2.5 py-1.5 text-sm text-slate-600 transition hover:bg-slate-100"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {error ? (
        <ErrorBox message={error} />
      ) : rows === null ? (
        <Loading label="Loading claims…" />
      ) : rows.length === 0 ? (
        <Empty label="No determinations match these filters." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-2.5">Claim</th>
                  <th className="px-4 py-2.5">Band</th>
                  <th className="px-4 py-2.5">Disposition</th>
                  <th className="px-4 py-2.5 text-right">Score</th>
                  <th className="px-4 py-2.5 text-right">Medical</th>
                  <th className="px-4 py-2.5 text-right">Net</th>
                  <th className="px-4 py-2.5 text-center">Eligible</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.id} className="transition hover:bg-slate-50">
                    <td className="px-4 py-2.5">
                      <Link
                        to={`/claims/${encodeURIComponent(r.claim_id)}`}
                        className="font-mono text-[13px] font-medium text-slate-900 hover:text-blue-600 hover:underline"
                      >
                        {r.claim_id}
                      </Link>
                      <div className="text-[11px] text-slate-400">
                        {r.accident_id}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <BandChip band={r.band} />
                    </td>
                    <td className="px-4 py-2.5">
                      <DispositionChip disposition={r.disposition} />
                    </td>
                    <td className="tnum px-4 py-2.5 text-right text-slate-700">
                      {r.score}
                    </td>
                    <td className="tnum px-4 py-2.5 text-right text-slate-700">
                      {rand(r.medical_payable)}
                    </td>
                    <td className="tnum px-4 py-2.5 text-right font-medium text-slate-900">
                      {rand(r.net_payable)}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <YesNo value={r.eligible_to_pay} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-slate-100 px-4 py-2 text-xs text-slate-400">
            {rows.length} determination{rows.length === 1 ? "" : "s"}
          </div>
        </div>
      )}
    </div>
  );
}
