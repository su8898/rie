// Claims — the determination table: every submitted claim the engine has scored,
// filterable by band + disposition and searchable across the full corpus.
//
// A determination is one claim's verdict on two orthogonal axes. The risk axis is
// the score → band read (GREEN [0,25) · AMBER [25,50) · RED [50,∞), domain-logic §;
// higher score = more to answer for). The routing axis is the worst-wins disposition
// (§9): the single most severe reason wins, so a claim sits in exactly one lane —
// FRAUD ▸ MERITS ▸ COMPLIANCE ▸ PREAUTH ▸ SI_GATE ▸ ADJUSTED ▸ CLEAN. The money is
// what the payment path reads: net payable = min(billed, reference) summed across the
// six heads of damage after gates & apportionment; eligible-to-pay means the claim
// cleared its gates and can be pulled into a payment batch. Each row links to the
// full determination at /claims/:id.
//
// Filters (band + disposition + needs-review) and the search box push to the
// server via query params; the search is debounced so typing doesn't fire a
// request per keystroke. Paging is server-side (limit/offset + X-Total-Count),
// so the whole corpus is reachable and the total is the real total — the
// server returns one row per claim, its latest determination (H9).

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import {
  BandChip,
  Card,
  DispositionChip,
  Empty,
  ErrorBox,
  Loading,
  Pagination,
  SearchInput,
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
  "REVIEW",
  "ADJUSTED",
  "CLEAN",
];

const PAGE_SIZE = 25;

const selectCls =
  "rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const th =
  "px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500";

export default function ClaimsPage() {
  const [rows, setRows] = useState<Determination[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [band, setBand] = useState("");
  const [disposition, setDisposition] = useState("");
  const [needsReview, setNeedsReview] = useState(false);
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);

  // Any filter change starts again from the first page.
  useEffect(() => {
    setPage(0);
  }, [band, disposition, needsReview, q]);

  useEffect(() => {
    let alive = true;
    // Debounce the search so typing doesn't fire a request per keystroke;
    // band / disposition / page changes settle just as quickly.
    const handle = setTimeout(() => {
      setRows(null);
      setError(null);
      api
        .listClaimsPage({
          band: band || undefined,
          disposition: disposition || undefined,
          q: q || undefined,
          needsReview: needsReview || undefined,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
        })
        .then((r) => {
          if (!alive) return;
          setRows(r.rows);
          setTotal(r.total);
        })
        .catch((e) =>
          alive &&
          setError(e instanceof ApiError ? e.message : "Failed to load"),
        );
    }, 250);
    return () => {
      alive = false;
      clearTimeout(handle);
    };
  }, [band, disposition, needsReview, q, page]);

  const filtered = band || disposition || q || needsReview;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const slice = rows ?? [];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Claims</h1>
        <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
          Every submitted claim the engine has scored into a risk{" "}
          <span className="font-medium text-slate-600">band</span> (GREEN / AMBER /
          RED, by score) and routed to a worst-wins{" "}
          <span className="font-medium text-slate-600">disposition</span> (§9 — the
          single most severe reason wins). Net payable = min(billed, reference)
          across the six heads of damage after gates; eligible-to-pay means it
          cleared the gate and can join a payment batch. Read the money as what the
          payment path will pay, not what was billed.
        </p>
      </header>

      <Card
        title="Determinations"
        sub="One row per claim. Band is the risk read (higher score = more to answer for); disposition is where it routes, worst-first (§9). Net is what the payment path pays — min(billed, reference) across the six heads after gates, not the billed amount; Medical is the two medical heads within it. Eligible ✓ means the claim cleared its gates and is ready for a batch."
        right={
          <div className="flex flex-wrap items-center gap-2">
            <SearchInput
              value={q}
              onChange={setQ}
              placeholder="Search claim or accident id…"
              className="w-56"
            />
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
            <label className="flex items-center gap-1.5 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={needsReview}
                onChange={(e) => setNeedsReview(e.target.checked)}
                className="h-3.5 w-3.5 rounded border-slate-300"
              />
              Needs review
            </label>
            {filtered && (
              <button
                onClick={() => {
                  setBand("");
                  setDisposition("");
                  setNeedsReview(false);
                  setQ("");
                }}
                className="rounded-md border border-slate-300 px-2.5 py-1.5 text-sm text-slate-600 transition hover:bg-slate-100"
              >
                Clear
              </button>
            )}
          </div>
        }
      >
        {error ? (
          <ErrorBox message={error} />
        ) : rows === null ? (
          <Loading label="Loading claims…" />
        ) : rows.length === 0 ? (
          <Empty
            label={
              filtered
                ? "No determinations match these filters."
                : "No determinations yet."
            }
          />
        ) : (
          <div className="overflow-hidden rounded-md border border-slate-100">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className={`${th} text-left`}>Claim / accident</th>
                    <th className={`${th} text-left`}>Band</th>
                    <th className={`${th} text-left`}>Disposition</th>
                    <th className={`${th} text-right`}>Score</th>
                    <th className={`${th} text-right`}>Medical</th>
                    <th className={`${th} text-right`}>Net</th>
                    <th className={`${th} text-center`}>Eligible</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {slice.map((r) => (
                    <tr key={r.id} className="transition hover:bg-slate-50">
                      <td className="px-4 py-2.5">
                        <Link
                          to={`/claims/${encodeURIComponent(r.claim_id)}`}
                          className="font-mono text-[13px] font-medium text-slate-900 hover:text-blue-600 hover:underline"
                        >
                          {r.claim_id}
                        </Link>
                        <div className="font-mono text-[11px] text-slate-400">
                          {r.accident_id}
                          {r.accident_candidate && (
                            <span
                              className="ml-1.5 rounded bg-violet-50 px-1 py-px font-sans text-[10px] font-medium text-violet-700"
                              title={`WORKLIST — fuzzy match to ${r.accident_candidate}; a human confirms the join`}
                            >
                              worklist
                            </span>
                          )}
                          {r.needs_review && (
                            <span
                              className="ml-1.5 rounded bg-fuchsia-50 px-1 py-px font-sans text-[10px] font-medium text-fuchsia-700"
                              title="A billed code has no benchmark — R&N review before payment"
                            >
                              needs review
                            </span>
                          )}
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
            <Pagination
              page={page}
              pageCount={pageCount}
              total={total}
              onPage={setPage}
              unit="claims"
            />
          </div>
        )}
        <p className="mt-2 text-xs text-slate-400">
          Score → band: GREEN{" "}
          <span className="tnum text-slate-500">[0, 25)</span> auto-clears · AMBER{" "}
          <span className="tnum text-slate-500">[25, 50)</span> needs a look · RED{" "}
          <span className="tnum text-slate-500">[50, ∞)</span> worked first. Band
          and disposition are independent — a GREEN claim can still route non-CLEAN
          on a payment-rule adjustment, and a RED score does not by itself withhold
          payment.
        </p>
      </Card>
    </div>
  );
}
