// Admin → Practice register. Who each billing practice is, and whether it may bill
// the Fund — keyed on the practice number. At claim intake the register, not the
// submitter, decides three facts: a SUSPENDED or DEREGISTERED practice is refused
// (the claim is PROVIDER_UNREGISTERED and payment is blocked); a verified row's
// discipline is the one its lines are priced under; and its setting decides whether
// a claim is a hospital account. A practice the register does not know leaves the
// claim as submitted, unless enforcement is switched on for the deployment.
// This is a local register until a live practice-number feed is connected.

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { Card, CodePill, Empty, ErrorBox, Loading, Pagination, SearchInput, Toast } from "../components/ui";
import type { Practice, PracticeList, PracticeSummary } from "../types";

const th = "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";
const inputCls =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const primaryBtn =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40";
const smallBtn =
  "rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40";
const dangerBtn =
  "rounded-md border border-rose-200 px-2.5 py-1 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-40";
const labelCls = "mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400";

const STATUS_LABEL: Record<string, string> = {
  ACTIVE: "Active",
  SUSPENDED: "Suspended",
  DEREGISTERED: "Deregistered",
};
const BLANK = { provider_id: "", practice_name: "", discipline: "", practice_type: "", setting: "", professional_nr: "" };

export default function PracticesTab() {
  const [list, setList] = useState<PracticeList | null>(null);
  const [summary, setSummary] = useState<PracticeSummary | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "error" | "success" } | null>(null);
  const [form, setForm] = useState({ ...BLANK });
  const [csv, setCsv] = useState("");

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const [l, s] = await Promise.all([api.practices(q, status, page), api.practiceSummary()]);
      setList(l);
      setSummary(s);
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load the practice register.");
    }
  }, [q, status, page]);

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

  const set = (k: keyof typeof BLANK) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = () =>
    run(
      "save",
      () => api.upsertPractice({ ...form, provider_id: form.provider_id.trim() }).then(() => setForm({ ...BLANK })),
      `Practice ${form.provider_id.trim()} saved.`,
    );

  const changeStatus = (p: Practice, to: string) => {
    const reason = to === "ACTIVE" ? "" : window.prompt(`Reason to mark practice ${p.provider_id} ${STATUS_LABEL[to].toLowerCase()}:`) ?? "";
    if (to !== "ACTIVE" && !reason.trim()) return;
    run(`status.${p.provider_id}`, () => api.setPracticeStatus(p.provider_id, to, reason), `Practice ${p.provider_id} is now ${STATUS_LABEL[to].toLowerCase()}.`);
  };

  if (loadError) return <ErrorBox message={loadError} />;
  if (list === null || summary === null) return <Loading />;

  return (
    <div className="space-y-4">
      <div className={`rounded-md border px-4 py-3 text-sm ${summary.enforced ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
        {summary.total} practice{summary.total === 1 ? "" : "s"} in the register.{" "}
        {summary.enforced
          ? "Enforcement is on: a practice that is not in the register may not bill."
          : "Enforcement is off: a practice that is not in the register is accepted as submitted. Only suspended and deregistered practices are refused."}
      </div>

      <Card title="Add or update a practice" sub="Saving an existing practice number updates its details. Status is changed from the list below, with a reason.">
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label className={labelCls}>Practice number</label>
            <input className={`${inputCls} w-full`} value={form.provider_id} onChange={set("provider_id")} placeholder="0265691" />
          </div>
          <div>
            <label className={labelCls}>Practice name</label>
            <input className={`${inputCls} w-full`} value={form.practice_name} onChange={set("practice_name")} />
          </div>
          <div>
            <label className={labelCls}>Discipline (as the tariff names it)</label>
            <input className={`${inputCls} w-full`} value={form.discipline} onChange={set("discipline")} placeholder="GP, Physiotherapy, …" />
          </div>
          <div>
            <label className={labelCls}>Practice type</label>
            <select className={`${inputCls} w-full`} value={form.practice_type} onChange={set("practice_type")}>
              <option value="">Not recorded</option>
              <option value="INDIVIDUAL">Individual</option>
              <option value="GROUP">Group</option>
              <option value="INSTITUTION">Institution</option>
              <option value="SUPPLIER">Supplier</option>
            </select>
          </div>
          <div>
            <label className={labelCls}>Setting</label>
            <select className={`${inputCls} w-full`} value={form.setting} onChange={set("setting")}>
              <option value="">Not recorded</option>
              <option value="ROOMS">Rooms</option>
              <option value="HOSPITAL">Hospital</option>
              <option value="ER">Emergency unit</option>
              <option value="MIXED">Mixed</option>
            </select>
          </div>
          <div>
            <label className={labelCls}>Professional council number</label>
            <input className={`${inputCls} w-full`} value={form.professional_nr} onChange={set("professional_nr")} placeholder="MP0123456" />
          </div>
          <div>
            <button className={primaryBtn} disabled={!form.provider_id.trim() || busy !== null} onClick={save}>
              {busy === "save" ? "Saving…" : "Save practice"}
            </button>
          </div>
        </div>
      </Card>

      <Card
        title="Practices"
        sub={`${list.total} match${list.total === 1 ? "" : "es"}.`}
        right={
          <div className="flex items-center gap-2">
            <select className={inputCls} value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
              <option value="">Any status</option>
              <option value="ACTIVE">Active</option>
              <option value="SUSPENDED">Suspended</option>
              <option value="DEREGISTERED">Deregistered</option>
            </select>
            <SearchInput value={q} onChange={(v) => { setQ(v); setPage(1); }} placeholder="Number, name, discipline…" className="w-56" />
          </div>
        }
      >
        {list.items.length === 0 ? (
          <Empty label="No practice matches. Add one above or import a file below." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="bg-slate-50 text-left">
                  <tr>
                    <th className={th}>Practice</th>
                    <th className={th}>Discipline</th>
                    <th className={th}>Setting</th>
                    <th className={th}>Status</th>
                    <th className={th} />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {list.items.map((p) => (
                    <tr key={p.provider_id}>
                      <td className="px-3 py-2">
                        <CodePill>{p.provider_id}</CodePill>
                        {p.practice_name && <span className="ml-2 text-slate-700">{p.practice_name}</span>}
                      </td>
                      <td className="px-3 py-2 text-slate-600">{p.discipline || "—"}</td>
                      <td className="px-3 py-2 text-slate-600">{p.setting ? p.setting.toLowerCase() : "—"}</td>
                      <td className={`px-3 py-2 ${p.status === "ACTIVE" ? "text-emerald-700" : "text-rose-700"}`}>
                        {STATUS_LABEL[p.status]}
                        {p.status_reason && <span className="ml-1 text-xs text-slate-500">({p.status_reason})</span>}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-right">
                        {p.status === "ACTIVE" ? (
                          <>
                            <button className={dangerBtn} disabled={busy !== null} onClick={() => changeStatus(p, "SUSPENDED")}>
                              Suspend
                            </button>{" "}
                            <button className={dangerBtn} disabled={busy !== null} onClick={() => changeStatus(p, "DEREGISTERED")}>
                              Deregister
                            </button>
                          </>
                        ) : (
                          <button className={smallBtn} disabled={busy !== null} onClick={() => changeStatus(p, "ACTIVE")}>
                            Reinstate
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={list.page} pageCount={Math.max(1, Math.ceil(list.total / list.page_size))} onPage={setPage} total={list.total} unit="practices" />
          </>
        )}
      </Card>

      <Card title="Import practices" sub="CSV with a provider_id column and any of practice_name, discipline, practice_type, setting, professional_nr, notes. An import never changes a practice's status.">
        <div className="space-y-2 p-4">
          <textarea
            className={`${inputCls} h-24 w-full font-mono text-xs`}
            value={csv}
            onChange={(e) => setCsv(e.target.value)}
            placeholder={"provider_id,practice_name,discipline,setting\n0265691,Acme Physio,Physiotherapy,ROOMS"}
          />
          <button
            className={primaryBtn}
            disabled={!csv.trim() || busy !== null}
            onClick={() =>
              run(
                "import",
                () =>
                  api.importPractices(csv).then((r) => {
                    if (r.errors.length) throw new ApiError(400, `${r.loaded} loaded; ${r.errors.length} row(s) skipped, first: line ${r.errors[0].line} — ${r.errors[0].error}`, r.errors);
                    setCsv("");
                  }),
                "Practices imported.",
              )
            }
          >
            {busy === "import" ? "Importing…" : "Import"}
          </button>
        </div>
      </Card>

      {toast && <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />}
    </div>
  );
}
