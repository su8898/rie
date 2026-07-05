// Accident graph — the corroboration substrate (domain-logic §6).
//
// Claims don't stand alone: every claim carries a mandatory SAPS case number,
// and claims sharing that number (normalised) plus overlapping parties are
// resolved onto ONE accident record — one accident → 1..n claims, one per
// injured party. Convergence then scores how independently that accident is
// corroborated. This graph is the substrate the collusion signals read
// (RING_PARTIES, CLAIMANT_SURGE, CONVERGENCE_THIN) — where staged-accident
// rings become visible as shared parties across otherwise-unrelated claims.

import { useEffect, useMemo, useState } from "react";
import { ApiError, api } from "../api";
import {
  Card,
  ConvergenceBar,
  Empty,
  ErrorBox,
  Loading,
  Pagination,
  SearchInput,
  matchQ,
  usePaged,
} from "../components/ui";
import type { Accident } from "../types";

const th =
  "px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500";

export default function AccidentsPage() {
  const [rows, setRows] = useState<Accident[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  const filtered = useMemo(
    () =>
      (rows ?? []).filter((a) =>
        matchQ(q, a.accident_id, a.case_number, a.where, a.parties.join(" ")),
      ),
    [rows, q],
  );
  const { page, setPage, pageCount, total, slice } = usePaged(filtered, 25);

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
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Accidents</h1>
        <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
          Claims are joined into accidents by SAPS case number and shared
          parties — one accident, 1..n claims, one per injured party (§6). Each
          accident carries a convergence score: how independently its existence
          is corroborated across sources that don't coordinate. The engine treats
          convergence as proof, not any single document — and this graph is the
          substrate for spotting staged-accident rings, where the same parties
          recur across supposedly unrelated claims.
        </p>
      </header>

      {error ? (
        <ErrorBox message={error} />
      ) : rows === null ? (
        <Loading label="Loading accident graph…" />
      ) : (
        <Card
          title="Accident graph"
          sub="One row = one resolved accident (matched on normalised case number + fuzzy date/place/vehicle/party). Convergence 0–100 is independence-weighted agreement across source classes — a co-cluster of records counts as one vote; ~66+ auto-clears existence, low routes to review, and BOTH tails matter (a thin trail is a flag, but so is a suspiciously dense one). n_claims and parties size the accident: parties are POPIA HMAC pseudonyms (A_/P_ tokens, never names), and a party appearing across many accidents is a ring edge."
          right={
            <SearchInput
              value={q}
              onChange={setQ}
              placeholder="Search accident, case or party id…"
            />
          }
        >
          {filtered.length === 0 ? (
            <Empty
              label={
                q
                  ? "No accidents match your search."
                  : "No accidents in the graph yet."
              }
            />
          ) : (
            <div className="overflow-hidden rounded-md border border-slate-100">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100 text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className={th}>Accident</th>
                      <th className={th}>Case number</th>
                      <th className={th}>When</th>
                      <th className={th}>
                        Convergence
                        <span className="ml-1 font-normal normal-case tracking-normal text-slate-400">
                          (0–100)
                        </span>
                      </th>
                      <th className={`${th} text-right`}>Claims</th>
                      <th className={th}>Parties</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {slice.map((a) => (
                      <tr
                        key={a.accident_id}
                        className="align-top transition hover:bg-slate-50"
                      >
                        <td className="px-4 py-2.5 font-mono text-[13px] text-slate-800">
                          {a.accident_id}
                          {a.where && (
                            <div className="text-[11px] text-slate-400">
                              {a.where}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-slate-600">
                          {a.case_number ?? (
                            <span
                              className="text-slate-400"
                              title="No SAPS case number resolved yet — OAR_PENDING (early-supplier window); the OAR_MISSING gate applies at validation, not ingest (§4b, §6)."
                            >
                              — pending
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-slate-600">{a.when}</td>
                        <td className="px-4 py-2.5">
                          <ConvergenceBar value={a.convergence} />
                        </td>
                        <td className="tnum px-4 py-2.5 text-right font-medium text-slate-800">
                          {a.n_claims}
                          {a.oar_occupants != null && (
                            <div
                              className="text-[11px] font-normal text-slate-400"
                              title="Claims lodged vs occupants on the SAPS accident report (OAR). Claimants far exceeding occupants is the classic CLAIMANT_SURGE tell — cohort-aware (a bus is not a hatchback). OAR counts carry LOW confidence until independently corroborated (§4b, §6)."
                            >
                              of {a.oar_occupants} occ.
                            </div>
                          )}
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
        </Card>
      )}
    </div>
  );
}
