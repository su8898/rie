// Admin → Coding rules. The tariff's own billing rules, held as reference data
// (one rule per tariff code) and applied by the engine at adjudication:
//
//   • ONCE_PER_ENCOUNTER — the tariff description limits the code to once per
//     encounter; a repeat for the same claimant, provider and day is not paid
//     (UNBUNDLING_CONFLICT), at any amount and on any claim.
//   • TIME_BLOCK / TIME_ANAES / TIME_FIRST_HOUR — a time modifier: the billed
//     quantity is MINUTES and the tariff rate is the block value, so the line is
//     priced by its ladder, not by a flat rate per minute.
//   • PCT_OF_TIME — a share of the anaesthetic time billed with it; with no time
//     line on the claim the modifier does not resolve and goes to review.
//
// The reference loader seeds the once-only codes from the tariff descriptions and
// the standard time modifiers the tariff carries; rules set here are kept on reload.

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { Card, CodePill, Empty, ErrorBox, Loading, Toast } from "../components/ui";
import type { CodeRule, CodeRuleKind } from "../types";

const RULES: { key: CodeRuleKind; label: string; param: string | null; help: string }[] = [
  {
    key: "ONCE_PER_ENCOUNTER",
    label: "Once per encounter",
    param: null,
    help: "A repeat for the same claimant, provider and day is not paid.",
  },
  {
    key: "TIME_BLOCK",
    label: "Time: block per N minutes",
    param: "Block length (minutes)",
    help: "Quantity is minutes. One block per N minutes or part thereof.",
  },
  {
    key: "TIME_ANAES",
    label: "Time: anaesthetic, per 15 minutes",
    param: null,
    help: "Quantity is minutes. One block per 15 minutes or part in the first hour, 1.5 blocks after.",
  },
  {
    key: "TIME_FIRST_HOUR",
    label: "Time: first hour, then per 15 minutes",
    param: null,
    help: "Quantity is minutes. One block for the first hour, then a third per 15 minutes or part.",
  },
  {
    key: "PCT_OF_TIME",
    label: "Percentage of anaesthetic time",
    param: "Share (0 to 1)",
    help: "A share of the anaesthetic time lines billed by the same provider on the same day.",
  },
];
const ruleOf = (k: string) => RULES.find((r) => r.key === k);

const th = "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500";
const inputCls =
  "rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
const primaryBtn =
  "rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-40";
const dangerBtn =
  "rounded-md border border-rose-200 px-2.5 py-1 text-xs font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-40";
const labelCls = "mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400";

function paramText(r: CodeRule): string {
  if (r.rule === "TIME_BLOCK") return `${r.param} min`;
  if (r.rule === "PCT_OF_TIME") return `${Math.round(r.param * 100)}%`;
  return "";
}

export default function CodeRulesTab() {
  const [rows, setRows] = useState<CodeRule[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "error" | "success" } | null>(null);
  const [code, setCode] = useState("");
  const [rule, setRule] = useState<CodeRuleKind>("ONCE_PER_ENCOUNTER");
  const [param, setParam] = useState("");
  const [basis, setBasis] = useState("");

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      setRows(await api.adminCodeRules());
    } catch (e) {
      setLoadError(e instanceof ApiError ? e.message : "Failed to load coding rules.");
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

  const meta = ruleOf(rule);
  const save = () =>
    run(
      "save",
      () =>
        api
          .upsertCodeRule({ code: code.trim(), rule, param: Number(param) || 0, basis: basis.trim() })
          .then(() => {
            setCode("");
            setParam("");
            setBasis("");
          }),
      `Rule saved for code ${code.trim()}.`,
    );

  if (loadError) return <ErrorBox message={loadError} />;
  if (rows === null) return <Loading />;

  return (
    <div className="space-y-4">
      <Card
        title="Add or replace a coding rule"
        sub="One rule per tariff code; saving a code that already has a rule replaces it. The engine applies the rule on the next determination. Time rules assume the billed quantity is minutes."
      >
        <div className="flex flex-wrap items-end gap-3 p-4">
          <div>
            <label className={labelCls}>Tariff code</label>
            <input
              className={`${inputCls} w-28`}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="0011"
            />
          </div>
          <div>
            <label className={labelCls}>Rule</label>
            <select
              className={inputCls}
              value={rule}
              onChange={(e) => setRule(e.target.value as CodeRuleKind)}
            >
              {RULES.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          {meta?.param && (
            <div>
              <label className={labelCls}>{meta.param}</label>
              <input
                className={`${inputCls} w-28`}
                value={param}
                onChange={(e) => setParam(e.target.value)}
                inputMode="decimal"
                placeholder={rule === "TIME_BLOCK" ? "30" : "0.5"}
              />
            </div>
          )}
          <div className="min-w-[14rem] flex-1">
            <label className={labelCls}>Basis (the clause or guideline cited)</label>
            <input
              className={`${inputCls} w-full`}
              value={basis}
              onChange={(e) => setBasis(e.target.value)}
              placeholder="e.g. tariff description: use once only"
            />
          </div>
          <button className={primaryBtn} disabled={!code.trim() || busy !== null} onClick={save}>
            {busy === "save" ? "Saving…" : "Save rule"}
          </button>
        </div>
        {meta && <p className="px-4 pb-4 text-xs text-slate-500">{meta.help}</p>}
      </Card>

      <Card title="Coding rules" sub={`${rows.length} tariff code${rows.length === 1 ? "" : "s"} carry a rule.`}>
        {rows.length === 0 ? (
          <Empty label="No coding rules loaded. Run the reference loader or add one above." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-left">
                <tr>
                  <th className={th}>Code</th>
                  <th className={th}>Rule</th>
                  <th className={th}>Parameter</th>
                  <th className={th}>Basis</th>
                  <th className={th}>Origin</th>
                  <th className={th} />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.code}>
                    <td className="px-3 py-2">
                      <CodePill>{r.code}</CodePill>
                    </td>
                    <td className="px-3 py-2 text-slate-800">{ruleOf(r.rule)?.label ?? r.rule}</td>
                    <td className="px-3 py-2 tabular-nums text-slate-600">{paramText(r)}</td>
                    <td className="px-3 py-2 text-slate-600">{r.basis}</td>
                    <td className="px-3 py-2 text-slate-500">{r.origin}</td>
                    <td className="px-3 py-2 text-right">
                      <button
                        className={dangerBtn}
                        disabled={busy !== null}
                        onClick={() =>
                          run(
                            `del.${r.code}`,
                            () => api.deleteCodeRule(r.code),
                            `Rule removed from code ${r.code}.`,
                          )
                        }
                      >
                        {busy === `del.${r.code}` ? "…" : "Remove"}
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
