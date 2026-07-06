import { describe, expect, it } from "vitest";
import type { AvailabilityResult, SslResult } from "./api";
import { buildAvailabilityAdvice, buildSslAdvice } from "./advice";

function availabilityResult(overrides: Partial<AvailabilityResult> = {}): AvailabilityResult {
  return {
    service_url: "https://example.com",
    final_url: "https://example.com/",
    is_available: true,
    status_code: 200,
    response_time_ms: 500,
    redirect_count: 0,
    uses_https: true,
    timed_out: false,
    failure_reason: null,
    created_at: "2026-07-06T00:00:00Z",
    updated_at: "2026-07-06T00:00:00Z",
    ...overrides
  };
}

function sslResult(overrides: Partial<SslResult> = {}): SslResult {
  return {
    service_url: "https://example.com",
    is_applicable: true,
    is_valid: true,
    expires_at: "2026-10-04T00:00:00Z",
    days_until_expiration: 89,
    failure_reason: null,
    created_at: "2026-07-06T00:00:00Z",
    updated_at: "2026-07-06T00:00:00Z",
    ...overrides
  };
}

describe("buildAvailabilityAdvice", () => {
  it("returns no advice for a healthy result", () => {
    expect(buildAvailabilityAdvice(availabilityResult(), 1000)).toEqual([]);
  });

  it("flags response time over the project threshold with both values", () => {
    const advice = buildAvailabilityAdvice(availabilityResult({ response_time_ms: 1180 }), 1000);

    expect(advice).toHaveLength(1);
    expect(advice[0]).toContain("1180ms");
    expect(advice[0]).toContain("1000ms");
  });

  it("skips the threshold advice when the project threshold is unknown", () => {
    const advice = buildAvailabilityAdvice(availabilityResult({ response_time_ms: 5000 }), null);

    expect(advice).toEqual([]);
  });

  it("flags unavailable, timed out, redirect chains, and missing https together", () => {
    const advice = buildAvailabilityAdvice(
      availabilityResult({
        is_available: false,
        timed_out: true,
        redirect_count: 3,
        uses_https: false
      }),
      null
    );

    expect(advice).toHaveLength(4);
    expect(advice.some((item) => item.includes("리다이렉트가 3회"))).toBe(true);
  });

  it("does not flag a single redirect", () => {
    expect(buildAvailabilityAdvice(availabilityResult({ redirect_count: 1 }), null)).toEqual([]);
  });
});

describe("buildSslAdvice", () => {
  it("returns no advice for a valid certificate with plenty of time left", () => {
    expect(buildSslAdvice(sslResult())).toEqual([]);
  });

  it("returns nothing when ssl is not applicable", () => {
    expect(buildSslAdvice(sslResult({ is_applicable: false, is_valid: null }))).toEqual([]);
  });

  it("flags an invalid certificate", () => {
    const advice = buildSslAdvice(sslResult({ is_valid: false }));

    expect(advice).toHaveLength(1);
    expect(advice[0]).toContain("유효하지 않습니다");
  });

  it("flags a certificate expiring within 30 days", () => {
    const advice = buildSslAdvice(sslResult({ days_until_expiration: 12 }));

    expect(advice).toHaveLength(1);
    expect(advice[0]).toContain("12일");
  });
});
