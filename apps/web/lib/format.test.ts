import { describe, expect, it } from "vitest";
import { formatDuration, formatRelativeTime } from "./format";

describe("formatDuration", () => {
  it("formats sub-minute durations in seconds", () => {
    expect(formatDuration("2026-07-10T00:00:00Z", "2026-07-10T00:00:58Z")).toBe("58초");
  });

  it("formats durations with minutes and seconds", () => {
    expect(formatDuration("2026-07-10T00:00:00Z", "2026-07-10T00:01:02Z")).toBe("1분 2초");
  });

  it("returns a placeholder when the run has not finished", () => {
    expect(formatDuration("2026-07-10T00:00:00Z", null)).toBe("—");
    expect(formatDuration(null, null)).toBe("—");
  });

  it("returns a placeholder when timestamps are inverted", () => {
    expect(formatDuration("2026-07-10T00:01:00Z", "2026-07-10T00:00:00Z")).toBe("—");
  });
});

describe("formatRelativeTime", () => {
  const now = new Date("2026-07-10T12:00:00Z");

  it("formats recent moments", () => {
    expect(formatRelativeTime("2026-07-10T11:59:40Z", now)).toBe("방금 전");
    expect(formatRelativeTime("2026-07-10T11:46:00Z", now)).toBe("14분 전");
  });

  it("formats hours and days", () => {
    expect(formatRelativeTime("2026-07-10T09:00:00Z", now)).toBe("3시간 전");
    expect(formatRelativeTime("2026-07-09T08:00:00Z", now)).toBe("어제");
    expect(formatRelativeTime("2026-07-07T08:00:00Z", now)).toBe("3일 전");
  });

  it("falls back to an absolute date after a week", () => {
    expect(formatRelativeTime("2026-06-01T08:00:00Z", now)).toContain("2026");
  });
});
