// Portfolio snapshot from GET /api/dashboard: determinations count, band mix,
// disposition breakdown, eligible-to-pay count, net + medical payable totals.

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

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-slate-900">Dashboard</h1>

      {/* Head stats */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Determinations" value={num(data.determinations)} />
        <Stat
          label="Eligible to pay"
          value={num(data.eligible_to_pay)}
          accent="text-emerald-600"
          sub={`of ${num(data.determinations)} determinations`}
        />
        <Stat
          label="Net payable"
          value={rand(data.net_payable_total)}
          sub="sum of net_payable"
        />
        <Stat
          label="Medical payable"
          value={rand(data.medical_payable_total)}
          sub="sum of medical_payable"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Band mix */}
        <Card title="Band mix">
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
            </div>
          )}
        </Card>

        {/* Disposition breakdown */}
        <Card title="Disposition breakdown">
          {dispTotal === 0 ? (
            <div className="text-sm text-slate-400">No determinations yet.</div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {dispEntries.map(([k, v]) => (
                <li
                  key={k}
                  className="flex items-center justify-between py-2 first:pt-0 last:pb-0"
                >
                  <DispositionChip disposition={k as Disposition} />
                  <div className="flex items-center gap-3">
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
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
