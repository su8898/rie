// Small typed fetch client for the RIE API. Every request is same-origin
// (Vite proxies /api and /healthz to the backend on :8021) and sends the
// session cookie via credentials:"include".

import type {
  Accident,
  AuthUser,
  ClaimDetail,
  Dashboard,
  Determination,
  Health,
  Reason,
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

  // — dashboard —
  dashboard: () => request<Dashboard>("/api/dashboard"),

  // — accidents —
  accidents: () => request<Accident[]>("/api/accidents"),
  getAccident: (id: string) =>
    request<Accident>(`/api/accidents/${encodeURIComponent(id)}`),
};
