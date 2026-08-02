import { describe, expect, it } from "vitest";
import { parseStructuredSummary } from "./aiSummary";

describe("parseStructuredSummary", () => {
  it("parses the three-line contract into labeled sections", () => {
    const parsed = parseStructuredSummary(
      "결론: 배포 위험도 RISK · 등급 F · 12/100.\n원인: SSL 인증서가 유효하지 않습니다.\n조치: 인증서를 갱신하세요."
    );

    expect(parsed).toEqual({
      verdict: "배포 위험도 RISK · 등급 F · 12/100.",
      cause: "SSL 인증서가 유효하지 않습니다.",
      action: "인증서를 갱신하세요."
    });
  });

  it("tolerates surrounding whitespace and blank lines", () => {
    const parsed = parseStructuredSummary("결론: A.\n\n  원인: B.  \n조치: C.\n");

    expect(parsed).toEqual({ verdict: "A.", cause: "B.", action: "C." });
  });

  it("falls back to prose for legacy single-paragraph summaries", () => {
    expect(
      parseStructuredSummary("이 검사는 배포 위험도 STABLE로 판정되었습니다. 주요 이슈는 없습니다.")
    ).toBeNull();
  });

  it("rejects out-of-order or incomplete labels — half-parsed output is worse than prose", () => {
    expect(parseStructuredSummary("원인: B.\n결론: A.\n조치: C.")).toBeNull();
    expect(parseStructuredSummary("결론: A.\n원인: B.")).toBeNull();
    expect(parseStructuredSummary("결론:\n원인: B.\n조치: C.")).toBeNull();
  });
});
