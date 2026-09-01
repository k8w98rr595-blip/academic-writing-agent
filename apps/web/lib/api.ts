import type { PaperDocument } from "./types";

const SESSION_KEY = "paperlight.session.v1";

export class ApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly code = "") {
    super(message);
    this.name = "ApiError";
  }
}

export function isQuotaError(cause: unknown): boolean {
  return cause instanceof ApiError
    && cause.status === 402
    && ["quota_exceeded", "entitlement_required"].includes(cause.code);
}

export function withIdempotency(options: RequestInit = {}, key = globalThis.crypto.randomUUID()): RequestInit {
  const headers = new Headers(options.headers);
  headers.set("Idempotency-Key", key);
  return { ...options, headers };
}

function apiBase(): string {
  if (typeof window === "undefined") return "http://127.0.0.1:8000";
  return (window.PAPERLIGHT_CONFIG?.apiBaseUrl || "http://127.0.0.1:8000").replace(/\/$/, "");
}

export function sessionToken(): string {
  return typeof window === "undefined" ? "" : sessionStorage.getItem(SESSION_KEY) || "";
}

export function storeSession(token: string): void {
  sessionStorage.setItem(SESSION_KEY, token);
}

export function clearSession(): void {
  sessionStorage.removeItem(SESSION_KEY);
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = sessionToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${apiBase()}${path}`, { ...options, headers, cache: "no-store" });
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    if (response.status === 401) clearSession();
    const detail = typeof payload === "object" && payload ? payload.detail : null;
    const message = typeof detail === "object" && detail?.message
      ? String(detail.message)
      : typeof detail === "string"
        ? detail
        : `Request failed (${response.status})`;
    const code = typeof detail === "object" && detail?.code ? String(detail.code) : "";
    throw new ApiError(message, response.status, code);
  }
  return payload as T;
}

export async function fetchDocument(documentId: string): Promise<PaperDocument> {
  const payload = await api<{ document: PaperDocument }>(`/api/v1/documents/${documentId}`);
  return payload.document;
}

export async function downloadExport(document: PaperDocument): Promise<void> {
  const token = sessionToken();
  const response = await fetch(`${apiBase()}/api/v1/documents/${document.id}/exports`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("Export failed");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = window.document.createElement("a");
  link.href = url;
  link.download = `${document.title.replace(/[^A-Za-z0-9_-]+/g, "-") || "paperlight"}.docx`;
  link.click();
  URL.revokeObjectURL(url);
}
