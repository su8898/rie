// Claim detail → Medical reports. The statutory forms a provider has filed for
// this claim over the rails channel: the RAF 1 medical report and the RAF 4
// serious injury assessment. Each is stored exactly as filed; the Fund judges
// completeness against its own form catalogue and names what is still missing.
// A complete RAF 4 on a personal claim opens the serious-injury assessment above.

import { useEffect, useState } from "react";
import { ApiError, api } from "../api";
import type { ClaimDocumentation, MedicalReportSummary } from "../types";
import { Card, CodePill, Empty, ErrorBox, Loading } from "./ui";

const th = "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";
const linkCls = "text-xs font-medium text-slate-700 underline decoration-slate-300 hover:text-slate-900";

function FormChip({ label, onFile, complete }: { label: string; onFile: boolean; complete: boolean }) {
  const cls = complete
    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
    : onFile
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : "border-slate-200 bg-slate-50 text-slate-500";
  const state = complete ? "complete" : onFile ? "on file, incomplete" : "not on file";
  return (
    <span className={`rounded-md border px-2 py-1 text-xs ${cls}`}>
      <span className="font-semibold">{label}</span> · {state}
    </span>
  );
}

export default function MedicalReportsCard({ claimId }: { claimId: string }) {
  const [rows, setRows] = useState<MedicalReportSummary[] | null>(null);
  const [doc, setDoc] = useState<ClaimDocumentation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    Promise.all([api.medicalReports(claimId), api.claimDocumentation(claimId)])
      .then(([r, d]) => {
        if (live) {
          setRows(r);
          setDoc(d);
        }
      })
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "Failed to load medical reports."));
    return () => {
      live = false;
    };
  }, [claimId]);

  return (
    <Card
      title="Medical reports on file"
      sub="Statutory forms the provider filed electronically for this claim, stored as received. Completeness is judged by the Fund against its form catalogue."
    >
      {error ? (
        <ErrorBox message={error} />
      ) : rows === null || doc === null ? (
        <Loading />
      ) : (
        <div>
          <div className="flex flex-wrap gap-2 px-4 py-3">
            {Object.entries(doc.forms).map(([code, f]) => (
              <FormChip key={code} label={code} onFile={f.on_file} complete={f.complete} />
            ))}
          </div>
          {rows.length === 0 ? (
            <Empty label="No medical report has been filed for this claim." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-left">
                  <tr>
                    <th className={th}>Reference</th>
                    <th className={th}>Form</th>
                    <th className={th}>Provider</th>
                    <th className={th}>Received</th>
                    <th className={th}>Status</th>
                    <th className={th} />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.map((r) => (
                    <tr key={r.ref}>
                      <td className="px-3 py-2">
                        <CodePill>{r.ref}</CodePill>
                      </td>
                      <td className="px-3 py-2 text-slate-800">{r.form_title}</td>
                      <td className="px-3 py-2 text-slate-600">{r.provider_id}</td>
                      <td className="px-3 py-2 text-slate-600">
                        {r.received_at ? r.received_at.slice(0, 10) : "—"}
                      </td>
                      <td className="px-3 py-2 text-slate-600">
                        {r.complete ? (
                          "Complete"
                        ) : (
                          <span title={r.missing.join("; ")} className="text-amber-700">
                            Incomplete ({r.missing.length} missing)
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-right">
                        <a
                          className={linkCls}
                          href={api.medicalReportPrintUrl(r.ref)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Print
                        </a>
                        <span className="px-1.5 text-slate-300">·</span>
                        <a
                          className={linkCls}
                          href={api.medicalReportXmlUrl(r.ref)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          XML
                        </a>
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
  );
}
