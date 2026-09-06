import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, downloadExport, isQuotaError, withIdempotency } from "./api";
import type { PaperDocument } from "./types";

afterEach(() => vi.unstubAllGlobals());

describe("version-bound Word export", () => {
  it("sends the displayed saved version and refuses a stale export", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("", { status: 409 }));
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("sessionStorage", { getItem: () => null });
    vi.stubGlobal("window", { PAPERLIGHT_CONFIG: { apiBaseUrl: "http://127.0.0.1:8100" } });
    await expect(downloadExport({ id: "doc_test", currentVersion: { id: "version_test" } } as PaperDocument)).rejects.toThrow("文稿版本已变化");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ expected_version_id: "version_test" });
  });
});

describe("local staging isolation", () => {
  it("refuses a production API before issuing any request", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("sessionStorage", { getItem: () => null });
    vi.stubGlobal("window", { PAPERLIGHT_CONFIG: {
      environment: "local-staging", apiBaseUrl: "https://production.invalid", basePath: "/academic-writing-agent",
    } });
    await expect(api("/api/health")).rejects.toThrow("非隔离 API");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("uses only the dedicated loopback API for staging", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetch);
    vi.stubGlobal("sessionStorage", { getItem: () => null });
    vi.stubGlobal("window", { PAPERLIGHT_CONFIG: {
      environment: "local-staging", apiBaseUrl: "http://127.0.0.1:8100", basePath: "/academic-writing-agent",
    } });
    await expect(api("/api/health")).resolves.toEqual({ ok: true });
    expect(fetch.mock.calls[0][0]).toBe("http://127.0.0.1:8100/api/health");
  });
});

describe("paid product request boundaries", () => {
  it("adds a fresh opaque idempotency key without dropping existing headers", () => {
    const first = withIdempotency({
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const second = withIdempotency({ method: "POST" });
    const firstHeaders = new Headers(first.headers);
    const secondHeaders = new Headers(second.headers);

    expect(first.method).toBe("POST");
    expect(firstHeaders.get("Content-Type")).toBe("application/json");
    expect(firstHeaders.get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
    expect(secondHeaders.get("Idempotency-Key")).not.toBe(firstHeaders.get("Idempotency-Key"));
  });

  it("preserves a supplied key for an uncertain network retry", () => {
    const key = "logical-operation-0001";
    const request = withIdempotency({ method: "POST" }, key);
    expect(new Headers(request.headers).get("Idempotency-Key")).toBe(key);
  });

  it("only classifies quota and entitlement payment boundaries as quota errors", () => {
    expect(isQuotaError(new ApiError("limit", 402, "quota_exceeded"))).toBe(true);
    expect(isQuotaError(new ApiError("plan", 402, "entitlement_required"))).toBe(true);
    expect(isQuotaError(new ApiError("provider", 402, "provider_balance"))).toBe(false);
    expect(isQuotaError(new ApiError("server", 500))).toBe(false);
  });
});
