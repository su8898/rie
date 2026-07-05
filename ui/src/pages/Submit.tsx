// Submit — the front door where a claim is scored (domain-logic §3–§9).
//
// Build a claim payload and POST it to the engine. The engine validates the
// documents / gates (§4), prices each line against the reference —
// payable = min(billed, reference), per-discipline for TARIFF, SEP for NAPPI
// (§3) — assembles the six heads of damage (§5), and returns a banded,
// dispositioned determination: deterministic, provenance-stamped, the same
// numbers here as in the payment path. On success we navigate to that new
// determination's detail page (the full result, holds and reasons live there).
//
// Everything the form captures is an assessment input, mirrored live in the
// payload preview so what the engine reads is never hidden. Three prefilled
// example buttons walk the happy paths. Submitting requires role HANDLER /
// MEDICAL_OFFICER / ADMIN; other roles get a 403 we surface inline.

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { Card, ErrorBox } from "../components/ui";
import { rand } from "../format";
import type { ClaimLine, TariffRate } from "../types";

const DEFAULT_DISCIPLINE = "GP";
const FALLBACK_DISCIPLINES = ["GP", "SPECIALIST"];

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
    discipline: DEFAULT_DISCIPLINE,
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
        discipline: "GP",
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
        discipline: "GP",
      },
      {
        kind: "TARIFF",
        code: "0200",
        qty: 1,
        amount: 300,
        service_date: "2026-01-20",
        provider_id: "PRV-002",
        dx: "S72.0",
        discipline: "GP",
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
        discipline: "GP",
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

  // Provider disciplines for the per-line select — fetched once on mount, with
  // a fallback when no reference data is loaded.
  const [disciplines, setDisciplines] = useState<string[]>(FALLBACK_DISCIPLINES);
  useEffect(() => {
    let alive = true;
    api
      .disciplines()
      .then((d) => {
        if (alive && d.length > 0) setDisciplines(d);
      })
      .catch(() => {
        /* no reference loaded — keep the fallback */
      });
    return () => {
      alive = false;
    };
  }, []);

  // Lightweight tariff-rate lookup: cache per tariff code -> { discipline: rate }.
  // Populated lazily (debounced) as codes are entered so we can show the ref rate
  // for each line's selected discipline. Errors are ignored quietly.
  const [tariffRates, setTariffRates] = useState<
    Record<string, Record<string, number>>
  >({});
  const inFlight = useRef<Set<string>>(new Set());

  const fetchTariff = useMemo(() => {
    return (code: string) => {
      const key = code.trim();
      if (!key || key in tariffRates || inFlight.current.has(key)) return;
      inFlight.current.add(key);
      api
        .tariffRates(key)
        .then((rows: TariffRate[]) => {
          const byDisc: Record<string, number> = {};
          for (const r of rows) byDisc[r.discipline] = r.rate;
          setTariffRates((m) => ({ ...m, [key]: byDisc }));
        })
        .catch(() => {
          // Mark as looked-up-but-empty so we don't refetch on every keystroke.
          setTariffRates((m) => ({ ...m, [key]: {} }));
        })
        .finally(() => inFlight.current.delete(key));
    };
  }, [tariffRates]);

  // Debounce tariff lookups for the TARIFF lines' codes.
  useEffect(() => {
    const codes = draft.lines
      .filter((l) => l.kind === "TARIFF" && l.code.trim())
      .map((l) => l.code.trim());
    const t = setTimeout(() => codes.forEach(fetchTariff), 300);
    return () => clearTimeout(t);
  }, [draft.lines, fetchTariff]);

  // The reference rate for a line's code + selected discipline, if known.
  function refRate(line: Line): number | null {
    if (line.kind !== "TARIFF") return null;
    const byDisc = tariffRates[line.code.trim()];
    if (!byDisc) return null;
    const disc = line.discipline || DEFAULT_DISCIPLINE;
    return disc in byDisc ? byDisc[disc] : null;
  }

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
      <div className="flex flex-wrap items-start justify-between gap-3">
        <header>
          <h1 className="text-xl font-semibold text-slate-900">Submit claim</h1>
          <p className="mt-0.5 max-w-3xl text-sm text-slate-500">
            The front door where a claim is scored. The engine validates the
            documents and gates, prices each line —{" "}
            <span className="font-medium text-slate-600">
              payable = min(billed, reference)
            </span>{" "}
            — assembles the six heads of damage, and returns a{" "}
            <span className="font-medium text-slate-600">band</span> (the risk
            read), a worst-wins{" "}
            <span className="font-medium text-slate-600">disposition</span>{" "}
            (where it routes) and a settled rand figure. Deterministic and
            provenance-stamped: same inputs, same determination, stamped with the
            engine version and reference edition that produced it (domain-logic
            §3–§9). The payload below is exactly what it reads.
          </p>
        </header>
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
          You are signed in as <b>{user?.role}</b>. Scoring a claim is an
          adjudication action, reserved for HANDLER, MEDICAL_OFFICER, or ADMIN —
          the engine will reject this submission with 403. You can still build a
          payload and watch the preview.
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card
            title="Claim"
            sub="The claim's identity, timeline and eligibility inputs — each one an assessment parameter, not just metadata. Type selects which merits and document rules apply (RAF1 heads a PERSONAL claim, RAF2 a SUPPLIER one); accident + lodged dates drive the prescription clocks (3y identified / 2y unidentified, §4a); the case number is the OAR — the universal hard gate every claim needs (§4b). merits_accepted is the payment gate: no head pays without it, and fault % apportions every head by (1 − fault) (§4c)."
          >
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
              <p className="mb-1.5 -mt-0.5 text-xs text-slate-400">
                Substantial-compliance checklist (§4b): a missing required form is
                a hard COMPLIANCE gate before pricing runs. RAF1 = PERSONAL claim
                form + medical report, RAF2 = SUPPLIER form, RAF4 = serious-injury
                (unlocks general damages, §5d).
              </p>
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
                <span className="text-xs text-slate-400">
                  — payment gate; unverified holds the payout (PAYEE_UNVERIFIED,
                  §8e)
                </span>
              </label>
            </div>
          </Card>

          <Card
            title="Lines"
            sub="The billed items — what gets priced. Each line is set against the reference: a TARIFF code at its per-discipline RPL rate, a NAPPI item at its Single Exit Price, and payable = min(billed, reference) (§3) — bill above and the line is repriced, not rejected. The dx (ICD-10) must corroborate the accident's injury regions or DX_ACCIDENT_MISMATCH flags for review; a service date before the accident is a hard causation gate (§4d). Priced lines sum into the past-medical head (§5a)."
          >
            <div className="space-y-3">
              {draft.lines.map((l, i) => (
                <LineRow
                  key={i}
                  line={l}
                  disciplines={disciplines}
                  refRate={refRate(l)}
                  onChange={(patch) => setLine(i, patch)}
                  onRemove={() => removeLine(i)}
                />
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

          <div className="space-y-1.5">
            <div className="flex items-center gap-3">
              <button
                onClick={onSubmit}
                disabled={busy}
                className="rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:opacity-50"
              >
                {busy ? "Submitting…" : "Submit claim"}
              </button>
              <span className="text-xs text-slate-400">
                Scores the claim and opens its determination — band, disposition,
                heads, holds and reasons.
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Seeded refs to try: TARIFF 0190, 0055, 0200 · NAPPI 700101 — enter a
              known code and the line shows its reference rate (ref: R…) for the
              selected discipline, so you can see the min(billed, reference)
              repricing before you submit.
            </p>
          </div>
        </div>

        {/* Live payload preview */}
        <div>
          <Card
            title="Payload preview"
            sub="The exact JSON POSTed to the engine, rebuilt live as you edit — nothing the engine reads is hidden. merits_accepted resolves to true / false / null (pending), each line carries its discipline for per-discipline pricing, and an empty discipline defers to the claim default."
          >
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
      // Backend prices tariff lines per discipline; "" = claim default.
      discipline: l.discipline ?? "",
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

// One editable billing line. Includes the provider Discipline select (the
// backend prices TARIFF lines per discipline) and, for TARIFF lines whose code
// is in the reference, an inline "ref: R…" showing the rate for the selected
// discipline so the per-discipline effect is visible as the discipline changes.
function LineRow({
  line,
  disciplines,
  refRate,
  onChange,
  onRemove,
}: {
  line: Line;
  disciplines: string[];
  refRate: number | null;
  onChange: (patch: Partial<Line>) => void;
  onRemove: () => void;
}) {
  const field =
    "w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm outline-none focus:border-slate-500 focus:ring-1 focus:ring-slate-500";
  const micro =
    "mb-0.5 block text-[10px] font-medium uppercase tracking-wide text-slate-400";
  const isTariff = line.kind === "TARIFF";
  // Ensure the line's current discipline is selectable even if not in the list.
  const disc = line.discipline || DEFAULT_DISCIPLINE;
  const options = disciplines.includes(disc)
    ? disciplines
    : [disc, ...disciplines];

  return (
    <div className="grid grid-cols-2 gap-2 rounded-md border border-slate-200 bg-slate-50/60 p-3 md:grid-cols-4 lg:grid-cols-8">
      <div>
        <label className={micro}>kind</label>
        <select
          value={line.kind}
          onChange={(e) => onChange({ kind: e.target.value as Line["kind"] })}
          className={field}
          aria-label="kind"
        >
          <option value="TARIFF">TARIFF</option>
          <option value="NAPPI">NAPPI</option>
        </select>
      </div>
      <div>
        <label className={micro}>code</label>
        <input
          value={line.code}
          onChange={(e) => onChange({ code: e.target.value })}
          className={`${field} font-mono`}
          placeholder="code"
          aria-label="code"
        />
      </div>
      <div>
        <label className={micro}>qty</label>
        <input
          type="number"
          value={line.qty}
          onChange={(e) => onChange({ qty: Number(e.target.value) })}
          className={`${field} tnum`}
          placeholder="qty"
          aria-label="qty"
        />
      </div>
      <div>
        <label className={micro}>amount</label>
        <input
          type="number"
          value={line.amount}
          onChange={(e) => onChange({ amount: Number(e.target.value) })}
          className={`${field} tnum`}
          placeholder="amount"
          aria-label="amount"
        />
        {/* Per-discipline reference rate hint (TARIFF only). */}
        {isTariff && (
          <div className="mt-0.5 h-3 text-[10px] leading-3">
            {refRate != null ? (
              <span className="tnum text-emerald-600" title="reference rate for the selected discipline">
                ref: {rand(refRate)}
              </span>
            ) : line.code.trim() ? (
              <span className="text-slate-300">no reference</span>
            ) : null}
          </div>
        )}
      </div>
      <div>
        <label className={micro}>discipline</label>
        <select
          value={disc}
          onChange={(e) => onChange({ discipline: e.target.value })}
          className={field}
          aria-label="discipline"
          disabled={!isTariff}
          title={isTariff ? undefined : "discipline pricing applies to TARIFF lines"}
        >
          {options.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className={micro}>service date</label>
        <input
          type="date"
          value={line.service_date}
          onChange={(e) => onChange({ service_date: e.target.value })}
          className={field}
          aria-label="service date"
        />
      </div>
      <div>
        <label className={micro}>provider</label>
        <input
          value={line.provider_id}
          onChange={(e) => onChange({ provider_id: e.target.value })}
          className={`${field} font-mono`}
          placeholder="provider"
          aria-label="provider"
        />
      </div>
      <div>
        <label className={micro}>dx</label>
        <div className="flex gap-1">
          <input
            value={line.dx ?? ""}
            onChange={(e) => onChange({ dx: e.target.value })}
            className={field}
            placeholder="dx"
            aria-label="dx"
          />
          <button
            onClick={onRemove}
            className="shrink-0 rounded-md border border-slate-300 px-2 text-slate-400 transition hover:bg-rose-50 hover:text-rose-600"
            title="Remove line"
            aria-label="remove line"
          >
            ×
          </button>
        </div>
      </div>
    </div>
  );
}
