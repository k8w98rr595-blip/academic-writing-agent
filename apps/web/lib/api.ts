import type { PaperDocument } from "./types";

const SESSION_KEY = "paperlight.session.v1";

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
    throw new Error(typeof payload === "object" && payload?.detail ? String(payload.detail) : `Request failed (${response.status})`);
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
