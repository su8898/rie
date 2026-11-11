// New claim. A guided form in four parts: the claim, liability, supporting documents and the
// medical account. The document checklist follows the claim type, so what is ticked here is
// exactly what the engine checks. Everything is validated before it is sent, and the Fund's
// answer opens as the claim record.

import { Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { CLAIM_TYPES, DOCUMENTS, REQUIRED_DOCUMENTS } from "../ds/labels";
import { useToast } from "../ds/overlays";
import { Button, Checkbox, ErrorBlock, Field, Input, PageHeader, Panel, Select } from "../ds/primitives";
import { rand } from "../format";

interface Line { key: number; kind: "TARIFF" | "NAPPI"; code: string; qty: string; amount: string; service_date: string; provider_id: string; discipline: string; dx: string }

const today = () => new Date().toISOString().slice(0, 10);
const newRef = () => `CLM-${Math.random().toString(36).slice(2, 7).toUpperCase()}`;
let nextKey = 1;
const blankLine = (from?: Line): Line => ({
  key: nextKey++, kind: "TARIFF", code: "", qty: "1", amount: "", service_date: from?.service_date ?? "",
  provider_id: from?.provider_id ?? "", discipline: from?.discipline ?? "", dx: from?.dx ?? "",
});

function serverErrors(e: unknown): string[] {
  if (!(e instanceof ApiError)) return ["The claim could not be submitted."];
  const detail = e.detail as { errors?: unknown[] } | string | null;
  if (detail && typeof detail === "object" && Array.isArray(detail.errors)) {
    return detail.errors.map((x) => {
      if (typeof x === "string") return x;
      const o = x as { loc?: unknown[]; msg?: string };
      return `${(o.loc ?? []).join(" › ")}: ${o.msg ?? JSON.stringify(x)}`;
    });
  }
  return [e.status === 409 ? "A claim with this reference already exists. Use a different reference." : e.message];
}

export default function ClaimNewPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [claimId, setClaimId] = useState(newRef);
  const [claimType, setClaimType] = useState("SUPPLIER");
  const [claimant, setClaimant] = useState("");
  const [accidentDate, setAccidentDate] = useState("");
  const [lodgedOn, setLodgedOn] = useState(today);
  const [caseNumber, setCaseNumber] = useState("");
  const [merits, setMerits] = useState("null");
  const [fault, setFault] = useState("0");
  const [documents, setDocuments] = useState<Record<string, boolean>>({});
  const [payeeVerified, setPayeeVerified] = useState(false);
  const [facility, setFacility] = useState(false);
  const [lines, setLines] = useState<Line[]>(() => [blankLine()]);
  const [disciplines, setDisciplines] = useState<string[]>([]);
  const [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  useEffect(() => { api.disciplines().then(setDisciplines).catch(() => setDisciplines([])); }, []);

  const required = REQUIRED_DOCUMENTS[claimType] ?? [];
  const personal = claimType === "PERSONAL";
  const isId = /^\d{13}$/.test(claimant.trim());
  const billed = useMemo(() => lines.reduce((s, l) => s + (Number(l.amount) || 0), 0), [lines]);
  const missingDocs = required.filter((k) => !documents[k]);

  // What stops the form being sent, field by field.
  const problems: Record<string, string> = {};
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(claimId)) problems.claimId = "Use letters, digits, dots, dashes or underscores.";
  if (!claimant.trim()) problems.claimant = "Enter the claimant's identity number or reference.";
  if (!accidentDate) problems.accidentDate = "Enter the accident date.";
  if (!lodgedOn) problems.lodgedOn = "Enter the lodgement date.";
  else if (accidentDate && lodgedOn < accidentDate) problems.lodgedOn = "A claim cannot be lodged before the accident.";
  if (personal && (Number(fault) < 0 || Number(fault) > 100 || fault === "")) problems.fault = "Enter a percentage from 0 to 100.";
  const lineProblem = (l: Line): string | null =>
    !l.code.trim() ? "Enter a code." : !(Number(l.qty) > 0) ? "Quantity must be more than zero."
    : l.amount === "" || Number(l.amount) < 0 ? "Enter the amount billed." : !l.service_date ? "Enter the service date."
    : accidentDate && l.service_date < accidentDate ? "The service is dated before the accident." : !l.provider_id.trim() ? "Enter the practice number." : null;
  const badLines = lines.filter((l) => lineProblem(l) !== null).length;
  const valid = Object.keys(problems).length === 0 && badLines === 0 && lines.length > 0;
  const show = (k: string) => (attempted ? problems[k] ?? null : null);

  const setLine = (key: number, patch: Partial<Line>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  async function submit() {
    setAttempted(true);
    setErrors([]);
    if (!valid) {
      toast.error("Some fields need attention before this claim can be submitted.");
      return;
    }
    const payload: Record<string, unknown> = {
      claim_id: claimId.trim(), claim_type: claimType, accident_date: accidentDate, lodged_on: lodgedOn,
      documents: Object.fromEntries(required.map((k) => [k, Boolean(documents[k])])),
      payee_verified: payeeVerified, facility,
      lines: lines.map((l) => ({
        kind: l.kind, code: l.code.trim(), qty: Number(l.qty), amount: Number(l.amount), service_date: l.service_date,
        provider_id: l.provider_id.trim(), dx: l.dx.trim(), ...(l.discipline ? { discipline: l.discipline } : {}),
      })),
      ...(isId ? { national_id: claimant.trim() } : { party_token: claimant.trim() }),
      ...(caseNumber.trim() ? { case_number_raw: caseNumber.trim() } : {}),
      ...(personal ? { merits_accepted: merits === "null" ? null : merits === "true", fault_pct: Number(fault) } : {}),
    };
    setBusy(true);
    try {
      const det = await api.submitClaim(payload);
      toast.success(`Claim ${det.claim_id} submitted and determined.`);
      navigate(`/claims/${encodeURIComponent(det.claim_id)}`);
    } catch (e) {
      setErrors(serverErrors(e));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Work" }, { label: "Claims", to: "/claims" }, { label: "New claim" }]}
        title="New claim"
        subtitle="Capture a claim or supplier invoice. It is priced and assessed the moment it is submitted."
        actions={<><Button onClick={() => navigate("/claims")}>Cancel</Button><Button variant="primary" loading={busy} onClick={submit}>Submit claim</Button></>}
      />

      {errors.length > 0 && (
        <div className="mb-4 space-y-2">{errors.map((m) => <ErrorBlock key={m} message={m} />)}</div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Panel title="1. Claim" description="Who is claiming, and for which accident.">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Claim reference" required error={show("claimId")}>
                <Input value={claimId} onChange={(e) => setClaimId(e.target.value)} invalid={Boolean(show("claimId"))} className="font-mono" />
              </Field>
              <Field label="Claim type" required>
                <Select value={claimType} onChange={(e) => setClaimType(e.target.value)}>
                  {["SUPPLIER", "PERSONAL"].map((k) => <option key={k} value={k}>{CLAIM_TYPES[k]}</option>)}
                </Select>
              </Field>
              <Field label="Claimant" required error={show("claimant")} hint={isId ? "Identity number: it is replaced by an anonymous reference and never stored." : "A 13-digit identity number, or an existing claimant reference."} className="sm:col-span-2">
                <Input value={claimant} onChange={(e) => setClaimant(e.target.value)} invalid={Boolean(show("claimant"))} placeholder="Identity number or claimant reference" />
              </Field>
              <Field label="Accident date" required error={show("accidentDate")}>
                <Input type="date" value={accidentDate} max={today()} onChange={(e) => setAccidentDate(e.target.value)} invalid={Boolean(show("accidentDate"))} />
              </Field>
              <Field label="Lodged on" required error={show("lodgedOn")}>
                <Input type="date" value={lodgedOn} onChange={(e) => setLodgedOn(e.target.value)} invalid={Boolean(show("lodgedOn"))} />
              </Field>
              <Field label="Police case number" hint="Links the claim to its accident record." className="sm:col-span-2">
                <Input value={caseNumber} onChange={(e) => setCaseNumber(e.target.value)} placeholder="CAS 123/02/2026" />
              </Field>
            </div>
          </Panel>

          {personal && (
            <Panel title="2. Liability" description="A personal claim is paid only once merits are accepted.">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Merits decision">
                  <Select value={merits} onChange={(e) => setMerits(e.target.value)}>
                    <option value="null">Not decided yet</option><option value="true">Accepted</option><option value="false">Rejected</option>
                  </Select>
                </Field>
                <Field label="Claimant's share of fault (%)" error={show("fault")} hint="Every head of damage is reduced by this share.">
                  <Input type="number" min={0} max={100} value={fault} onChange={(e) => setFault(e.target.value)} invalid={Boolean(show("fault"))} />
                </Field>
              </div>
            </Panel>
          )}

          <Panel title={`${personal ? 3 : 2}. Supporting documents`} description={`Tick each document received. A ${CLAIM_TYPES[claimType].toLowerCase()} needs all ${required.length} before it can be paid.`}>
            <div className="grid gap-2 sm:grid-cols-2">
              {required.map((k) => (
                <Checkbox key={k} label={DOCUMENTS[k] ?? k} checked={Boolean(documents[k])} onChange={(e) => setDocuments((d) => ({ ...d, [k]: e.target.checked }))} />
              ))}
            </div>
            <div className="mt-3 grid gap-2 border-t border-line pt-3 sm:grid-cols-2">
              <Checkbox label="Payee verified" hint="Banking details confirmed with the bank." checked={payeeVerified} onChange={(e) => setPayeeVerified(e.target.checked)} />
              <Checkbox label="Hospital account" hint="An inpatient or emergency-unit account." checked={facility} onChange={(e) => setFacility(e.target.checked)} />
            </div>
          </Panel>

          <Panel
            title={`${personal ? 4 : 3}. Medical account`} description="One row per billed line. Time-based codes take the minutes as the quantity."
            actions={<Button size="sm" icon={Plus} onClick={() => setLines((ls) => [...ls, blankLine(ls[ls.length - 1])])}>Add line</Button>} flush
          >
            <div className="divide-y divide-line">
              {lines.map((l, i) => {
                const problem = attempted ? lineProblem(l) : null;
                return (
                  <div key={l.key} className="px-4 py-3">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-xs font-medium text-ink-500">Line {i + 1}</span>
                      <button onClick={() => setLines((ls) => ls.filter((x) => x.key !== l.key))} disabled={lines.length === 1} className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-ink-500 hover:bg-bad-bg hover:text-bad-fg disabled:opacity-30" aria-label={`Remove line ${i + 1}`}>
                        <Trash2 size={13} /> Remove
                      </button>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-4">
                      <Select aria-label="Line type" value={l.kind} onChange={(e) => setLine(l.key, { kind: e.target.value as Line["kind"] })}>
                        <option value="TARIFF">Tariff code</option><option value="NAPPI">Medicine or material</option>
                      </Select>
                      <Input aria-label="Code" placeholder="Code" className="font-mono" value={l.code} onChange={(e) => setLine(l.key, { code: e.target.value })} />
                      <Input aria-label="Quantity" placeholder="Quantity" type="number" min={0} step="any" value={l.qty} onChange={(e) => setLine(l.key, { qty: e.target.value })} />
                      <Input aria-label="Amount billed" placeholder="Amount billed (R)" type="number" min={0} step="0.01" value={l.amount} onChange={(e) => setLine(l.key, { amount: e.target.value })} />
                      <Input aria-label="Service date" type="date" value={l.service_date} onChange={(e) => setLine(l.key, { service_date: e.target.value })} />
                      <Input aria-label="Practice number" placeholder="Practice number" className="font-mono" value={l.provider_id} onChange={(e) => setLine(l.key, { provider_id: e.target.value })} />
                      <Select aria-label="Discipline" value={l.discipline} onChange={(e) => setLine(l.key, { discipline: e.target.value })}>
                        <option value="">Discipline from the register</option>
                        {disciplines.map((d) => <option key={d} value={d}>{d}</option>)}
                      </Select>
                      <Input aria-label="Diagnosis" placeholder="Diagnosis (ICD-10)" className="font-mono" value={l.dx} onChange={(e) => setLine(l.key, { dx: e.target.value })} />
                    </div>
                    {problem && <p className="mt-1.5 text-xs text-bad-fg">{problem}</p>}
                  </div>
                );
              })}
            </div>
          </Panel>
        </div>

        <aside className="lg:sticky lg:top-4 lg:self-start">
          <Panel title="Summary">
            <dl className="space-y-2.5 text-sm">
              <div className="flex justify-between gap-3"><dt className="text-ink-500">Reference</dt><dd className="font-mono text-[13px]">{claimId || "—"}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-500">Type</dt><dd>{CLAIM_TYPES[claimType]}</dd></div>
              <div className="flex justify-between gap-3"><dt className="text-ink-500">Lines</dt><dd className="tnum">{lines.length}</dd></div>
              <div className="flex justify-between gap-3 border-t border-line pt-2.5"><dt className="text-ink-500">Total billed</dt><dd className="tnum text-base font-semibold">{rand(billed)}</dd></div>
            </dl>
            <div className="mt-4 rounded-md border border-line bg-ink-50 px-3 py-2.5 text-[13px] text-ink-600">
              {missingDocs.length === 0 ? "All required documents are ticked." : (
                <>The claim will be held until these arrive: <span className="font-medium text-ink-900">{missingDocs.map((k) => DOCUMENTS[k] ?? k).join(", ")}</span>.</>
              )}
            </div>
            <Button variant="primary" className="mt-4 w-full" loading={busy} onClick={submit}>Submit claim</Button>
            {attempted && !valid && <p className="mt-2 text-xs text-bad-fg">{Object.keys(problems).length + badLines} field{Object.keys(problems).length + badLines === 1 ? "" : "s"} need attention.</p>}
          </Panel>
        </aside>
      </div>
    </div>
  );
}
