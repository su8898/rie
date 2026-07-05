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
  // Provider discipline for a TARIFF line — the backend prices per discipline
  // (e.g. code 4301: Chiropractor R399.06 vs GP R10.60). "" = claim default.
  discipline?: string;
  emergency?: boolean;
  scheme_paid?: boolean;
}

// A per-discipline tariff rate row (GET /api/reference/tariffs?code=...).
export interface TariffRate {
  code: string;
  discipline: string;
  rate: number;
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

// Payload for POST /api/offer/{claim_id}. General damages may pass explicit bands, or an
// injury_class/severity_tier for the comparable-awards store to compute the band (§5d).
export interface OfferHeadsInput {
  loss_of_earnings?: { annual_losses: number[] };
  loss_of_support?: { annual_losses: number[] };
  general_damages?: {
    proposed: number;
    band_p25?: number;
    band_p75?: number;
    injury_class?: string;
    severity_tier?: string;
  };
  funeral?: { necessary_costs: number; non_necessary?: number };
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
  // Disparate-impact enrichment (governance view). Older callers ignore these.
  impact?: number | null; // cohort flag rate ÷ overall
  small?: boolean; // too few claims to judge
  review?: boolean; // impact outside the band on either tail
}

export interface Fairness {
  by_cohort: FairnessCohort[];
  four_fifths_ratio: number;
  pass: boolean;
  overall_flag_rate?: number;
  impact_low?: number;
  impact_high?: number;
  min_group?: number;
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

// ── Cases (/api/cases) ───────────────────────────────────────────────────────
export type CaseLane = "REVIEW" | "BLOCK" | "CLAWBACK";
export type CaseVerdict =
  | "CONFIRMED_FRAUD"
  | "CLEARED"
  | "ADJUSTED"
  | "NO_ACTION"
  | "REFERRED_LEGAL";

export interface CaseItem {
  id: number;
  claim_id: string | null;
  lane: CaseLane;
  status: string; // OPEN | IN_REVIEW | ESCALATED | CLOSED
  priority: number; // 1..5
  reason: string;
  rand_at_stake: number;
  owner_role: string | null;
  assigned_to: string | null;
  verdict: string | null;
  root_cause: string | null;
  rand_recovered: number;
  rand_prevented: number;
  opened_by: string;
  opened_at: string | null;
  due_at: string | null;
  closed_at: string | null;
  sla_days: number | null;
  days_to_sla: number | null;
  overdue: boolean;
  actions: string[];
}

export interface CaseAnalytics {
  n: number;
  open: number;
  by_lane: Record<string, number>;
  by_status: Record<string, number>;
  by_verdict: Record<string, number>;
  rand_at_stake_open: number;
  rand_recovered: number;
  rand_prevented: number;
  overdue: number;
}

export interface CaseNote {
  id: number;
  author: string;
  body: string;
  created_at: string | null;
}

// ── Disputes (/api/disputes) ─────────────────────────────────────────────────
export type DisputeSubject =
  | "MERITS"
  | "QUANTUM"
  | "TARIFF"
  | "REPUDIATION"
  | "SERIOUS_INJURY";
export type DisputeRaiser = "CLAIMANT" | "PROVIDER" | "ATTORNEY";

export interface DisputeItem {
  id: number;
  claim_id: string;
  subject: DisputeSubject;
  raised_by: DisputeRaiser;
  grounds: string;
  status: string; // LODGED | UNDER_RECONSIDERATION | UPHELD | REJECTED | REFERRED | RESOLVED | WITHDRAWN
  channel: string | null; // INTERNAL | HPCSA_TRIBUNAL | LITIGATION
  outcome: string | null;
  linked_ref: string | null;
  opened_by: string;
  opened_at: string | null;
  deadline: string | null;
  days_to_deadline: number | null;
  overdue: boolean;
  closed_at: string | null;
  actions: string[];
}

export interface DisputeAnalytics {
  n: number;
  open: number;
  by_subject: Record<string, number>;
  by_status: Record<string, number>;
  by_channel: Record<string, number>;
  by_raised_by: Record<string, number>;
}

// ── Governance / precision (/api/governance) ─────────────────────────────────
export interface PrecisionRow {
  signal: string;
  category: string | null;
  maturity: string | null;
  current_mode: string;
  recommended_mode: string;
  fired: number;
  labeled: number;
  substantiated: number;
  substantiation: number | null;
  wilson_lower: number | null;
  wilson_upper: number | null;
  action?: "PROMOTE" | "DEMOTE";
}

export interface RecallEstimate {
  reviewed: number;
  misses: number;
  miss_rate: number | null;
  miss_rate_wilson_upper: number | null;
  recall_floor: number | null;
}

export interface RecallSample {
  population: number;
  sample_size: number;
  claims: string[];
}

export interface LabelRow {
  claim_id: string;
  verdict: string;
  label: string;
  lane: string;
  case_id: number;
}

// ── Admin (/api/admin) ───────────────────────────────────────────────────────
export interface AdminUser {
  id: number;
  username: string;
  role: Role;
  active: boolean;
}

export interface StatutoryCap {
  effective_from: string;
  annual_cap: number;
}

export interface NegotiatedRate {
  kind: string;
  code: string;
  rate: number;
}

export interface SignalMode {
  signal: string;
  maturity: string;
  category: string;
  default_mode: string;
  effective_mode: string;
  overridden: boolean;
  effective_from: string | null;
  set_by: string | null;
  note: string;
  overridable: boolean;
  substantiation: number | null;
  wilson_lower: number | null;
  recommended_mode: string | null;
}

export interface AdminAuditRow {
  id: number;
  actor: string;
  action: string;
  target: string;
  detail: Record<string, unknown>;
  at: string | null;
}

// ── Coding intelligence (/api/coding) ────────────────────────────────────────
export interface CodeAgg {
  kind: string;
  code: string;
  n_lines: number;
  n_claims: number;
  n_providers: number;
  billed: number;
  payable: number;
  repricing_captured: number;
  over_reference_signal: number;
  uncovered_billed: number;
  uncovered_lines: number;
  top_src: string | null;
  legal_status: string | null;
  potential_saving?: number;
}

export interface ConditionBand {
  p25: number;
  p50: number;
  p75: number;
  p90: number;
  min: number;
  max: number;
}

export interface ConditionRow {
  injury_class: string;
  n: number;
  robust: boolean;
  bands: ConditionBand | null;
  by_intensity: Record<
    string,
    { n: number; robust: boolean; bands: ConditionBand | null }
  >;
}

export interface CostEstimate {
  injury_class: string;
  n: number;
  robust: boolean;
  classification: string; // BELOW_TYPICAL | TYPICAL | HIGH | OUTLIER | UNKNOWN
  amount: number;
  bands?: ConditionBand;
}

// ── Notifications (/api/notifications) ───────────────────────────────────────
export type NotifChannel = "SMS" | "EMAIL" | "NONE";

export interface Notification {
  id: number;
  claim_id: string;
  party_token: string | null;
  channel: string;
  event: string;
  body: string;
  status: string; // PENDING | SENT | FAILED | SUPPRESSED
  created_at: string | null;
  sent_at: string | null;
}

export interface NotifPref {
  party_token: string;
  channel: string;
  opted_in: boolean;
}

// ── Comparable awards (/api/reference/awards) ────────────────────────────────
export interface AwardAuthority {
  citation: string;
  court: string;
  severity_tier: string;
  award_year: number;
  award_rand: number;
  adjusted: number;
  notes: string;
}

export interface AwardBand {
  injury_class: string;
  severity_tier: string | null;
  n: number;
  robust: boolean;
  current_year: number;
  awards: AwardAuthority[];
  band_min?: number;
  band_max?: number;
  band_p25?: number;
  band_median?: number;
  band_p75?: number;
}

export interface AwardClass {
  injury_class: string;
  severity_tiers: string[];
}
