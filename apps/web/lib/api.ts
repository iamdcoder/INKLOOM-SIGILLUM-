export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api/v1";

export type SessionUser = { id: string; email: string; display_name: string; role: string };
export type Finding = {
  id: string; code: string; category: string; severity: string; verdict: string;
  title: string; explanation: string; reason_code: string; evidence_sufficiency: string;
  confidence: number; extraction_confidence: number; content_start: number | null;
  content_end: number | null; content_quote: string | null; region: Record<string, unknown> | null;
  evidence: Array<Record<string, unknown>>; status: string; resolution_note?: string | null;
  suggestions?: string[];
};
export type ReviewPayload = {
  submission: { id: string; title: string; status: string; channel: string; locale: string;
    geography: string; audience: string; offer_id: string | null; publication_at: string };
  content_version: { id: string; version_number: number; filename: string; mime_type: string;
    sha256: string; size_bytes: number; text: string; extraction_confidence: number;
    extraction_status: string; warnings: string[]; regions: Array<Record<string, unknown>> };
  review: { id: string; status: string; content_hash: string; brand_pack_version: string;
    knowledge_pack_hash: string; analysis_config_version: string; created_at: string };
  findings: Finding[];
  decisions: Array<{ id: string; action: string; reason: string | null; content_hash: string; reviewer_id: string; created_at: string }>;
};

export type VersionHistoryItem = {
  version_id: string;
  version_number: number;
  filename: string;
  sha256: string;
  created_at: string;
  extraction_status: string;
  review_id: string | null;
  review_status: string;
  brand_pack_version?: string;
  knowledge_pack_hash?: string;
  analysis_config_version?: string;
  finding_count: number;
  decisions: Array<{ action: string; reason: string | null; content_hash: string; created_at: string }>;
};

export function getToken() {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem("sigillum_token");
}
export function getUser(): SessionUser | null {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem("sigillum_user");
  try { return raw ? JSON.parse(raw) as SessionUser : null; } catch { return null; }
}
export function saveSession(token: string, user: SessionUser) {
  sessionStorage.setItem("sigillum_token", token);
  sessionStorage.setItem("sigillum_user", JSON.stringify(user));
}
export function clearSession() {
  sessionStorage.removeItem("sigillum_token");
  sessionStorage.removeItem("sigillum_user");
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !(init.body instanceof URLSearchParams) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (init.body instanceof URLSearchParams && !headers.has("Content-Type")) headers.set("Content-Type", "application/x-www-form-urlencoded;charset=UTF-8");
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data?.detail;
    const message = typeof detail === "string" ? detail : detail?.message || data?.message || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data as T;
}
