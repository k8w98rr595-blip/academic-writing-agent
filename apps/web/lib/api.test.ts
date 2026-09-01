import { describe, expect, it } from "vitest";

import { ApiError, isQuotaError, withIdempotency } from "./api";

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
