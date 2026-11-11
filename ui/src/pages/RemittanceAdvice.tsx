// One remittance advice: the Fund's payment record to one practice for one payment run. What was
// billed, what was paid, and the reason for every reduction, claim by claim and line by line.

import { Download, Printer } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { REMITTANCE_STATUS, dateTime, reasonLabel, shortDate } from "../ds/labels";
import { Badge, ErrorBlock, Facts, LoadingBlock, PageHeader, Panel, Ref, Stat, cx } from "../ds/primitives";
import { rand } from "../format";
import type { RemittanceDetail } from "../types";

const linkBase = "inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-sm font-medium transition";
const linkButton = `${linkBase} border-line-strong bg-white text-ink-800 hover:bg-ink-50`;
const linkPrimary = `${linkBase} border-ink-900 bg-ink-900 text-white hover:bg-ink-800`;

export default function RemittanceAdvicePage() {
  const { ref = "" } = useParams();
  const [advice, setAdvice] = useState<RemittanceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setAdvice(await api.remittance(ref));
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? "There is no remittance advice with that reference." : e instanceof ApiError ? e.message : "The remittance advice could not be loaded.");
    }
  }, [ref]);
  useEffect(() => { setAdvice(null); void load(); }, [load]);

  const crumbs = [{ label: "Finance" }, { label: "Payments", to: "/payments" }, { label: "Remittance advice", to: "/payments?tab=advice" }, { label: ref }];
  const title = <Ref className="text-[26px]">{ref}</Ref>;
  if (error) return <div><PageHeader crumbs={crumbs} title={title} /><ErrorBlock message={error} onRetry={load} /></div>;
  if (!advice) return <div><PageHeader crumbs={crumbs} title={title} /><LoadingBlock /></div>;

  const status = REMITTANCE_STATUS[advice.status];
  const th = "px-4 py-2 text-xs font-medium text-ink-500";
  return (
    <div>
      <PageHeader
        crumbs={crumbs} title={title}
        meta={<Badge tone={status?.tone ?? "neutral"} dot>{status?.label ?? advice.status}</Badge>}
        subtitle={<>Payment advice to practice <Ref>{advice.provider_id}</Ref> for payment run {advice.batch_id}.</>}
        actions={
          <>
            <a className={linkButton} href={api.remittanceXmlUrl(advice.ref)} target="_blank" rel="noreferrer"><Download size={15} aria-hidden /> Download XML</a>
            <a className={linkPrimary} href={api.remittancePrintUrl(advice.ref)} target="_blank" rel="noreferrer"><Printer size={15} aria-hidden /> Print</a>
          </>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Billed" value={rand(advice.total_billed)} hint={`${advice.n_claims} claim${advice.n_claims === 1 ? "" : "s"}`} />
        <Stat label="Paid" value={rand(advice.total_paid)} tone="ok" />
        <Stat label="Reduced" value={advice.total_reduced > 0 ? rand(advice.total_reduced) : "None"} tone={advice.total_reduced > 0 ? "bad" : undefined} hint={advice.total_reduced > 0 ? "Each reason is shown on its line" : "Paid as billed"} />
        <Stat label="Issued" value={shortDate(advice.issued_at)} hint={advice.acknowledged_at ? `Acknowledged ${shortDate(advice.acknowledged_at)}` : "Not acknowledged yet"} />
      </div>

      <Panel title="Details" className="mb-4">
        <Facts items={[
          { label: "Practice", value: <Link className="text-brand-700 hover:underline" to={`/practices/${encodeURIComponent(advice.provider_id)}`}><Ref>{advice.provider_id}</Ref></Link> },
          { label: "Payment run", value: <Link className="text-brand-700 hover:underline" to={`/payments/runs/${advice.batch_id}`}>Payment run {advice.batch_id}</Link> },
          { label: "Payment reference", value: <Ref>{advice.payment_ref}</Ref> },
          { label: "Invoice reference", value: <Ref>{advice.invoice_ref}</Ref> },
          { label: "Service period", value: advice.period_from ? `${shortDate(advice.period_from)} to ${shortDate(advice.period_to)}` : "—" },
          { label: "Issued", value: dateTime(advice.issued_at) },
        ]} />
      </Panel>

      <div className="space-y-4">
        {advice.claims.map((c) => (
          <Panel
            key={c.claim_id} flush
            title={<Link to={`/claims/${encodeURIComponent(c.claim_id)}`} className="text-brand-700 hover:underline"><Ref>{c.claim_id}</Ref></Link>}
            description={<>Claimant reference <Ref>{c.patient || "—"}</Ref></>}
            actions={<Badge tone={c.outcome === "REDUCED" ? "warn" : "ok"}>{c.outcome === "REDUCED" ? "Paid with reductions" : "Paid in full"}</Badge>}
          >
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-line bg-ink-50/70 text-left">
                    <th className={th}>Service date</th><th className={th}>Code</th><th className={cx(th, "text-right")}>Billed</th>
                    <th className={cx(th, "text-right")}>Paid</th><th className={cx(th, "text-right")}>Reduced</th><th className={th}>Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {c.lines.map((l, i) => (
                    <tr key={i} className="align-top">
                      <td className="px-4 py-2.5 text-ink-700">{shortDate(l.service_date)}</td>
                      <td className="px-4 py-2.5"><Ref>{l.code}</Ref> <span className="text-xs text-ink-400">{l.kind === "NAPPI" ? "medicine" : "tariff"}</span></td>
                      <td className="tnum px-4 py-2.5 text-right text-ink-600">{rand(l.billed)}</td>
                      <td className="tnum px-4 py-2.5 text-right font-medium text-ink-900">{rand(l.paid)}</td>
                      <td className={cx("tnum px-4 py-2.5 text-right", l.reduced > 0 ? "text-bad-fg" : "text-ink-400")}>{l.reduced > 0 ? `−${rand(l.reduced)}` : "—"}</td>
                      <td className="px-4 py-2.5 text-[13px] text-ink-700">{l.reasons.length ? l.reasons.map(reasonLabel).join("; ") : l.reduced > 0 ? l.reason_text || "Adjusted" : <span className="text-ink-400">Paid as billed</span>}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-line bg-ink-50/40 font-medium">
                    <td className="px-4 py-2.5 text-ink-500" colSpan={2}>Claim total</td>
                    <td className="tnum px-4 py-2.5 text-right">{rand(c.billed)}</td>
                    <td className="tnum px-4 py-2.5 text-right text-ink-900">{rand(c.paid)}</td>
                    <td className={cx("tnum px-4 py-2.5 text-right", c.reduced > 0 ? "text-bad-fg" : "text-ink-400")}>{c.reduced > 0 ? `−${rand(c.reduced)}` : "—"}</td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            </div>
          </Panel>
        ))}
      </div>
    </div>
  );
}
