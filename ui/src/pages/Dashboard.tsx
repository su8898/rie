// Portfolio snapshot from GET /api/dashboard — the state of the book in one view:
// how many claims the engine has determined, how they split by risk band and by
// disposition, how many cleared the gate to pay, and the rand on the payment path.
//
// Band is the risk read (GREEN [0,25) · AMBER [25,50) · RED [50,∞), domain-logic §; higher
// score = more to answer for). Disposition is the routing verdict, worst-wins (§9):
// FRAUD ▸ MERITS ▸ COMPLIANCE ▸ PREAUTH ▸ SI_GATE ▸ ADJUSTED ▸ CLEAN. Money is what the
// payment path reads: payable = min(billed, reference), summed across the six heads of
// damage after gates and apportionment.

import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { Card, DispositionChip, ErrorBox, Loading, Stat } from "../components/ui";
import { num, rand } from "../format";
import type { Band, Dashboard, Disposition } from "../types";

const BANDS: { key: Band; label: string; bar: string; text: string }[] = [
  { key: "GREEN", label: "Green", bar: "bg-emerald-500", text: "text-emerald-700" },
  { key: "AMBER", label: "Amber", bar: "bg-amber-500", text: "text-amber-700" },
  { key: "RED", label: "Red", bar: "bg-rose-500", text: "text-rose-700" },
];

const DISP_ORDER: Disposition[] = [
  "FRAUD",
  "MERITS",
  "COMPLIANCE",
  "PREAUTH",
  "SI_GATE",
  "ADJUSTED",
  "CLEAN",
];

// One-line outcome per disposition (domain-logic §9) — what a claim in this lane needs next.
const DISP_OUTCOME: Record<Disposition, string> = {
  FRAUD: "investigate — opens a case",
  MERITS: "merits determination / repudiation",
  COMPLIANCE: "request documents · cure · reject",
  PREAUTH: "obtain authorisation or reject the invoice",
  SI_GATE: "RAF 4 serious-injury process",
  ADJUSTED: "auto-adjudicated, no human",
  CLEAN: "paid / offered as computed",
};

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .dashboard()
      .then((d) => alive && setData(d))
      .catch((e) =>
        alive && setError(e instanceof ApiError ? e.message : "Failed to load"),
      );
    return () => {
      alive = false;
    };
  }, []);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loading label="Loading portfolio…" />;

  const bandTotal = data.by_band.GREEN + data.by_band.AMBER + data.by_band.RED;
  const eligiblePct =
    data.determinations > 0
      ? Math.round((data.eligible_to_pay / data.determinations) * 100)
      : 0;

  // Order dispositions worst-first, then append any unexpected keys.
  const dispEntries: [string, number][] = [
    ...DISP_ORDER.filter((k) => data.by_disposition[k] != null).map(
      (k) => [k, data.by_disposition[k] as number] as [string, number],
    ),
    ...Object.entries(data.by_disposition).filter(
      ([k]) => !DISP_ORDER.includes(k as Disposition),
    ),
  ];
  const dispTotal = dispEntries.reduce((s, [, v]) => s + v, 0);
  const cleanCount = data.by_disposition.CLEAN ?? 0;
  const fraudCount = data.by_disposition.FRAUD ?? 0;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>
        <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
          The state of the book from the latest engine run. Each claim carries a risk{" "}
          <span className="font-medium text-slate-600">band</span> (how much it has to answer
          for), a worst-wins <span className="font-medium text-slate-600">disposition</span>{" "}
          (where it routes), and a settled rand figure — payable = min(billed, reference)
          across the six heads of damage. Read the money as what the payment path will pay,
          not what was billed.
        </p>
      </header>

      {/* Head stats */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Determinations"
          value={num(data.determinations)}
          sub="claims the engine has scored and dispositioned"
        />
        <Stat
          label="Eligible to pay"
          value={num(data.eligible_to_pay)}
          accent="text-emerald-600"
          sub={`cleared the gate; ready for a payment batch · ${eligiblePct}% of determinations`}
        />
        <Stat
          label="Net payable"
          value={rand(data.net_payable_total)}
          sub="Σ payable across all six heads, after gates & apportionment"
        />
        <Stat
          label="Medical payable"
          value={rand(data.medical_payable_total)}
          sub="the medical heads (past + future) within net payable"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Band mix */}
        <Card
          title="Band mix"
          sub="Risk split by score: GREEN [0,25) auto-clears, AMBER [25,50) needs a look, RED [50,∞) is worked first. A book weighted GREEN is healthy; a heavy RED tail is where the review effort goes."
        >
          {bandTotal === 0 ? (
            <div className="text-sm text-slate-400">No determinations yet.</div>
          ) : (
            <div className="space-y-3">
              {BANDS.map(({ key, label, bar, text }) => {
                const v = data.by_band[key];
                const w = bandTotal ? (v / bandTotal) * 100 : 0;
                return (
                  <div key={key}>
                    <div className="mb-1 flex items-center justify-between text-sm">
                      <span className={`font-medium ${text}`}>{label}</span>
                      <span className="tnum text-slate-500">
                        {num(v)}{" "}
                        <span className="text-slate-300">
                          ({Math.round(w)}%)
                        </span>
                      </span>
                    </div>
                    <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className={`h-full rounded-full ${bar}`}
                        style={{ width: `${w}%` }}
                      />
                    </div>
                  </div>
                );
              })}
              <p className="pt-1 text-xs text-slate-400">
                {Math.round((data.by_band.GREEN / bandTotal) * 100)}% GREEN,{" "}
                {Math.round((data.by_band.RED / bandTotal) * 100)}% RED —{" "}
                {data.by_band.RED > data.by_band.GREEN
                  ? "the RED tail outweighs the clean lane; expect heavy review load."
                  : "the clean lane carries the book; the RED tail is the work queue."}
              </p>
            </div>
          )}
        </Card>

        {/* Disposition breakdown */}
        <Card
          title="Disposition breakdown"
          sub="The routing verdict per claim, worst-first (§9): the single most severe reason wins, so a claim is counted once, in its worst lane. FRAUD/MERITS/COMPLIANCE/PREAUTH/SI_GATE need a human; ADJUSTED and CLEAN carry the auto-processed volume."
        >
          {dispTotal === 0 ? (
            <div className="text-sm text-slate-400">No determinations yet.</div>
          ) : (
            <>
              <ul className="divide-y divide-slate-100">
                {dispEntries.map(([k, v]) => {
                  const outcome = DISP_OUTCOME[k as Disposition];
                  return (
                    <li
                      key={k}
                      className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0"
                    >
                      <div className="min-w-0">
                        <DispositionChip disposition={k as Disposition} />
                        {outcome && (
                          <div className="mt-0.5 text-[11px] text-slate-400">
                            {outcome}
                          </div>
                        )}
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className="h-full rounded-full bg-slate-400"
                            style={{
                              width: `${dispTotal ? (v / dispTotal) * 100 : 0}%`,
                            }}
                          />
                        </div>
                        <span className="tnum w-8 text-right text-sm font-medium text-slate-700">
                          {num(v)}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
              <p className="mt-3 border-t border-slate-100 pt-2 text-xs text-slate-400">
                {Math.round((cleanCount / dispTotal) * 100)}% land CLEAN (paid as computed)
                {fraudCount > 0
                  ? `; ${num(fraudCount)} in FRAUD — the review lane that pays for itself.`
                  : "; no FRAUD flagged this run."}
              </p>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
