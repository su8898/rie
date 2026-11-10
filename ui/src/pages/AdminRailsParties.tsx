// Admin → Channel keys. The register of parties allowed onto the provider channel.
// A party is a provider's own system or a switch acting for many providers. Each
// signs every request with its own ES256 private key; the Fund holds only the
// PUBLIC key registered here, so a signature identifies its signer, and the
// party may act only for the provider ids listed against it ("*" = any, for a
// switch). Suspending a party refuses its signatures at once. The Fund never
// generates or sees a private key: the party makes its key pair with the
// conformance kit (refclient.py keygen) and sends the public half.

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { Card, CodePill, Empty, ErrorBox, Loading, Toast } from "../components/ui";
import type { RailsParty } from "../types";

const th = "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";
const inputCls =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const primaryBtn =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40";
const smallBtn =
  "rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40";
const labelCls = "mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400";

export default function RailsPartiesTab() {
  const [rows, setRows] = useState<RailsParty[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "error" | "success" } | null>(null);
  const [partyId, setPartyId] = useState("");
  const [name, setName] = useState("");
  const [kind, setKind] = useState("PROVIDER");
  const [providers, setProviders] = useState("");
  const [jwk, setJwk] = useState("");

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setRows(await api.railsParties());
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load channel keys.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = (key: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(key);
    fn()
      .then(() => {
        setToast({ message: ok, tone: "success" });
        return load();
      })
      .catch((e) =>
        setToast({ message: e instanceof ApiError ? e.message : "Request failed.", tone: "error" }),
      )
      .finally(() => setBusy(null));
  };

  const register = () =>
    run(
      "register",
      () =>
        api
          .registerRailsParty({
            party_id: partyId.trim(),
            name: name.trim(),
            kind,
            providers: providers
              .split(/[\s,]+/)
              .map((p) => p.trim())
              .filter(Boolean),
            public_jwk: jwk.trim(),
          })
          .then(() => {
            setPartyId("");
            setName("");
            setProviders("");
            setJwk("");
          }),
      `Party ${partyId.trim()} registered.`,
    );

  if (loadError) return <ErrorBox message={loadError} />;
  if (rows === null) return <Loading />;

  return (
    <div className="space-y-4">
      <Card
        title="Register a party"
        sub="Paste the PUBLIC key the party sent you, as a JWK. A private key is refused. A provider system lists the practice numbers it bills under; a switch may list many, or * for any."
      >
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className={labelCls}>Party id (the key id it signs with)</label>
            <input className={`${inputCls} w-full`} value={partyId} onChange={(e) => setPartyId(e.target.value)} placeholder="ACME-PMS" />
          </div>
          <div>
            <label className={labelCls}>Name</label>
            <input className={`${inputCls} w-full`} value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme Practice Systems" />
          </div>
          <div>
            <label className={labelCls}>Kind</label>
            <select className={`${inputCls} w-full`} value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="PROVIDER">Provider system</option>
              <option value="SWITCH">Switch</option>
            </select>
          </div>
          <div>
            <label className={labelCls}>Provider ids (comma or space separated)</label>
            <input className={`${inputCls} w-full`} value={providers} onChange={(e) => setProviders(e.target.value)} placeholder={kind === "SWITCH" ? "* or a list" : "0265691"} />
          </div>
          <div className="sm:col-span-2 lg:col-span-4">
            <label className={labelCls}>Public key (JWK)</label>
            <textarea
              className={`${inputCls} h-24 w-full font-mono text-xs`}
              value={jwk}
              onChange={(e) => setJwk(e.target.value)}
              placeholder={'{"kty": "EC", "crv": "P-256", "x": "…", "y": "…"}'}
            />
          </div>
          <div>
            <button
              className={primaryBtn}
              disabled={!partyId.trim() || !providers.trim() || !jwk.trim() || busy !== null}
              onClick={register}
            >
              {busy === "register" ? "Registering…" : "Register party"}
            </button>
          </div>
        </div>
      </Card>

      <Card title="Registered parties" sub={`${rows.length} part${rows.length === 1 ? "y" : "ies"} may sign onto the provider channel.`}>
        {rows.length === 0 ? (
          <Empty label="No party is registered. Until one is, only the shared development secret can sign." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left">
                <tr>
                  <th className={th}>Party</th>
                  <th className={th}>Kind</th>
                  <th className={th}>May act for</th>
                  <th className={th}>Key fingerprint</th>
                  <th className={th}>Status</th>
                  <th className={th} />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.party_id}>
                    <td className="px-3 py-2">
                      <CodePill>{r.party_id}</CodePill>
                      {r.name && <span className="ml-2 text-slate-600">{r.name}</span>}
                    </td>
                    <td className="px-3 py-2 text-slate-600">{r.kind === "SWITCH" ? "Switch" : "Provider system"}</td>
                    <td className="px-3 py-2 text-slate-600">
                      {r.providers.includes("*")
                        ? "any provider"
                        : r.providers.slice(0, 4).join(", ") + (r.providers.length > 4 ? ` +${r.providers.length - 4}` : "")}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-slate-500">{r.key_thumbprint.slice(0, 16)}…</td>
                    <td className={`px-3 py-2 ${r.status === "ACTIVE" ? "text-emerald-700" : "text-rose-700"}`}>
                      {r.status === "ACTIVE" ? "Active" : "Suspended"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        className={smallBtn}
                        disabled={busy !== null}
                        onClick={() =>
                          run(
                            `status.${r.party_id}`,
                            () => api.setRailsPartyStatus(r.party_id, r.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE"),
                            r.status === "ACTIVE" ? `Party ${r.party_id} suspended.` : `Party ${r.party_id} reactivated.`,
                          )
                        }
                      >
                        {r.status === "ACTIVE" ? "Suspend" : "Reactivate"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {toast && <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />}
    </div>
  );
}
