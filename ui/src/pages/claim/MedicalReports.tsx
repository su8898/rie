// Medical reports on a claim. The statutory forms a practice has filed electronically: the RAF 1
// medical report and the RAF 4 serious-injury assessment. Each is stored exactly as filed. The
// Fund judges whether it is complete and names what is missing.

import { Download, Printer } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../../api";
import { shortDate } from "../../ds/labels";
import { Badge, EmptyState, ErrorBlock, LoadingBlock, Panel, Ref } from "../../ds/primitives";
import type { ClaimDocumentation, MedicalReportSummary } from "../../types";

const link = "inline-flex h-8 items-center gap-1.5 rounded-md border border-line-strong bg-white px-2.5 text-[13px] font-medium text-ink-800 hover:bg-ink-50";

export default function MedicalReports({ claimId }: { claimId: string }) {
  const [rows, setRows] = useState<MedicalReportSummary[] | null>(null);
  const [doc, setDoc] = useState<ClaimDocumentation | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([api.medicalReports(claimId), api.claimDocumentation(claimId)])
      .then(([r, d]) => { if (live) { setRows(r); setDoc(d); } })
      .catch((e) => live && setError(e instanceof ApiError ? e.message : "The medical reports could not be loaded."));
    return () => { live = false; };
  }, [claimId]);

  return (
    <Panel title="Medical reports" description="Forms the practice filed electronically, stored as received. A complete RAF 4 on a personal claim opens the serious-injury assessment." flush>
      {error ? <div className="p-4"><ErrorBlock message={error} /></div> : rows === null || doc === null ? <LoadingBlock /> : (
        <>
          <ul className="grid gap-2 border-b border-line px-4 py-3 sm:grid-cols-2">
            {Object.entries(doc.forms).map(([code, f]) => (
              <li key={code} className="flex items-center justify-between gap-2 rounded-md border border-line px-3 py-2">
                <span className="min-w-0 text-sm text-ink-800">{f.title || code}</span>
                {f.complete ? <Badge tone="ok" dot>Complete</Badge> : f.on_file ? <Badge tone="warn" dot>Received, incomplete</Badge> : <Badge dot>Not received</Badge>}
              </li>
            ))}
          </ul>
          {rows.length === 0 ? <EmptyState title="No medical report has been filed" body="Reports arrive from the practice's system over the provider channel." /> : (
            <ul className="divide-y divide-line">
              {rows.map((r) => (
                <li key={r.ref} className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-ink-900">{r.form_title}</div>
                    <div className="text-[13px] text-ink-500"><Ref>{r.ref}</Ref> · from practice <Link to={`/practices/${encodeURIComponent(r.provider_id)}`} className="text-brand-700 hover:underline"><Ref>{r.provider_id}</Ref></Link> · received {shortDate(r.received_at)}</div>
                    {!r.complete && <div className="mt-1 text-[13px] text-warn-fg">Incomplete. Missing: {r.missing.join("; ")}. Ask the practice to file a corrected report.</div>}
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <a className={link} href={api.medicalReportPrintUrl(r.ref)} target="_blank" rel="noreferrer"><Printer size={14} aria-hidden /> Print</a>
                    <a className={link} href={api.medicalReportXmlUrl(r.ref)} target="_blank" rel="noreferrer"><Download size={14} aria-hidden /> XML</a>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Panel>
  );
}
