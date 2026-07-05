// Determination detail. Head figures + band/disposition, holds, and a reasons
// panel that joins each reason code to its catalogue entry (basis, maturity,
// category, mode) from /api/reasons. Shadow signals shown separately (muted).
// The raw claim (accident_date, type, lines) is rendered at the bottom.

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import {
  BandChip,
  Card,
  CodePill,
  DispositionChip,
  ErrorBox,
  Loading,
  MaturityChip,
  ModeChip,
} from "../components/ui";
import { num, pct, rand } from "../format";
import type { ClaimDetail, Reason } from "../types";

export default function ClaimDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<ClaimDetail | null>(null);
  const [reasons, setReasons] = useState<Map<string, Reason>>(new Map());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let alive = true;
    setDetail(null);
    setError(null);
    Promise.all([api.getClaim(id), api.reasons()])
      .then(([d, catalogue]) => {
        if (!alive) return;
        setDetail(d);
        setReasons(new Map(catalogue.map((r) => [r.code, r])));
      })
      .catch((e) =>
        alive && setError(e instanceof ApiError ? e.message : "Failed to load"),
      );
    return () => {
      alive = false;
    };
  }, [id]);

  if (error) return <ErrorBox message={error} />;
  if (!detail) return <Loading label="Loading determination…" />;

  const d = detail.determination;
  const claim = detail.claim;
  const raw = claim?.raw;
  const lines = raw?.lines ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <Link
          to="/claims"
          className="text-sm text-slate-400 transition hover:text-slate-700"
        >
          ← Claims
        </Link>
        <h1 className="font-mono text-xl font-semibold text-slate-900">
          {d.claim_id}
        </h1>
        <BandChip band={d.band} />
        <DispositionChip disposition={d.disposition} />
        {d.validated && (
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
            validated
          </span>
        )}
      </div>

      {/* Head figures */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <Figure label="Score" value={String(d.score)} />
        <Figure label="Convergence" value={`${Math.round(pct(d.convergence))}`} />
        <Figure label="Medical payable" value={rand(d.medical_payable)} />
        <Figure label="Net payable" value={rand(d.net_payable)} accent />
        <Figure
          label="Eligible to pay"
          value={d.eligible_to_pay ? "Yes" : "No"}
          accent={d.eligible_to_pay}
        />
        <Figure label="Accident action" value={d.accident_action} mono />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Reasons (joined to catalogue) */}
        <div className="lg:col-span-2">
          <Card title="Reasons">
            {d.reasons.length === 0 ? (
              <div className="text-sm text-slate-400">
                No reasons — clean determination.
              </div>
            ) : (
              <ul className="space-y-2">
                {d.reasons.map((code) => {
                  const meta = reasons.get(code);
                  return (
                    <li
                      key={code}
                      className="rounded-md border border-slate-100 bg-slate-50/60 p-3"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <CodePill>{code}</CodePill>
                        {meta && (
                          <>
                            <span className="text-xs font-medium text-slate-500">
                              {meta.category}
                            </span>
                            <MaturityChip maturity={meta.maturity} />
                            <ModeChip mode={meta.mode} />
                            {meta.hard && (
                              <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[11px] font-medium text-rose-700">
                                hard gate
                              </span>
                            )}
                            {meta.points > 0 && (
                              <span className="tnum text-[11px] text-slate-400">
                                +{meta.points} pts
                              </span>
                            )}
                          </>
                        )}
                      </div>
                      {meta?.basis && (
                        <div className="mt-1.5 text-xs leading-relaxed text-slate-500">
                          {meta.basis}
                        </div>
                      )}
                      {!meta && (
                        <div className="mt-1.5 text-xs italic text-slate-400">
                          Not in reason catalogue.
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          {/* Shadow signals — muted */}
          <div className="mt-6">
            <Card title="Shadow signals">
              {d.shadow_signals.length === 0 ? (
                <div className="text-sm text-slate-400">
                  No shadow signals.
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {d.shadow_signals.map((code) => {
                    const meta = reasons.get(code);
                    return (
                      <span
                        key={code}
                        title={meta?.basis || undefined}
                        className="inline-flex items-center gap-1.5 rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-400"
                      >
                        <span className="font-mono">{code}</span>
                        {meta && (
                          <span className="text-slate-300">
                            {meta.category}
                          </span>
                        )}
                      </span>
                    );
                  })}
                </div>
              )}
            </Card>
          </div>
        </div>

        {/* Side column: holds + provenance */}
        <div className="space-y-6">
          <Card title="Holds">
            {d.holds.length === 0 ? (
              <div className="text-sm text-slate-400">No holds.</div>
            ) : (
              <ul className="space-y-1.5">
                {d.holds.map((h, i) => (
                  <li
                    key={i}
                    className="rounded border border-amber-200 bg-amber-50 px-2.5 py-1.5 font-mono text-xs text-amber-800"
                  >
                    {h}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Provenance">
            <dl className="space-y-1.5 text-xs">
              <Row k="Accident" v={d.accident_id} mono />
              <Row k="Engine" v={d.engine_version} mono />
              <Row k="Ruleset" v={d.ruleset_effective} mono />
              <Row k="Reference" v={d.reference_edition} mono />
              {d.created_at && (
                <Row k="Determined" v={new Date(d.created_at).toLocaleString()} />
              )}
            </dl>
          </Card>
        </div>
      </div>

      {/* Raw claim */}
      <Card title="Claim">
        {!claim ? (
          <div className="text-sm text-slate-400">
            Claim record unavailable.
          </div>
        ) : (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-4">
              <Row k="Type" v={claim.claim_type} mono />
              <Row k="Party" v={claim.party_token} mono />
              <Row k="Accident date" v={claim.accident_date} />
              <Row k="Lodged on" v={claim.lodged_on} />
              {raw?.case_number_raw && (
                <Row k="Case number" v={raw.case_number_raw} mono />
              )}
              {raw?.fault_pct != null && (
                <Row k="Fault %" v={`${raw.fault_pct}`} />
              )}
              {raw?.merits_accepted !== undefined && (
                <Row
                  k="Merits"
                  v={
                    raw.merits_accepted === null
                      ? "pending"
                      : raw.merits_accepted
                        ? "accepted"
                        : "rejected"
                  }
                />
              )}
              {raw?.payee_verified !== undefined && (
                <Row k="Payee verified" v={raw.payee_verified ? "yes" : "no"} />
              )}
            </dl>

            {lines.length > 0 && (
              <div className="overflow-x-auto rounded-md border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200 text-sm">
                  <thead className="bg-slate-50">
                    <tr className="text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                      <th className="px-3 py-2">Kind</th>
                      <th className="px-3 py-2">Code</th>
                      <th className="px-3 py-2 text-right">Qty</th>
                      <th className="px-3 py-2 text-right">Amount</th>
                      <th className="px-3 py-2">Service date</th>
                      <th className="px-3 py-2">Provider</th>
                      <th className="px-3 py-2">Dx</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {lines.map((l, i) => (
                      <tr key={i}>
                        <td className="px-3 py-2 text-slate-600">{l.kind}</td>
                        <td className="px-3 py-2 font-mono text-slate-800">
                          {l.code}
                        </td>
                        <td className="tnum px-3 py-2 text-right text-slate-600">
                          {num(l.qty)}
                        </td>
                        <td className="tnum px-3 py-2 text-right text-slate-800">
                          {rand(l.amount)}
                        </td>
                        <td className="px-3 py-2 text-slate-600">
                          {l.service_date}
                        </td>
                        <td className="px-3 py-2 font-mono text-xs text-slate-500">
                          {l.provider_id}
                        </td>
                        <td className="px-3 py-2 text-slate-500">
                          {l.dx || "—"}
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
  );
}

function Figure({
  label,
  value,
  accent = false,
  mono = false,
}: {
  label: string;
  value: string;
  accent?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div
        className={`tnum mt-0.5 text-lg font-semibold ${
          accent ? "text-emerald-600" : "text-slate-900"
        } ${mono ? "font-mono text-sm" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}

function Row({ k, v, mono = false }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-400">{k}</dt>
      <dd className={`text-right text-slate-800 ${mono ? "font-mono" : ""}`}>
        {v}
      </dd>
    </div>
  );
}
