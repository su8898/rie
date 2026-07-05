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
