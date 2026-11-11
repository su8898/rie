// Plain language for everything the engine says in codes. Screens show the label; the code is
// kept as secondary detail for the people who need it.

import type { Band, Disposition } from "../types";

export type Tone = "ok" | "warn" | "bad" | "info" | "neutral" | "brand";

export const CLAIM_TYPES: Record<string, string> = {
  SUPPLIER: "Supplier claim",
  PERSONAL: "Personal claim",
  UNDERTAKING_INVOICE: "Undertaking invoice",
};

export const RISK: Record<Band, { label: string; tone: Tone }> = {
  GREEN: { label: "Low", tone: "ok" },
  AMBER: { label: "Medium", tone: "warn" },
  RED: { label: "High", tone: "bad" },
};

export const DISPOSITIONS: Record<Disposition, { label: string; tone: Tone; help: string }> = {
  FRAUD: { label: "Fraud review", tone: "bad", help: "Held for an investigator before anything is paid." },
  MERITS: { label: "Awaiting merits", tone: "warn", help: "Liability has not been accepted yet." },
  COMPLIANCE: { label: "Compliance hold", tone: "warn", help: "A statutory or documentary requirement is not met." },
  PREAUTH: { label: "Pre-authorisation", tone: "warn", help: "A line needed prior authorisation." },
  SI_GATE: { label: "Serious injury", tone: "warn", help: "General damages wait on the serious-injury assessment." },
  REVIEW: { label: "Pricing review", tone: "info", help: "A line has no reference price and needs a reviewer." },
  ADJUSTED: { label: "Adjusted", tone: "info", help: "Paid at the adjudicated amount, below what was billed." },
  CLEAN: { label: "Clean", tone: "ok", help: "Nothing to resolve." },
};

/** The one status a handler needs for a claim: can it be paid, and if not, what is in the way. */
export function claimStatus(d: { eligible_to_pay: boolean; disposition: Disposition }): {
  label: string;
  tone: Tone;
} {
  if (d.eligible_to_pay) {
    return d.disposition === "ADJUSTED"
      ? { label: "Ready to pay, adjusted", tone: "ok" }
      : { label: "Ready to pay", tone: "ok" };
  }
  const x = DISPOSITIONS[d.disposition];
  return x ? { label: x.label, tone: x.tone } : { label: d.disposition, tone: "neutral" };
}

export const HOLDS: Record<string, { label: string; action: string }> = {
  held_for_validation: { label: "Supporting documents outstanding", action: "Obtain the missing documents listed under Documents." },
  held_for_merits: { label: "Merits not accepted", action: "Record the merits decision under Workflow." },
  held_fraud: { label: "Held for fraud review", action: "An investigator must clear the case." },
  held_merits: { label: "Held on merits", action: "Liability was rejected or is undecided." },
  held_compliance: { label: "Compliance hold", action: "Resolve the compliance findings below." },
  held_preauth: { label: "Pre-authorisation hold", action: "Confirm or obtain the authorisation." },
  held_si_gate: { label: "Serious-injury gate", action: "Decide the RAF 4 assessment under Workflow." },
  held_review: { label: "Pricing review", action: "A reviewer must price the unbenchmarked line." },
  PAYEE_UNVERIFIED: { label: "Payee not verified", action: "Verify the payee's banking details." },
  ATTORNEY_NOT_IN_STANDING: { label: "Attorney not in good standing", action: "Confirm standing with the Legal Practice Council." },
  LIFE_STATUS_MISMATCH: { label: "Life status mismatch", action: "Reconcile the claimant's status with Home Affairs." },
};

export const REASONS: Record<string, string> = {
  PRESCRIBED_LODGEMENT: "Lodged after the prescription period",
  PRESCRIBED_SUMMONS: "Summons served after the prescription period",
  S24_INCOMPLETE: "Mandatory documents missing",
  OAR_MISSING: "Accident report missing",
  DUPLICATE_CLAIM: "Claimant already has a claim for this accident",
  PROVIDER_UNREGISTERED: "Practice may not bill the Fund",
  ATTORNEY_NOT_IN_STANDING: "Attorney not in good standing",
  PAYEE_UNVERIFIED: "Payee not verified",
  LIFE_STATUS_MISMATCH: "Service dated after the claimant's death",
  SOLE_NEGLIGENCE: "Claimant solely negligent",
  S19_EXCLUSION: "Excluded under section 19",
  NO_MVA_NEXUS: "No link to a motor vehicle accident",
  SERVICE_BEFORE_ACCIDENT: "Service dated before the accident",
  SUPPLIER_PRECLUSION: "Already paid on another claim",
  DUPLICATE_LINE: "Duplicate line",
  UNBUNDLING_CONFLICT: "Code limited to once per encounter",
  PREAUTH_MISSING: "Pre-authorisation missing",
  PREAUTH_EXCEEDED: "Above the authorised amount",
  UNDERTAKING_NOT_ACTIVE: "No active undertaking",
  UNDERTAKING_SCOPE: "Outside the undertaking's scope",
  GENERAL_DAMAGES_NO_SI: "No accepted serious injury",
  EARNINGS_UNPROVEN: "Earnings not proven",
  REFERENCE_UNRESOLVED: "No reference price for the code",
  BILLED_OVER_REFERENCE: "Billed above the reference tariff",
  VALUE_OUTLIER: "Unusually high value",
  VALUE_OUTLIER_EXTREME: "Extremely high value",
  LINE_COUNT_OUTLIER: "Unusually many lines on one visit",
  MATERIAL_PADDING: "Visit dominated by consumables",
  IMPOSSIBLE_DAY: "Provider billed too many claimants in a day",
  IMPOSSIBLE_WEEK: "Too many visits for one claimant in a week",
  DX_ACCIDENT_MISMATCH: "Diagnosis does not fit the accident",
  PRE_EXISTING_CONDITION: "Possible pre-existing condition",
  INJURY_ESCALATION: "Injury worse than first recorded",
  OAR_MISMATCH: "Accident report details differ",
  OAR_REUSED: "Police case number reused",
  EARNINGS_OUTLIER: "Earnings out of line with the sector",
  LATE_CLAIM_CLUSTER: "Lodged in a deadline cluster",
  RING_PARTIES: "Parties recur across accidents",
  PROVIDER_SHOPPING: "Several providers of one discipline",
  CLAIMANT_SURGE: "More claimants than vehicle occupants",
  CLAIMANT_RECURRENCE: "Claimant recurs across accidents",
  CONVERGENCE_THIN: "Accident thinly corroborated",
  PAYMENT_ADJUSTED: "Apportioned, or net of an earlier payment",
};

export const reasonLabel = (code: string) => REASONS[code] ?? code.replace(/_/g, " ").toLowerCase();

export const DOCUMENTS: Record<string, string> = {
  RAF1: "RAF 1 claim form",
  RAF2: "RAF 2 supplier claim form",
  OAR: "Accident report (police)",
  ID: "Identity document",
  BANK: "Banking details",
  INVOICES: "Invoices and statements",
};

/** The documents each claim type must carry — mirrors the engine's mandatory checklist. */
export const REQUIRED_DOCUMENTS: Record<string, string[]> = {
  PERSONAL: ["RAF1", "OAR", "ID", "BANK"],
  SUPPLIER: ["RAF2", "OAR", "INVOICES", "BANK"],
  UNDERTAKING_INVOICE: ["INVOICES", "BANK"],
};

export const PAYMENT_STATUS: Record<string, { label: string; tone: Tone }> = {
  NOT_QUEUED: { label: "Not in a payment run", tone: "neutral" },
  QUEUED: { label: "In an open payment run", tone: "info" },
  APPROVED: { label: "Approved, awaiting payment", tone: "info" },
  PAID: { label: "Paid", tone: "ok" },
};

/** A date (local midnight) or a server timestamp. The server stores timestamps in UTC without an
 *  offset, so a bare timestamp is read as UTC and shown in the viewer's own time zone. */
function parseStamp(iso: string): Date {
  if (iso.length <= 10) return new Date(`${iso}T00:00:00`);
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso.replace(" ", "T")}Z`);
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = parseStamp(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = parseStamp(iso);
  return isNaN(d.getTime()) ? iso : `${shortDate(iso)}, ${d.toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit", hour12: false })}`;
}

// ── Payments ─────────────────────────────────────────────────────────────────
export const RUN_STATUS: Record<string, { label: string; tone: Tone; help: string }> = {
  OPEN: { label: "Being assembled", tone: "info", help: "Claims can still be added or removed. A second person must approve it." },
  APPROVED: { label: "Approved, awaiting release", tone: "warn", help: "The contents are fixed. A third person must release the payment." },
  PAID: { label: "Paid", tone: "ok", help: "The payment was released and a remittance advice went to each practice." },
  CANCELLED: { label: "Cancelled", tone: "neutral", help: "Nothing was paid. Its claims went back to the ready-to-pay list." },
};

export const PAYMENT_SOURCES: Record<string, string> = {
  SUPPLIER: "Supplier claim",
  UNDERTAKING_INVOICE: "Undertaking invoice",
  SETTLEMENT: "Settlement",
  COURT_ORDER: "Court order",
  INTERIM: "Interim payment",
};

export const QUEUE_BLOCKS: Record<string, string> = {
  IN_BATCH: "Already in a payment run",
  NOT_SETTLED: "Not settled yet",
  PAYEE_UNVERIFIED: "Payee not verified",
  NO_CLAIM_RECORD: "No claim record",
};

export const REMITTANCE_STATUS: Record<string, { label: string; tone: Tone }> = {
  REMITTED: { label: "Sent", tone: "info" },
  ACKNOWLEDGED: { label: "Acknowledged by the practice", tone: "ok" },
};

export const PAYMENT_EVENTS: Record<string, string> = {
  CREATED: "Run created",
  INSTRUCTION_ADDED: "Claim added",
  INSTRUCTION_REMOVED: "Claim removed",
  NOTE_CHANGED: "Note changed",
  APPROVED: "Approved",
  PAID: "Payment released",
  CANCELLED: "Cancelled",
};

/** The Fund's refusals on a payment action, in the words an operator needs. */
export function paymentError(message: string): string {
  const m = message.toLowerCase();
  if (m.includes("approver must differ")) return "You assembled this run, so a different administrator must approve it.";
  if (m.includes("payer must differ")) return "You assembled or approved this run, so a different administrator must release the payment.";
  if (m.includes("payee_unverified")) return "The payee's banking details are not verified, so this claim cannot be paid yet.";
  if (m.includes("is paid once") || m.includes("already has a")) return "This claim is already in a payment run. A claim is paid once.";
  if (m.includes("not eligible to pay")) return "This claim is not cleared for payment.";
  if (m.includes("not settled") || m.includes("no assembled offer")) return "This claim has no settlement or court order yet, so there is nothing to pay.";
  if (m.includes("requires accepted merits")) return "An interim payment needs the merits to be accepted first.";
  if (m.includes("exceeds the payable")) return "The amount is more than the claim's payable amount.";
  if (m.includes("empty batch")) return "Add at least one claim before the run is approved.";
  if (m.includes("batch is not open")) return "This run is no longer being assembled, so it cannot be changed.";
  if (m.includes("role")) return "Your role does not allow this action.";
  return message;
}

// ── Practices ────────────────────────────────────────────────────────────────
export const PRACTICE_STATUS: Record<string, { label: string; tone: Tone; help: string }> = {
  ACTIVE: { label: "Active", tone: "ok", help: "May bill the Fund." },
  SUSPENDED: { label: "Suspended", tone: "warn", help: "Cannot bill the Fund until it is reinstated." },
  DEREGISTERED: { label: "Deregistered", tone: "bad", help: "Removed from practice. Cannot bill the Fund." },
};

export const PRACTICE_TYPES: Record<string, string> = {
  INDIVIDUAL: "Individual practitioner",
  GROUP: "Group practice",
  INSTITUTION: "Institution",
  SUPPLIER: "Supplier",
};

export const PRACTICE_SETTINGS: Record<string, string> = {
  ROOMS: "Consulting rooms",
  HOSPITAL: "Hospital",
  ER: "Emergency unit",
  MIXED: "Rooms and hospital",
};

export const PRACTICE_SOURCES: Record<string, string> = {
  MANUAL: "Captured by an administrator",
  IMPORT: "Imported from a file",
  PCNS: "Practice-number register",
};

export const PARTY_RATING: Record<string, { label: string; tone: Tone }> = {
  CRITICAL: { label: "Critical", tone: "bad" },
  HIGH: { label: "High", tone: "bad" },
  ELEVATED: { label: "Elevated", tone: "warn" },
  WATCH: { label: "Watch", tone: "warn" },
  LOW: { label: "Low", tone: "ok" },
};

export const PRACTICE_FIELDS: Record<string, string> = {
  practice_name: "name",
  discipline: "discipline",
  practice_type: "type",
  setting: "setting",
  professional_nr: "council number",
  verified: "verified",
  notes: "notes",
};

// ── Administration ───────────────────────────────────────────────────────────
export const ROLES: Record<string, { label: string; help: string }> = {
  HANDLER: { label: "Claims handler", help: "Captures and progresses claims, and assembles payment runs." },
  MEDICAL_OFFICER: { label: "Medical officer", help: "Decides serious-injury assessments and undertakings." },
  INVESTIGATOR: { label: "Investigator", help: "Works fraud cases and post-payment recovery." },
  LEGAL: { label: "Legal officer", help: "Handles litigation and referred disputes." },
  ADMIN: { label: "Administrator", help: "Maintains users and settings, and approves and releases payments." },
};

export const SIGNAL_MODES: Record<string, { label: string; tone: Tone; help: string }> = {
  SCORED: { label: "Scored", tone: "ok", help: "Counts toward the claim's risk score and can hold a claim." },
  ADVISORY: { label: "Advisory", tone: "info", help: "Shown to the handler, but does not change the score." },
  SHADOW: { label: "Shadow", tone: "neutral", help: "Recorded for measurement only. Handlers do not see it." },
};

export const MATURITY: Record<string, string> = {
  GROUNDED: "Set by law",
  HEURISTIC: "Rule of thumb",
  UNVALIDATED: "Not yet validated",
};

export const CODE_RULE_KINDS: Record<string, { label: string; param: string | null; help: string }> = {
  ONCE_PER_ENCOUNTER: { label: "Once per encounter", param: null, help: "A repeat for the same claimant, practice and day is not paid." },
  TIME_BLOCK: { label: "Time: one block per N minutes", param: "Block length in minutes", help: "Quantity is minutes. One block per N minutes or part of it." },
  TIME_ANAES: { label: "Time: anaesthetic, per 15 minutes", param: null, help: "Quantity is minutes. One block per 15 minutes in the first hour, 1.5 blocks after." },
  TIME_FIRST_HOUR: { label: "Time: first hour, then per 15 minutes", param: null, help: "Quantity is minutes. One block for the first hour, then a third per 15 minutes." },
  PCT_OF_TIME: { label: "Percentage of anaesthetic time", param: "Share, from 0 to 1 (0.5 is half)", help: "A share of the anaesthetic time billed by the same practice on the same day." },
};

export const AUDIT_AREAS: Record<string, string> = {
  user: "Users",
  cap: "Statutory cap",
  preauth: "Pre-authorisation codes",
  negotiated: "Negotiated rates",
  rate: "Dated rates",
  code_rule: "Coding rules",
  signal_mode: "Signal modes",
  rails_party: "Channel access",
  provider_register: "Practice register",
  price_list: "Price lists",
};

/** One audit entry in plain words: what was done, and the detail worth showing beside it. */
export function describeAudit(a: { action: string; target: string; detail: Record<string, unknown> }): { title: string; note?: string } {
  const d = a.detail ?? {};
  const s = (k: string) => (d[k] === undefined || d[k] === null ? "" : String(d[k]));
  switch (a.action) {
    case "user.create": return { title: "User created", note: `Role: ${ROLES[s("role")]?.label ?? s("role")}` };
    case "user.set_role": return { title: "Role changed", note: `To ${ROLES[s("role")]?.label ?? s("role")}` };
    case "user.set_active": return { title: d.active ? "User reactivated" : "User deactivated" };
    case "user.reset_password": return { title: "Password reset" };
    case "cap.upsert": return { title: "Statutory cap set", note: `R${Number(d.annual_cap).toLocaleString("en-ZA")} a year` };
    case "cap.delete": return { title: "Statutory cap removed" };
    case "preauth.add": return { title: "Pre-authorisation code added" };
    case "preauth.remove": return { title: "Pre-authorisation code removed" };
    case "negotiated.upsert": return { title: "Negotiated rate set", note: `R${Number(d.rate).toLocaleString("en-ZA", { minimumFractionDigits: 2 })}` };
    case "negotiated.delete": return { title: "Negotiated rate removed" };
    case "code_rule.upsert": return { title: "Coding rule set", note: CODE_RULE_KINDS[s("rule")]?.label ?? s("rule") };
    case "code_rule.delete": return { title: "Coding rule removed" };
    case "signal_mode.set": return { title: `Signal mode set to ${SIGNAL_MODES[s("mode")]?.label ?? s("mode")}`, note: s("note") || undefined };
    case "signal_mode.clear": return { title: "Signal mode reset to its default" };
    case "rails_party.register": return { title: "Channel party registered", note: s("kind") === "SWITCH" ? "Switch" : "Provider system" };
    case "rails_party.status": return { title: s("status") === "ACTIVE" ? "Channel party reactivated" : "Channel party suspended" };
    case "rails_party.providers": return { title: "Practices it may act for changed", note: Array.isArray(d.providers) ? (d.providers.includes("*") ? "Every practice" : `${d.providers.length} practice${d.providers.length === 1 ? "" : "s"}`) : undefined };
    case "rails_party.rotate_key": return { title: "Signing key replaced" };
    case "provider_register.add": return { title: "Practice added to the register" };
    case "provider_register.update": return { title: "Practice details changed", note: Object.keys(d).map((k) => PRACTICE_FIELDS[k] ?? k).join(", ") || undefined };
    case "provider_register.status": return { title: `Practice status changed to ${PRACTICE_STATUS[s("to")]?.label ?? s("to")}`, note: s("reason") || undefined };
    default: {
      if (a.action.startsWith("price_list.")) {
        const p = describePriceListChange(a);
        return { title: `${p.title}${s("name") ? `: ${s("name")}` : ""}`, note: p.note };
      }
      const [area, verb = ""] = a.action.split(".");
      return { title: `${AUDIT_AREAS[area] ?? area}: ${verb.replace(/_/g, " ")}` };
    }
  }
}

// ── Cases, disputes, notifications ───────────────────────────────────────────
export const CASE_LANES: Record<string, { label: string; owner: string; help: string }> = {
  REVIEW: { label: "Billing review", owner: "HANDLER", help: "A pricing or billing question a claims handler resolves." },
  BLOCK: { label: "Fraud hold", owner: "INVESTIGATOR", help: "Payment is held while an investigator looks into it." },
  CLAWBACK: { label: "Recovery", owner: "INVESTIGATOR", help: "Money already paid that may have to be recovered." },
};

export const CASE_STATUS: Record<string, { label: string; tone: Tone }> = {
  OPEN: { label: "Unassigned", tone: "info" },
  IN_REVIEW: { label: "In progress", tone: "brand" },
  ESCALATED: { label: "Escalated", tone: "warn" },
  CLOSED: { label: "Closed", tone: "neutral" },
};

export const CASE_VERDICTS: Record<string, string> = {
  CONFIRMED_FRAUD: "Fraud confirmed",
  CLEARED: "Cleared",
  ADJUSTED: "Payment adjusted",
  NO_ACTION: "No action needed",
  REFERRED_LEGAL: "Referred to legal",
};

export const CASE_PRIORITIES: Record<number, { label: string; days: number }> = {
  1: { label: "Urgent", days: 1 }, 2: { label: "High", days: 3 }, 3: { label: "Normal", days: 7 },
  4: { label: "Low", days: 10 }, 5: { label: "Lowest", days: 14 },
};

export const DISPUTE_SUBJECTS: Record<string, string> = {
  MERITS: "Liability decision",
  QUANTUM: "Amount offered",
  TARIFF: "Tariff or price applied",
  REPUDIATION: "Claim rejected",
  SERIOUS_INJURY: "Serious-injury decision",
};

export const DISPUTE_RAISERS: Record<string, string> = { CLAIMANT: "Claimant", PROVIDER: "Practice", ATTORNEY: "Attorney" };

export const DISPUTE_STATUS: Record<string, { label: string; tone: Tone; help: string }> = {
  LODGED: { label: "New", tone: "info", help: "Lodged and waiting for someone to start the reconsideration." },
  UNDER_RECONSIDERATION: { label: "Being reconsidered", tone: "brand", help: "The Fund is reconsidering its decision." },
  REJECTED: { label: "Rejected", tone: "warn", help: "The decision stands. Legal may still refer it to a tribunal or court." },
  REFERRED: { label: "Referred", tone: "warn", help: "With the tribunal or the court. Legal records the outcome." },
  UPHELD: { label: "Upheld", tone: "ok", help: "The objection succeeded and the decision was revised." },
  RESOLVED: { label: "Resolved", tone: "neutral", help: "The tribunal or court outcome is recorded." },
  WITHDRAWN: { label: "Withdrawn", tone: "neutral", help: "The objection was withdrawn." },
};

export const DISPUTE_CHANNELS: Record<string, string> = {
  INTERNAL: "Internal reconsideration",
  HPCSA_TRIBUNAL: "HPCSA tribunal",
  LITIGATION: "Litigation",
};

export const NOTIFICATION_STATUS: Record<string, { label: string; tone: Tone; help: string }> = {
  PENDING: { label: "Waiting to send", tone: "info", help: "Queued for the delivery service." },
  SENT: { label: "Sent", tone: "ok", help: "Delivered to the claimant's chosen channel." },
  FAILED: { label: "Failed", tone: "bad", help: "Delivery failed. Check the contact details, then try again." },
  SUPPRESSED: { label: "Not sent", tone: "neutral", help: "The claimant has not agreed to be contacted." },
};

export const NOTIFICATION_CHANNELS: Record<string, string> = { SMS: "SMS", EMAIL: "Email", NONE: "None" };

/** "DOCS_OUTSTANDING" reads as "Docs outstanding". */
export const humanise = (code: string) => (code ? code.charAt(0) + code.slice(1).toLowerCase().replace(/_/g, " ") : "");

/** How long until a due date, or how late it is. */
export function dueText(days: number | null | undefined, overdue: boolean): string {
  if (days == null) return "No due date";
  if (overdue) return days <= -1 ? `${Math.abs(days)} day${Math.abs(days) === 1 ? "" : "s"} overdue` : "Overdue";
  return days <= 0 ? "Due within a day" : `${days} day${days === 1 ? "" : "s"} left`;
}

/** The refusals of the case and dispute machines, in plain words. */
export function workError(message: string): string {
  const m = message.toLowerCase();
  if (m.includes("merits not accepted")) return "Liability has not been accepted yet. Record the merits decision first.";
  if (m.includes("no assembled offer")) return "There is no assembled offer. Build the offer first, and clear anything holding it.";
  if (m.includes("checklist incomplete")) return "The supporting documents are incomplete, so the lodgement cannot be validated.";
  if (m.includes("undertaking not active")) return "The undertaking is not active, so it cannot take an invoice.";
  if (m.includes("lane is owned by")) return "This case belongs to another role, so you cannot act on it.";
  if (m.includes("not permitted for role") || m.includes("may not") || m.includes("only ")) return "Your role does not allow this action.";
  if (m.includes("cannot be changed")) return "This is closed and can no longer be changed.";
  if (m.includes("no transition") || m.includes("illegal") || m.includes("not allowed from")) return "That step is not available from the current status. Reload the page to see the latest status.";
  return message;
}

// ── Price lists ──────────────────────────────────────────────────────────────
export const PRICE_LIST_STATE: Record<string, { label: string; tone: Tone; help: string }> = {
  DRAFT: { label: "Draft", tone: "warn", help: "Being put together. Its entries can still be changed." },
  PUBLISHED: { label: "Published", tone: "ok", help: "Fixed. A correction is made by issuing a new edition." },
  RETIRED: { label: "Retired", tone: "neutral", help: "Kept for the record. No longer current." },
};

export const LEGAL_STANDING: Record<string, { label: string; tone: Tone; help: string }> = {
  ENFORCEABLE: { label: "Enforceable", tone: "ok", help: "The Fund may hold providers to these prices: a contract, or a price set by law." },
  ACCEPTED: { label: "Accepted", tone: "info", help: "Providers accept these prices as the going rate. The Fund may pay up to them." },
  INTERDICTED: { label: "Interdicted", tone: "bad", help: "A court has stopped the Fund from applying this list. It is kept for comparison only." },
};

export const PRICE_LIST_FIELDS: Record<string, string> = {
  name: "Name", edition: "Edition", source: "Published in", legal_status: "Legal standing", status_note: "Reason for the standing",
  effective_from: "In effect from", effective_to: "In effect to", notes: "Notes", discipline: "Discipline", code: "Code",
  alt_code: "Second code", price_column: "Price column", description: "Description", units: "Units", units_suffix: "Units marker",
  value_rand: "Rand value", unit_of_issue: "Unit of issue", source_page: "Page", note: "Note",
};

/** The period a price list is in effect, in words. */
export function inEffect(pl: { effective_from: string | null; effective_to: string | null }): string {
  if (!pl.effective_from) return "No start date set";
  return pl.effective_to ? `${shortDate(pl.effective_from)} to ${shortDate(pl.effective_to)}` : `From ${shortDate(pl.effective_from)}`;
}

/** One change to a price list in plain words. */
export function describePriceListChange(h: { action: string; detail: Record<string, unknown> }): { title: string; note?: string } {
  const d = h.detail ?? {};
  const s = (k: string) => (d[k] === undefined || d[k] === null ? "" : String(d[k]));
  const n = (k: string) => Number(d[k] ?? 0).toLocaleString("en-ZA");
  const entry = [s("code"), s("discipline"), s("price_column") && s("price_column") !== "standard" ? s("price_column") : ""].filter(Boolean).join(" · ");
  const fields = d.changed && typeof d.changed === "object" ? Object.keys(d.changed as object).map((k) => PRICE_LIST_FIELDS[k] ?? k).join(", ") : "";
  switch (h.action) {
    case "price_list.create": return { title: "Price list created", note: s("edition") ? `Edition ${s("edition")}` : undefined };
    case "price_list.update": return { title: "Details changed", note: fields || undefined };
    case "price_list.legal_status":
      return { title: `Legal standing changed from ${LEGAL_STANDING[s("from")]?.label ?? s("from")} to ${LEGAL_STANDING[s("to")]?.label ?? s("to")}`, note: s("reason") || undefined };
    case "price_list.factors": return { title: "Conversion factors changed" };
    case "price_list.publish": return { title: "Published", note: `${n("entries")} entries, in effect from ${shortDate(s("effective_from"))}` };
    case "price_list.retire": return { title: "Retired", note: [`In effect to ${shortDate(s("effective_to"))}`, s("note")].filter(Boolean).join(". ") };
    case "price_list.copy": return { title: "New edition started", note: `From ${s("from_name")}, ${n("entries")} entries` };
    case "price_list.delete": return { title: "Draft deleted", note: `${n("entries")} entries` };
    case "price_list.entry.add": return { title: "Entry added", note: entry || undefined };
    case "price_list.entry.update": return { title: "Entry changed", note: [entry, fields].filter(Boolean).join(": ") || undefined };
    case "price_list.entry.delete": return { title: "Entry removed", note: entry || undefined };
    case "price_list.import": {
      const parts = [`${n("added")} added`];
      if (Number(d.removed)) parts.push(`${n("removed")} removed first`);
      if (Number(d.failed)) parts.push(`${n("failed")} rows could not be read`);
      return { title: "Entries loaded from a file", note: parts.join(", ") };
    }
    default: return { title: h.action.replace("price_list.", "").replace(/[._]/g, " ") };
  }
}

