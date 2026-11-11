// Plain-language names for the claim's workflow: its stages, the steps between them, who may
// take each step, and what the step does. The server remains the authority on who may act.

import type { Role } from "../../types";
import type { Tone } from "../../ds/labels";

export const STAGE_PATH = ["LODGED", "VALIDATED", "MERITS", "QUANTUM", "OFFER_MADE", "SETTLED", "PAID", "FINALIZED"];

export const STAGES: Record<string, { label: string; help: string }> = {
  LODGED: { label: "Lodged", help: "Received. The lodgement still has to be checked." },
  VALIDATED: { label: "Validated", help: "The lodgement meets the requirements." },
  MERITS: { label: "Merits", help: "Liability is being decided." },
  QUANTUM: { label: "Quantum", help: "Liability is accepted. The amount is being assembled." },
  OFFER_MADE: { label: "Offer made", help: "The offer is with the claimant." },
  SETTLED: { label: "Settled", help: "The offer was accepted. Payment is due." },
  PAID: { label: "Paid", help: "The settlement has been paid." },
  FINALIZED: { label: "Finalised", help: "Nothing further is outstanding." },
  REJECTED_COMPLIANCE: { label: "Rejected: lodgement not compliant", help: "The lodgement did not meet the requirements. This ends the claim as lodged." },
  REPUDIATED: { label: "Repudiated", help: "Liability was rejected. The claimant may object, or the matter may go to court." },
  LITIGATION: { label: "In litigation", help: "The matter is before the court." },
  COURT_ORDER: { label: "Court order", help: "The court has ordered payment." },
};

export interface Step { label: string; help: string; danger?: boolean }

export const STEPS: Record<string, Step> = {
  // lifecycle
  "lifecycle.validate": { label: "Validate lodgement", help: "Confirms the lodgement meets the requirements. The claimant is told." },
  "lifecycle.reject_compliance": { label: "Reject lodgement", help: "The lodgement does not meet the requirements. The claimant is told what is outstanding.", danger: true },
  "lifecycle.open_merits": { label: "Open merits", help: "Starts the decision on liability." },
  "lifecycle.accept_merits": { label: "Move to quantum", help: "Liability is accepted, so the amount can be assembled. The merits decision must be Accepted first." },
  "lifecycle.repudiate": { label: "Repudiate the claim", help: "Liability is rejected. The claimant is told and may lodge an objection.", danger: true },
  "lifecycle.litigate": { label: "Move to litigation", help: "The matter goes to court." },
  "lifecycle.make_offer": { label: "Make the offer", help: "Sends the assembled offer to the claimant. An offer must be assembled and not held." },
  "lifecycle.settle": { label: "Record settlement", help: "The claimant accepted. The claim becomes payable in a payment run." },
  "lifecycle.court_order": { label: "Record court order", help: "The court ordered payment. The claim becomes payable in a payment run." },
  "lifecycle.pay": { label: "Mark as paid", help: "Normally done by releasing a payment run. Use this only when payment was made outside a run." },
  "lifecycle.finalize": { label: "Finalise", help: "Closes the claim. Nothing further is outstanding." },
  // merits
  "merits.accept": { label: "Accept liability", help: "Records the claimant's share of fault. Every head of damage is reduced by it." },
  "merits.reject": { label: "Reject liability", help: "Records the ground on which the Fund is not liable.", danger: true },
  "merits.appeal": { label: "Record an appeal", help: "The rejection is under appeal." },
  "merits.dismiss": { label: "Dismiss the appeal", help: "The rejection stands.", danger: true },
  // serious injury
  "si.accept": { label: "Accept as serious", help: "Opens general damages for this claim." },
  "si.reject": { label: "Not serious", help: "General damages stay closed. The claimant may appeal to the HPCSA.", danger: true },
  "si.appeal": { label: "Record HPCSA appeal", help: "The decision is before the HPCSA appeal tribunal." },
  "si.uphold": { label: "Appeal upheld", help: "The tribunal found the injury serious. General damages open." },
  "si.dismiss": { label: "Appeal dismissed", help: "The tribunal confirmed the injury is not serious.", danger: true },
  // undertakings
  "undertaking.activate": { label: "Activate", help: "Providers may bill against it from now on." },
  "undertaking.suspend": { label: "Suspend", help: "Invoices are refused until it is resumed.", danger: true },
  "undertaking.resume": { label: "Resume", help: "Providers may bill against it again." },
  "undertaking.terminate": { label: "Terminate", help: "Ends the undertaking for good.", danger: true },
  "undertaking.lapse": { label: "Mark as lapsed", help: "The undertaking has run its course.", danger: true },
  // invoices
  "invoice.adjudicate": { label: "Adjudicate", help: "Records the amount approved after checking the invoice." },
  "invoice.approve": { label: "Approve for payment", help: "The adjudicated amount becomes payable." },
  "invoice.reject": { label: "Reject", help: "Nothing is paid on this invoice.", danger: true },
  "invoice.pay": { label: "Mark as paid", help: "Records that the invoice was paid." },
  // litigation
  "litigation.plead": { label: "Pleadings filed", help: "The Fund has pleaded." },
  "litigation.set_trial": { label: "Trial date set", help: "The matter is set down for trial." },
  "litigation.default_judgment": { label: "Default judgment", help: "Judgment was granted because the Fund did not defend in time.", danger: true },
  "litigation.settle": { label: "Settled", help: "The matter was settled before judgment." },
  "litigation.judgment": { label: "Judgment given", help: "The court has given judgment." },
  "litigation.order_paid": { label: "Order paid", help: "The amount ordered or settled has been paid." },
  "litigation.close": { label: "Close the matter", help: "Nothing further is outstanding." },
};

export const PERMS: Record<string, Role[]> = {
  "lifecycle.validate": ["HANDLER"], "lifecycle.reject_compliance": ["HANDLER"], "lifecycle.open_merits": ["HANDLER"],
  "lifecycle.accept_merits": ["HANDLER", "LEGAL"], "lifecycle.repudiate": ["HANDLER", "LEGAL"], "lifecycle.litigate": ["LEGAL"],
  "lifecycle.make_offer": ["HANDLER"], "lifecycle.settle": ["HANDLER", "LEGAL"], "lifecycle.court_order": ["LEGAL"],
  "lifecycle.pay": ["ADMIN"], "lifecycle.finalize": ["HANDLER", "ADMIN"],
  "merits.accept": ["HANDLER", "LEGAL"], "merits.reject": ["HANDLER", "LEGAL"], "merits.appeal": ["LEGAL"], "merits.dismiss": ["LEGAL"],
  "si.create": ["MEDICAL_OFFICER"], "si.accept": ["MEDICAL_OFFICER"], "si.reject": ["MEDICAL_OFFICER"],
  "si.appeal": ["LEGAL"], "si.uphold": ["LEGAL"], "si.dismiss": ["LEGAL"],
  "undertaking.create": ["HANDLER", "MEDICAL_OFFICER"], "undertaking.activate": ["HANDLER", "MEDICAL_OFFICER"],
  "undertaking.suspend": ["INVESTIGATOR", "MEDICAL_OFFICER"], "undertaking.resume": ["INVESTIGATOR", "MEDICAL_OFFICER"],
  "undertaking.terminate": ["ADMIN", "MEDICAL_OFFICER"], "undertaking.lapse": ["ADMIN"],
  "invoice.submit": ["MEDICAL_OFFICER"], "invoice.adjudicate": ["MEDICAL_OFFICER"], "invoice.approve": ["MEDICAL_OFFICER"],
  "invoice.reject": ["MEDICAL_OFFICER"], "invoice.pay": ["ADMIN"],
  "offer.build": ["HANDLER"],
  "litigation.create": ["LEGAL"], "litigation.plead": ["LEGAL"], "litigation.set_trial": ["LEGAL"],
  "litigation.default_judgment": ["LEGAL", "ADMIN"], "litigation.settle": ["LEGAL"], "litigation.judgment": ["LEGAL"],
  "litigation.order_paid": ["ADMIN"], "litigation.close": ["LEGAL", "ADMIN"],
};

export const STATUS: Record<string, { label: string; tone: Tone }> = {
  // merits
  "merits.PENDING": { label: "Not decided", tone: "warn" }, "merits.ACCEPTED": { label: "Accepted", tone: "ok" },
  "merits.REJECTED": { label: "Rejected", tone: "bad" }, "merits.APPEALED": { label: "Under appeal", tone: "warn" },
  // offer
  "offer.ASSEMBLED": { label: "Assembled", tone: "ok" }, "offer.HELD": { label: "Held", tone: "warn" },
  // serious injury
  "si.SUBMITTED": { label: "Awaiting decision", tone: "warn" }, "si.RAF_ACCEPTED": { label: "Accepted as serious", tone: "ok" },
  "si.RAF_REJECTED": { label: "Not serious", tone: "bad" }, "si.HPCSA_APPEAL": { label: "On appeal at the HPCSA", tone: "warn" },
  "si.UPHELD": { label: "Appeal upheld: serious", tone: "ok" }, "si.DISMISSED": { label: "Appeal dismissed", tone: "bad" },
  // undertakings
  "undertaking.ISSUED": { label: "Issued, not active", tone: "info" }, "undertaking.ACTIVE": { label: "Active", tone: "ok" },
  "undertaking.SUSPENDED": { label: "Suspended", tone: "warn" }, "undertaking.TERMINATED": { label: "Terminated", tone: "neutral" },
  "undertaking.LAPSED": { label: "Lapsed", tone: "neutral" },
  // invoices
  "invoice.RECEIVED": { label: "Received", tone: "info" }, "invoice.ADJUDICATED": { label: "Adjudicated", tone: "warn" },
  "invoice.PAYABLE": { label: "Approved for payment", tone: "ok" }, "invoice.REJECTED": { label: "Rejected", tone: "bad" },
  "invoice.PAID": { label: "Paid", tone: "ok" },
  // litigation
  "litigation.SUMMONS_SERVED": { label: "Summons served", tone: "warn" }, "litigation.PLEADINGS": { label: "Pleadings", tone: "info" },
  "litigation.TRIAL_SET": { label: "Trial date set", tone: "info" }, "litigation.SETTLED": { label: "Settled", tone: "ok" },
  "litigation.JUDGMENT": { label: "Judgment", tone: "warn" }, "litigation.ORDER_PAID": { label: "Order paid", tone: "ok" },
  "litigation.CLOSED": { label: "Closed", tone: "neutral" },
};

export const GROUNDS: Record<string, string> = {
  S19_EXCLUSION: "Excluded under section 19 of the Act",
  SOLE_NEGLIGENCE: "The claimant was solely negligent",
  NO_MVA_NEXUS: "Not caused by the driving of a motor vehicle",
};

export const HEADS: Record<string, string> = {
  PAST_MEDICAL: "Past medical expenses",
  LOSS_OF_EARNINGS: "Loss of earnings",
  LOSS_OF_SUPPORT: "Loss of support",
  GENERAL_DAMAGES: "General damages",
  FUNERAL: "Funeral expenses",
};

/** The history's `area` (the machine's name on the server) mapped to the keys used above. */
export const AREAS: Record<string, { key: string; label: string }> = {
  claim_lifecycle: { key: "lifecycle", label: "Claim" },
  merits: { key: "merits", label: "Merits" },
  serious_injury: { key: "si", label: "Serious-injury assessment" },
  undertaking: { key: "undertaking", label: "Undertaking" },
  undertaking_invoice: { key: "invoice", label: "Undertaking invoice" },
  litigation: { key: "litigation", label: "Litigation matter" },
};
