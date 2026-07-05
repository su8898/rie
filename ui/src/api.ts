// Small typed fetch client for the RIE API. Every request is same-origin
// (Vite proxies /api and /healthz to the backend on :8021) and sends the
// session cookie via credentials:"include".

import type {
  Accident,
  AdminAuditRow,
  AdminUser,
  Attorney,
  AuditItem,
  AuditRoi,
  AuthUser,
  AwardBand,
  AwardClass,
  BatchDict,
  CaseAnalytics,
  CaseItem,
  CaseNote,
  ClaimDetail,
  Claimant,
  CodeAgg,
  ConditionRow,
  CostEstimate,
  Dashboard,
  Determination,
  DisputeAnalytics,
  DisputeItem,
  Fairness,
  Health,
  LabelRow,
  NegotiatedRate,
  Notification,
  NotifPref,
  Offer,
  OfferHeadsInput,
  PaymentSource,
  PrecisionRow,
  Provider,
  QueueRow,
  Reason,
  RecallEstimate,
  RecallSample,
  RiskSweep,
  SignalMode,
  StatutoryCap,
  SweepResult,
  TariffRate,
  Workflow,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      credentials: "include",
      headers:
        init?.body != null
          ? { "Content-Type": "application/json", ...(init?.headers ?? {}) }
          : init?.headers,
      ...init,
    });
  } catch (e) {
    // Network error / backend unreachable.
    throw new ApiError(0, `network error: ${(e as Error).message}`, null);
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const detail =
      data && typeof data === "object" && "detail" in data
        ? (data as { detail: unknown }).detail
        : data;
    throw new ApiError(res.status, detailToMessage(detail, res.status), detail);
  }
  return data as T;
}

function detailToMessage(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    try {
      return JSON.stringify(detail);
    } catch {
      /* ignore */
    }
  }
  return `request failed (${status})`;
}

export const api = {
  // — health —
  health: () => request<Health>("/healthz"),

  // — auth —
  me: () => request<AuthUser>("/api/auth/me"),
  login: (username: string, password: string) =>
    request<AuthUser>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  logout: () =>
    request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),

  // — claims —
  submitClaim: (payload: unknown) =>
    request<Determination>("/api/claims", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listClaims: (params: {
    band?: string;
    disposition?: string;
    limit?: number;
    offset?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.band) q.set("band", params.band);
    if (params.disposition) q.set("disposition", params.disposition);
    if (params.limit != null) q.set("limit", String(params.limit));
    if (params.offset != null) q.set("offset", String(params.offset));
    const qs = q.toString();
    return request<Determination[]>(`/api/claims${qs ? `?${qs}` : ""}`);
  },
  getClaim: (claimId: string) =>
    request<ClaimDetail>(`/api/claims/${encodeURIComponent(claimId)}`),

  // — reference —
  reasons: () => request<Reason[]>("/api/reasons"),
  // Distinct provider disciplines in the loaded tariff schedules (submit UI).
  disciplines: () => request<string[]>("/api/reference/disciplines"),
  // Per-discipline rate rows for a tariff code.
  tariffRates: (code: string) =>
    request<TariffRate[]>(
      `/api/reference/tariffs?code=${encodeURIComponent(code)}`,
    ),

  // — dashboard —
  dashboard: () => request<Dashboard>("/api/dashboard"),

  // — accidents —
  accidents: () => request<Accident[]>("/api/accidents"),
  getAccident: (id: string) =>
    request<Accident>(`/api/accidents/${encodeURIComponent(id)}`),

  // — operational workflow —
  // The one aggregation call for a claim's every state machine + offer.
  workflow: (claimId: string) =>
    request<Workflow>(
      `/api/claims/${encodeURIComponent(claimId)}/workflow`,
    ),

  // Lifecycle: POST /api/lifecycle/{claim_id}/{action}
  lifecycleAction: (claimId: string, action: string) =>
    post(`/api/lifecycle/${encodeURIComponent(claimId)}/${action}`),

  // Merits: POST /api/merits/{claim_id}/{action}
  //   accept -> {fault_pct}; reject|dismiss -> {ground}; appeal -> {}
  meritsAction: (
    claimId: string,
    action: string,
    body: { fault_pct?: number; ground?: string } = {},
  ) => post(`/api/merits/${encodeURIComponent(claimId)}/${action}`, body),

  // Offer: POST /api/offer/{claim_id} {heads_input}; GET latest.
  buildOffer: (claimId: string, headsInput: OfferHeadsInput) =>
    request<Offer>(`/api/offer/${encodeURIComponent(claimId)}`, {
      method: "POST",
      body: JSON.stringify({ heads_input: headsInput }),
    }),
  getOffer: (claimId: string) =>
    request<Offer>(`/api/offer/${encodeURIComponent(claimId)}`),

  // Serious injury (RAF 4): create (MEDICAL_OFFICER) + transition.
  createSeriousInjury: (body: {
    claim_id: string;
    list_match?: boolean;
    wpi?: number | null;
    narrative?: boolean;
  }) => post("/api/serious-injury", body),
  seriousInjuryAction: (siId: number, action: string) =>
    post(`/api/serious-injury/${siId}/${action}`),

  // Undertaking: create + state transition + invoice submit/adjudicate/transition.
  createUndertaking: (body: {
    claim_id: string;
    origin: "SETTLEMENT" | "EMERGENCY";
    scope_dx: string[];
  }) => post("/api/undertakings", body),
  undertakingAction: (uId: number, action: string) =>
    post(`/api/undertakings/${uId}/state/${action}`),
  submitInvoice: (uId: number, body: { billed: number; dx: string }) =>
    post(`/api/undertakings/${uId}/invoices`, body),
  adjudicateInvoice: (invId: number, approved: number) =>
    post(`/api/undertakings/invoices/${invId}/adjudicate`, { approved }),
  invoiceAction: (invId: number, action: string) =>
    post(`/api/undertakings/invoices/${invId}/state/${action}`),

  // Litigation: create (LEGAL) + transition.
  createLitigation: (claimId: string) =>
    post("/api/litigation", { claim_id: claimId }),
  litigationAction: (litId: number, action: string) =>
    post(`/api/litigation/${litId}/${action}`),

  // — payments (payment-batch layer) —
  paymentsQueue: () => request<QueueRow[]>("/api/payments/queue"),
  listBatches: () => request<BatchDict[]>("/api/payments/batches"),
  createBatch: (note?: string) =>
    request<BatchDict>("/api/payments/batches", {
      method: "POST",
      body: JSON.stringify(note ? { note } : {}),
    }),
  getBatch: (id: number) =>
    request<BatchDict>(`/api/payments/batches/${id}`),
  addInstruction: (
    id: number,
    body: { claim_id: string; source: PaymentSource; amount?: number },
  ) =>
    request<BatchDict>(`/api/payments/batches/${id}/instructions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  approveBatch: (id: number) =>
    request<BatchDict>(`/api/payments/batches/${id}/approve`, {
      method: "POST",
      body: "{}",
    }),
  payBatch: (id: number) =>
    request<BatchDict>(`/api/payments/batches/${id}/pay`, {
      method: "POST",
      body: "{}",
    }),
  cancelBatch: (id: number) =>
    request<BatchDict>(`/api/payments/batches/${id}/cancel`, {
      method: "POST",
      body: "{}",
    }),

  // — party intelligence —
  providers: () => request<Provider[]>("/api/parties/providers"),
  attorneys: () => request<Attorney[]>("/api/parties/attorneys"),
  claimants: () => request<Claimant[]>("/api/parties/claimants"),
  fairness: () => request<Fairness>("/api/parties/fairness"),
  riskSweep: (threshold: number) =>
    request<RiskSweep>(`/api/parties/risk-sweep?threshold=${threshold}`),

  // — audit / clawback recovery —
  auditItems: (status?: string) =>
    request<AuditItem[]>(
      `/api/audit${status ? `?status=${encodeURIComponent(status)}` : ""}`,
    ),
  auditRoi: () => request<AuditRoi>("/api/audit/roi"),
  auditSweep: (threshold: number) =>
    request<SweepResult>(`/api/audit/sweep?threshold=${threshold}`, {
      method: "POST",
      body: "{}",
    }),
  getAuditItem: (id: number) =>
    request<AuditItem>(`/api/audit/${id}`),
  auditAction: (
    id: number,
    action: string,
    body: { amount?: number; outcome?: string } = {},
  ) =>
    request<AuditItem>(`/api/audit/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // — cases (investigation / review case machine) —
  cases: (params: { lane?: string; status?: string; mine?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.lane) q.set("lane", params.lane);
    if (params.status) q.set("status", params.status);
    if (params.mine) q.set("mine", "true");
    const qs = q.toString();
    return request<CaseItem[]>(`/api/cases${qs ? `?${qs}` : ""}`);
  },
  openCase: (body: {
    lane: string;
    reason: string;
    claim_id?: string | null;
    priority?: number;
    rand_at_stake?: number;
  }) =>
    request<CaseItem>("/api/cases", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  caseAnalytics: () => request<CaseAnalytics>("/api/cases/analytics"),
  caseAction: (
    id: number,
    action: string,
    body: {
      verdict?: string;
      root_cause?: string;
      recovered?: number;
      prevented?: number;
    } = {},
  ) =>
    request<CaseItem>(`/api/cases/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  caseNotes: (id: number) => request<CaseNote[]>(`/api/cases/${id}/notes`),
  addCaseNote: (id: number, body: string) =>
    request<{ id: number }>(`/api/cases/${id}/notes`, {
      method: "POST",
      body: JSON.stringify({ body }),
    }),

  // — disputes (objection register) —
  disputes: (
    params: { subject?: string; status?: string; claim_id?: string } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.subject) q.set("subject", params.subject);
    if (params.status) q.set("status", params.status);
    if (params.claim_id) q.set("claim_id", params.claim_id);
    const qs = q.toString();
    return request<DisputeItem[]>(`/api/disputes${qs ? `?${qs}` : ""}`);
  },
  lodgeDispute: (body: {
    claim_id: string;
    subject: string;
    raised_by: string;
    grounds?: string;
  }) =>
    request<DisputeItem>("/api/disputes", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  disputeAnalytics: () => request<DisputeAnalytics>("/api/disputes/analytics"),
  disputeAction: (
    id: number,
    action: string,
    body: { outcome?: string; channel?: string; linked_ref?: string } = {},
  ) =>
    request<DisputeItem>(`/api/disputes/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // — governance (precision / recall / promotion lifecycle) —
  precision: () => request<PrecisionRow[]>("/api/governance/precision"),
  promotions: () => request<PrecisionRow[]>("/api/governance/promotions"),
  recall: () => request<RecallEstimate>("/api/governance/recall"),
  recallSample: (n: number) =>
    request<RecallSample>(`/api/governance/recall/sample?n=${n}`),
  labels: () => request<LabelRow[]>("/api/governance/labels"),

  // — admin (users / statutory config / signal-mode overrides / audit) —
  adminUsers: () => request<AdminUser[]>("/api/admin/users"),
  createUser: (body: { username: string; role: string; password: string }) =>
    request<AdminUser>("/api/admin/users", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  setUserRole: (username: string, role: string) =>
    request<AdminUser>(
      `/api/admin/users/${encodeURIComponent(username)}/role`,
      { method: "POST", body: JSON.stringify({ role }) },
    ),
  setUserActive: (username: string, active: boolean) =>
    request<AdminUser>(
      `/api/admin/users/${encodeURIComponent(username)}/active`,
      { method: "POST", body: JSON.stringify({ active }) },
    ),
  adminCaps: () => request<StatutoryCap[]>("/api/admin/caps"),
  upsertCap: (effective_from: string, annual_cap: number) =>
    request<StatutoryCap>("/api/admin/caps", {
      method: "POST",
      body: JSON.stringify({ effective_from, annual_cap }),
    }),
  adminNegotiated: () => request<NegotiatedRate[]>("/api/admin/negotiated"),
  upsertNegotiated: (body: { kind: string; code: string; rate: number }) =>
    request<NegotiatedRate>("/api/admin/negotiated", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  signalModes: () => request<SignalMode[]>("/api/admin/signal-modes"),
  setSignalMode: (body: { code: string; mode: string; note?: string }) =>
    request<{ signal: string; mode: string; effective_from: string }>(
      "/api/admin/signal-modes",
      { method: "POST", body: JSON.stringify(body) },
    ),
  clearSignalMode: (code: string) =>
    request<{ ok: boolean }>(
      `/api/admin/signal-modes/${encodeURIComponent(code)}`,
      { method: "DELETE" },
    ),
  adminAudit: () => request<AdminAuditRow[]>("/api/admin/audit"),

  // — coding intelligence (aggregation / negotiation targets / condition bands) —
  codingCodes: (kind?: string) =>
    request<CodeAgg[]>(
      `/api/coding/codes${kind ? `?kind=${encodeURIComponent(kind)}` : ""}`,
    ),
  negotiationTargets: () =>
    request<CodeAgg[]>("/api/coding/negotiation-targets"),
  conditions: () => request<ConditionRow[]>("/api/coding/conditions"),
  estimateCondition: (injuryClass: string, amount: number) =>
    request<CostEstimate>(
      `/api/coding/estimate?injury_class=${encodeURIComponent(injuryClass)}&amount=${amount}`,
    ),

  // — notifications (POPIA-minimal outbox + opt-in) —
  notifications: (params: { status?: string; claim_id?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.claim_id) q.set("claim_id", params.claim_id);
    const qs = q.toString();
    return request<Notification[]>(`/api/notifications${qs ? `?${qs}` : ""}`);
  },
  notifPref: (token: string) =>
    request<NotifPref>(
      `/api/notifications/prefs/${encodeURIComponent(token)}`,
    ),
  setNotifPref: (token: string, channel: string, opted_in: boolean) =>
    request<NotifPref>(
      `/api/notifications/prefs/${encodeURIComponent(token)}`,
      { method: "POST", body: JSON.stringify({ channel, opted_in }) },
    ),
  notifMarkSent: (id: number) =>
    request<Notification>(`/api/notifications/${id}/sent`, {
      method: "POST",
      body: "{}",
    }),
  notifMarkFailed: (id: number) =>
    request<Notification>(`/api/notifications/${id}/failed`, {
      method: "POST",
      body: "{}",
    }),

  // — comparable awards (general-damages quantum) —
  awardClasses: () => request<AwardClass[]>("/api/reference/awards/classes"),
  awardBand: (injuryClass: string, severity?: string) =>
    request<AwardBand>(
      `/api/reference/awards?injury_class=${encodeURIComponent(injuryClass)}${
        severity ? `&severity=${encodeURIComponent(severity)}` : ""
      }`,
    ),
};

// Thin POST helper for transition/create endpoints whose exact response body
// we don't consume (we always re-fetch /workflow on success). Errors still
// carry the 409/403 {detail} via ApiError.
function post(path: string, body?: unknown): Promise<unknown> {
  return request<unknown>(path, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });
}
