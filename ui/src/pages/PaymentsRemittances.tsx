// Payments → Remittance advice. When a batch is paid, each provider paid in it gets
// one remittance advice: every adjudicated line with billed / paid / reduced and
// the reason for a reduction. The provider's system fetches and acknowledges it
// over the rails channel; this card is the Fund's own view, with a print page and
// the XML document for each advice.

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { Card, CodePill, Empty, ErrorBox, Loading, SearchInput } from "../components/ui";
import { rand } from "../format";
import type { RemittanceSummary } from "../types";

const th = "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";
const linkCls = "text-xs font-medium text-slate-700 underline decoration-slate-300 hover:text-slate-900";

export default function RemittancesCard({ refreshKey }: { refreshKey: number }) {
  const [rows, setRows] = useState<RemittanceSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [provider, setProvider] = useState("");

  const load = useCallback(async () => {
    setError(null);
    try {
      setRows(await api.remittances(provider.trim() || undefined));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load remittance advice.");
    }
  }, [provider]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <Card
      title="Remittance advice"
      sub="Issued automatically when a batch is paid: one advice per provider, reconciled line by line to the amount paid. Providers fetch and acknowledge theirs over the rails channel."
      right={
        <SearchInput
          value={provider}
          onChange={setProvider}
          placeholder="Provider id…"
          className="w-44"
        />
      }
    >
      {error ? (
        <ErrorBox message={error} />
      ) : rows === null ? (
        <Loading />
      ) : rows.length === 0 ? (
        <Empty label="No remittance advice yet. One is issued for each provider when a batch is paid." />
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left">
              <tr>
                <th className={th}>Reference</th>
                <th className={th}>Provider</th>
                <th className={th}>Batch</th>
                <th className={th}>Service period</th>
                <th className={`${th} text-right`}>Billed</th>
                <th className={`${th} text-right`}>Reduced</th>
                <th className={`${th} text-right`}>Paid</th>
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
                  <td className="px-3 py-2 text-slate-800">{r.provider_id}</td>
                  <td className="px-3 py-2 tabular-nums text-slate-600">#{r.batch_id}</td>
                  <td className="px-3 py-2 text-slate-600">
                    {r.period_from ?? "—"} to {r.period_to ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">
                    {rand(r.total_billed)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-rose-700">
                    {r.total_reduced > 0 ? rand(r.total_reduced) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right font-medium tabular-nums text-slate-900">
                    {rand(r.total_paid)}
                  </td>
                  <td className="px-3 py-2 text-slate-600">
                    {r.status === "ACKNOWLEDGED" ? "Acknowledged" : "Remitted"}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right">
                    <a
                      className={linkCls}
                      href={api.remittancePrintUrl(r.ref)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Print
                    </a>
                    <span className="px-1.5 text-slate-300">·</span>
                    <a
                      className={linkCls}
                      href={api.remittanceXmlUrl(r.ref)}
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
    </Card>
  );
}
