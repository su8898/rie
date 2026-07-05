// Types mirroring the RIE JSON API (verified against server/api/*.py and server/models.py).

export type Role =
  | "ADMIN"
  | "HANDLER"
  | "MEDICAL_OFFICER"
  | "INVESTIGATOR"
  | "LEGAL";

export type Band = "GREEN" | "AMBER" | "RED";

export type Disposition =
  | "FRAUD"
  | "MERITS"
  | "COMPLIANCE"
  | "PREAUTH"
  | "SI_GATE"
  | "ADJUSTED"
  | "CLEAN";

export interface Health {
  status: string;
  db: string;
}

export interface AuthUser {
  username: string;
  role: Role;
}

// A single determination row (POST /api/claims, GET /api/claims, and nested in detail).
export interface Determination {
  id: number;
  claim_id: string;
  accident_id: string;
  accident_action: string;
  band: Band;
  score: number;
  disposition: Disposition;
  validated: boolean;
  convergence: number;
  medical_payable: number;
  net_payable: number;
  eligible_to_pay: boolean;
  reasons: string[];
  shadow_signals: string[];
  holds: string[];
  engine_version: string;
  ruleset_effective: string;
  reference_edition: string;
  created_at: string | null;
}

// The immutable claim corpus row (GET /api/claims/{id} -> claim).
export interface ClaimLine {
  kind: "TARIFF" | "NAPPI";
  code: string;
  qty: number;
  amount: number;
  service_date: string;
  provider_id: string;
  dx?: string;
  emergency?: boolean;
  scheme_paid?: boolean;
}

export interface ClaimRaw {
  claim_id: string;
  claim_type: string;
  party_token: string;
  accident_date: string;
  lodged_on: string;
  case_number_raw?: string;
  today?: string;
  documents?: Record<string, boolean>;
  payee_verified?: boolean;
  merits_accepted?: boolean | null;
  fault_pct?: number | null;
  lines?: ClaimLine[];
  [k: string]: unknown;
}

export interface ClaimRecord {
  claim_id: string;
  claim_type: string;
  party_token: string;
  accident_date: string;
  lodged_on: string;
  raw: ClaimRaw;
  created_at: string | null;
}

export interface ClaimDetail {
  claim: ClaimRecord | null;
  determination: Determination;
}

export interface Reason {
  code: string;
  category: string;
  hard: boolean;
  points: number;
  maturity: "GROUNDED" | "HEURISTIC" | "UNVALIDATED";
  endogenous: boolean;
  basis: string;
  mode: "SHADOW" | "ADVISORY" | "SCORED";
}

export interface Dashboard {
  determinations: number;
  by_band: Record<Band, number>;
  by_disposition: Partial<Record<Disposition, number>>;
  eligible_to_pay: number;
  net_payable_total: number;
  medical_payable_total: number;
}

export interface Accident {
  accident_id: string;
  case_number: string | null;
  when: string;
  where: string;
  parties: string[];
  vehicles: string[];
  oar_occupants: number | null;
  claims: string[];
  n_claims: number;
  convergence: number;
}

// ── Operational workflow layer (GET /api/claims/{id}/workflow) ───────────────
// Each `actions` array is exactly the set of transitions currently allowed
// from that entity's state — we render one button per entry.

export interface LifecycleState {
  stage: string;
  actions: string[];
}

export interface MeritsState {
  status: string;
  fault_pct: number | null;
  ground: string | null;
  actions: string[];
}

export interface OfferHead {
  head: string;
  amount: number;
  detail: Record<string, unknown>;
}

export type OfferStatus = "ASSEMBLED" | "HELD";

export interface Offer {
  offer_id: number;
  claim_id: string;
  status: OfferStatus;
  total: number;
  gated_by: string[];
  heads: OfferHead[];
}

export interface SeriousInjuryRecord {
  id: number;
  status: string;
  list_match: boolean;
  wpi: number | null;
  narrative: boolean;
  actions: string[];
}

export interface UndertakingInvoice {
  id: number;
  status: string;
  billed: number;
  payable: number;
  reasons: string[];
  actions: string[];
}

export interface UndertakingRecord {
  id: number;
  origin: string;
  status: string;
  scope_dx: string[];
  actions: string[];
  invoices: UndertakingInvoice[];
}

export interface LitigationRecord {
  id: number;
  status: string;
  default_judgment: boolean;
  actions: string[];
}

export interface Workflow {
  claim_id: string;
  lifecycle: LifecycleState | null;
  merits: MeritsState | null;
  offer: Offer | null;
  serious_injury: SeriousInjuryRecord[];
  undertakings: UndertakingRecord[];
  litigation: LitigationRecord[];
}

// Ground options for a merits reject / dismiss (s19 exclusion grounds).
export type MeritsGround = "S19_EXCLUSION" | "SOLE_NEGLIGENCE" | "NO_MVA_NEXUS";

// Payload for POST /api/offer/{claim_id}.
export interface OfferHeadsInput {
  loss_of_earnings?: { annual_losses: number[] };
  general_damages?: {
    proposed: number;
    band_p25: number;
    band_p75: number;
  };
}

// ── Payments (payment-batch layer, /api/payments) ────────────────────────────
export type PaymentSource =
  | "SETTLEMENT"
  | "COURT_ORDER"
  | "UNDERTAKING_INVOICE"
  | "SUPPLIER"
  | "INTERIM";

export type BatchStatus = "OPEN" | "APPROVED" | "PAID" | "CANCELLED";

// A claim eligible to pay and not yet in a paid instruction (GET /payments/queue).
export interface QueueRow {
  claim_id: string;
  net_payable: number;
  disposition: Disposition;
  band: Band;
}

export interface PaymentInstruction {
  id: number;
  claim_id: string;
  source: PaymentSource;
  amount: number;
  paid: boolean;
}

export interface PaymentEvent {
  event: string;
  actor: string;
  role: string;
  amount: number | null;
  at: string | null;
  detail: Record<string, unknown>;
}

export interface BatchDict {
  id: number;
  status: BatchStatus;
  created_by: string;
  approved_by: string | null;
  paid_by: string | null;
  note: string | null;
  total: number;
  actions: string[];
  instructions: PaymentInstruction[];
  events: PaymentEvent[];
}

// ── Party intelligence (/api/parties) ────────────────────────────────────────
export type Rating = "CRITICAL" | "HIGH" | "ELEVATED" | "WATCH" | "LOW";
export type Confidence = "OK" | "LOW_N";

export interface RiskComponents {
  behavioural: number;
  cohort_outlier: number;
  over_servicing: number;
  history: number;
}

export interface Provider {
  provider_id: string;
  archetype: string;
  cohort: string;
  n_claims: number;
  n_lines: number;
  billed: number;
  avg_value: number;
  value_percentile: number;
  red_rate: number;
  flag_rate: number;
  score: number;
  rating: Rating;
  confidence: Confidence;
  components: RiskComponents;
}

export interface Attorney {
  attorney: string;
  cohort: string;
  n_claims: number;
  claim_type_mix: Record<string, number>;
  late_lodgement_share: number;
  score: number;
  rating: Rating;
  confidence: Confidence;
  components: RiskComponents;
}

export interface Claimant {
  party_token: string;
  n_accidents: number;
  accidents: string[];
}

export interface FairnessCohort {
  cohort: string;
  n_claims: number;
  flag_rate: number;
}

export interface Fairness {
  by_cohort: FairnessCohort[];
  four_fifths_ratio: number;
  pass: boolean;
}

// A flagged party from the risk sweep — the full provider/attorney dict plus a
// discriminating `type` and `id`. We keep the shared fields typed and allow the
// rest through.
export interface RiskSweepHit {
  type: "provider" | "attorney";
  id: string;
  score: number;
  rating: Rating;
  confidence: Confidence;
  n_claims: number;
  [k: string]: unknown;
}

export interface RiskSweep {
  threshold: number;
  n: number;
  flagged: RiskSweepHit[];
}

// ── Audit / clawback recovery (/api/audit) ───────────────────────────────────
export type AuditStatus = "OPEN" | "UNDER_REVIEW" | "RECOVERED" | "CLEARED";

export type RecoveryOutcome =
  | "RECOVERED_FULL"
  | "RECOVERED_PARTIAL"
  | "WRITTEN_OFF"
  | "NOT_PURSUED";

export interface AuditItem {
  id: number;
  claim_id: string;
  status: AuditStatus;
  reason: string;
  amount_at_stake: number;
  amount_recovered: number;
  recovery_outcome: string | null;
  assigned_to: string | null;
  opened_by: string;
  actions: string[];
  opened_at: string | null;
}

export interface AuditRoi {
  n_items: number;
  amount_at_stake: number;
  amount_recovered: number;
  recovery_rate: number;
  by_status: Record<string, number>;
  by_outcome: Record<string, number>;
}

export interface SweepResult {
  opened: number[];
  n: number;
  threshold: number;
}
