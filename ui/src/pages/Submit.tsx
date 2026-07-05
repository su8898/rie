// Build and POST a claim payload. On success, navigate to the new
// determination's detail page. Three prefilled example buttons make the
// happy paths easy to demo. Requires role HANDLER / MEDICAL_OFFICER / ADMIN;
// other roles get a 403 which we surface inline.

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { Card, ErrorBox } from "../components/ui";
import type { ClaimLine } from "../types";

type Line = ClaimLine;

interface Draft {
  claim_id: string;
  claim_type: "SUPPLIER" | "PERSONAL" | "UNDERTAKING_INVOICE";
  party_token: string;
  accident_date: string;
  lodged_on: string;
  case_number_raw: string;
  today: string;
  payee_verified: boolean;
  merits_accepted: "true" | "false" | "null";
  fault_pct: number;
  documents: Record<string, boolean>;
  lines: Line[];
}

const DOC_KEYS = ["RAF1", "RAF2", "RAF4", "affidavit", "invoice"];

const TODAY = "2026-07-05";

function blankLine(): Line {
  return {
    kind: "TARIFF",
    code: "0190",
    qty: 1,
    amount: 500,
    service_date: "2026-02-10",
    provider_id: "PRV-001",
    dx: "",
  };
}

function uid(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 7).toUpperCase()}`;
}

// ── Example presets ──────────────────────────────────────────────────────────
function exampleClean(): Draft {
  return {
    claim_id: uid("CLM"),
    claim_type: "SUPPLIER",
    party_token: "PARTY-100",
    accident_date: "2026-01-15",
    lodged_on: "2026-02-01",
    case_number_raw: "CAS 100/02/2026",
    today: TODAY,
    payee_verified: true,
    merits_accepted: "true",
    fault_pct: 0,
    documents: { RAF1: true, RAF2: true, invoice: true },
    lines: [
      {
        kind: "TARIFF",
        code: "0190",
        qty: 1,
        amount: 500,
        service_date: "2026-01-20",
        provider_id: "PRV-001",
        dx: "S72.0",
      },
    ],
  };
}

function exampleBilledOver(): Draft {
  // 0190 GP benchmark is 500 — bill 1200 to trip the over-billing signal.
  return {
    claim_id: uid("CLM"),
    claim_type: "SUPPLIER",
    party_token: "PARTY-200",
    accident_date: "2026-01-15",
    lodged_on: "2026-02-01",
    case_number_raw: "CAS 200/02/2026",
    today: TODAY,
    payee_verified: true,
    merits_accepted: "true",
    fault_pct: 0,
    documents: { RAF1: true, RAF2: true, invoice: true },
    lines: [
      {
        kind: "TARIFF",
        code: "0190",
        qty: 1,
        amount: 1200,
        service_date: "2026-01-20",
        provider_id: "PRV-002",
        dx: "S72.0",
      },
      {
        kind: "TARIFF",
        code: "0200",
        qty: 1,
        amount: 300,
        service_date: "2026-01-20",
        provider_id: "PRV-002",
        dx: "S72.0",
      },
    ],
  };
}

function examplePersonalMerits(): Draft {
  // Personal claim with merits still pending -> held for merits.
  return {
    claim_id: uid("CLM"),
    claim_type: "PERSONAL",
    party_token: "PARTY-300",
    accident_date: "2026-01-15",
    lodged_on: "2026-02-01",
    case_number_raw: "CAS 300/02/2026",
    today: TODAY,
    payee_verified: true,
    merits_accepted: "null",
    fault_pct: 20,
    documents: { RAF1: true, RAF4: true },
    lines: [
      {
        kind: "TARIFF",
        code: "0190",
        qty: 1,
        amount: 700,
        service_date: "2026-01-20",
        provider_id: "PRV-003",
        dx: "S82.1",
      },
    ],
  };
}

export default function SubmitPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [draft, setDraft] = useState<Draft>(exampleClean);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canSubmit =
    user?.role === "ADMIN" ||
    user?.role === "HANDLER" ||
    user?.role === "MEDICAL_OFFICER";

  const payload = useMemo(() => buildPayload(draft), [draft]);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function setLine(i: number, patch: Partial<Line>) {
    setDraft((d) => ({
      ...d,
      lines: d.lines.map((l, idx) => (idx === i ? { ...l, ...patch } : l)),
    }));
  }

  function addLine() {
    setDraft((d) => ({ ...d, lines: [...d.lines, blankLine()] }));
  }

  function removeLine(i: number) {
    setDraft((d) => ({ ...d, lines: d.lines.filter((_, idx) => idx !== i) }));
  }

  async function onSubmit() {
    setError(null);
    setBusy(true);
    try {
      const det = await api.submitClaim(payload);
      navigate(`/claims/${encodeURIComponent(det.claim_id)}`);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(
          e.status === 403
            ? `Your role (${user?.role}) may not submit claims. Use handler, medical, or admin.`
            : e.message,
        );
      } else {
        setError("Submit failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  const inputCls =
    "w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
  const labelCls = "mb-1 block text-xs font-medium text-slate-600";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900">Submit claim</h1>
        <div className="flex flex-wrap gap-2">
          <ExampleBtn label="Clean supplier" onClick={() => setDraft(exampleClean())} />
          <ExampleBtn label="Billed-over" onClick={() => setDraft(exampleBilledOver())} />
          <ExampleBtn
            label="Personal · merits pending"
            onClick={() => setDraft(examplePersonalMerits())}
          />
        </div>
      </div>

      {!canSubmit && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          You are signed in as <b>{user?.role}</b>. Submitting requires HANDLER,
          MEDICAL_OFFICER, or ADMIN — the request will be rejected with 403.
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Claim">
            <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
              <div>
                <label className={labelCls}>Claim ID</label>
                <input
                  value={draft.claim_id}
                  onChange={(e) => set("claim_id", e.target.value)}
                  className={`${inputCls} font-mono`}
                />
              </div>
              <div>
                <label className={labelCls}>Type</label>
                <select
                  value={draft.claim_type}
                  onChange={(e) =>
                    set("claim_type", e.target.value as Draft["claim_type"])
                  }
                  className={inputCls}
                >
                  <option value="SUPPLIER">SUPPLIER</option>
                  <option value="PERSONAL">PERSONAL</option>
                  <option value="UNDERTAKING_INVOICE">UNDERTAKING_INVOICE</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Party token</label>
                <input
                  value={draft.party_token}
                  onChange={(e) => set("party_token", e.target.value)}
                  className={`${inputCls} font-mono`}
                />
              </div>
              <div>
                <label className={labelCls}>Accident date</label>
                <input
                  type="date"
                  value={draft.accident_date}
                  onChange={(e) => set("accident_date", e.target.value)}
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>Lodged on</label>
                <input
                  type="date"
                  value={draft.lodged_on}
                  onChange={(e) => set("lodged_on", e.target.value)}
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>Today (assessment)</label>
                <input
                  type="date"
                  value={draft.today}
                  onChange={(e) => set("today", e.target.value)}
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>Case number</label>
                <input
                  value={draft.case_number_raw}
                  onChange={(e) => set("case_number_raw", e.target.value)}
                  className={`${inputCls} font-mono`}
                  placeholder="CAS 100/02/2026"
                />
              </div>
              <div>
                <label className={labelCls}>Merits accepted</label>
                <select
                  value={draft.merits_accepted}
                  onChange={(e) =>
                    set(
                      "merits_accepted",
                      e.target.value as Draft["merits_accepted"],
                    )
                  }
                  className={inputCls}
                >
                  <option value="true">accepted (true)</option>
                  <option value="false">rejected (false)</option>
                  <option value="null">pending (null)</option>
                </select>
              </div>
              <div>
                <label className={labelCls}>Fault %</label>
                <input
                  type="number"
                  value={draft.fault_pct}
                  onChange={(e) => set("fault_pct", Number(e.target.value))}
                  className={`${inputCls} tnum`}
                  min={0}
                  max={100}
                />
              </div>
            </div>

            <div className="mt-4">
              <label className={labelCls}>Documents</label>
              <div className="flex flex-wrap gap-3">
                {DOC_KEYS.map((k) => (
                  <label
                    key={k}
                    className="flex items-center gap-1.5 text-sm text-slate-600"
                  >
                    <input
                      type="checkbox"
                      checked={!!draft.documents[k]}
                      onChange={(e) =>
                        set("documents", {
                          ...draft.documents,
                          [k]: e.target.checked,
                        })
                      }
                      className="h-4 w-4 rounded border-slate-300"
                    />
                    {k}
                  </label>
                ))}
              </div>
              <label className="mt-3 flex items-center gap-1.5 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={draft.payee_verified}
                  onChange={(e) => set("payee_verified", e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300"
                />
                payee_verified
              </label>
            </div>
          </Card>

          <Card title="Lines">
            <div className="space-y-3">
              {draft.lines.map((l, i) => (
                <div
                  key={i}
                  className="grid grid-cols-2 gap-2 rounded-md border border-slate-200 bg-slate-50/60 p-3 md:grid-cols-7"
                >
                  <select
                    value={l.kind}
                    onChange={(e) =>
                      setLine(i, { kind: e.target.value as Line["kind"] })
                    }
                    className={inputCls}
                    aria-label="kind"
                  >
                    <option value="TARIFF">TARIFF</option>
                    <option value="NAPPI">NAPPI</option>
                  </select>
                  <input
                    value={l.code}
                    onChange={(e) => setLine(i, { code: e.target.value })}
                    className={`${inputCls} font-mono`}
                    placeholder="code"
                    aria-label="code"
                  />
                  <input
                    type="number"
                    value={l.qty}
                    onChange={(e) => setLine(i, { qty: Number(e.target.value) })}
                    className={`${inputCls} tnum`}
                    placeholder="qty"
                    aria-label="qty"
                  />
                  <input
                    type="number"
                    value={l.amount}
                    onChange={(e) =>
                      setLine(i, { amount: Number(e.target.value) })
                    }
                    className={`${inputCls} tnum`}
                    placeholder="amount"
                    aria-label="amount"
                  />
                  <input
                    type="date"
                    value={l.service_date}
                    onChange={(e) =>
                      setLine(i, { service_date: e.target.value })
                    }
                    className={inputCls}
                    aria-label="service date"
                  />
                  <input
                    value={l.provider_id}
                    onChange={(e) =>
                      setLine(i, { provider_id: e.target.value })
                    }
                    className={`${inputCls} font-mono`}
                    placeholder="provider"
                    aria-label="provider"
                  />
                  <div className="flex gap-1">
                    <input
                      value={l.dx ?? ""}
                      onChange={(e) => setLine(i, { dx: e.target.value })}
                      className={inputCls}
                      placeholder="dx"
                      aria-label="dx"
                    />
                    <button
                      onClick={() => removeLine(i)}
                      className="rounded-md border border-slate-300 px-2 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
                      title="Remove line"
                      aria-label="remove line"
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))}
              <button
                onClick={addLine}
                className="rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-sm text-slate-500 transition hover:bg-slate-50"
              >
                + Add line
              </button>
            </div>
          </Card>

          {error && <ErrorBox message={error} />}

          <div className="flex items-center gap-3">
            <button
              onClick={onSubmit}
              disabled={busy}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50"
            >
              {busy ? "Submitting…" : "Submit claim"}
            </button>
            <span className="text-xs text-slate-400">
              Seeded refs to try: TARIFF 0190, 0055, 0200 · NAPPI 700101
            </span>
          </div>
        </div>

        {/* Live payload preview */}
        <div>
          <Card title="Payload preview">
            <pre className="max-h-[36rem] overflow-auto rounded bg-slate-900 p-3 text-[11px] leading-relaxed text-slate-100">
              {JSON.stringify(payload, null, 2)}
            </pre>
          </Card>
        </div>
      </div>
    </div>
  );
}

function buildPayload(d: Draft) {
  return {
    claim_id: d.claim_id,
    claim_type: d.claim_type,
    party_token: d.party_token,
    accident_date: d.accident_date,
    lodged_on: d.lodged_on,
    case_number_raw: d.case_number_raw || undefined,
    today: d.today || undefined,
    documents: d.documents,
    payee_verified: d.payee_verified,
    merits_accepted:
      d.merits_accepted === "null"
        ? null
        : d.merits_accepted === "true",
    fault_pct: d.fault_pct,
    lines: d.lines.map((l) => ({
      kind: l.kind,
      code: l.code,
      qty: Number(l.qty),
      amount: Number(l.amount),
      service_date: l.service_date,
      provider_id: l.provider_id,
      dx: l.dx || "",
    })),
  };
}

function ExampleBtn({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
    >
      {label}
    </button>
  );
}
