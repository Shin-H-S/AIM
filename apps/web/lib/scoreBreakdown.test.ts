import { describe, expect, it } from "vitest";
import type { ScoreBreakdown } from "./api";
import {
  buildBreakdownSummary,
  scoreCategoryLabel,
  scoreGateLabel,
  scoreReasonText
} from "./scoreBreakdown";

function breakdownFixture(overrides: Partial<ScoreBreakdown> = {}): ScoreBreakdown {
  return {
    version: 1,
    categories: [
      { key: "availability", weight: 25, score: 100, reasons: [{ code: "all_checks_passed" }] },
      {
        key: "functional_stability",
        weight: 30,
        score: null,
        reasons: [{ code: "no_scenario_runs" }]
      },
      { key: "web_performance", weight: 20, score: 0, reasons: [{ code: "lighthouse_failed" }] },
      { key: "accessibility", weight: 10, score: 0, reasons: [{ code: "lighthouse_failed" }] },
      {
        key: "seo_basic_quality",
        weight: 5,
        score: 0,
        reasons: [{ code: "lighthouse_failed" }]
      },
      {
        key: "regression_stability",
        weight: 10,
        score: null,
        reasons: [{ code: "not_implemented" }]
      }
    ],
    gate: {
      code: "lighthouse_failed",
      deployment_risk: "RISK",
      grade_cap: "D",
      detail: "Lighthouse CLI failed."
    },
    overall: { score: 42, evaluated_weight: 60, grade_before_gate: "F" },
    ...overrides
  };
}

describe("scoreReasonText", () => {
  it("describes availability deductions with values", () => {
    expect(
      scoreReasonText({
        code: "response_time_over_threshold",
        points: -20,
        value: 1500,
        threshold: 1000
      })
    ).toBe("응답 시간 1500ms이 임계값(1000ms)을 초과해 −20점");
  });

  it("describes scenario scoring counts", () => {
    expect(
      scoreReasonText({ code: "scenario_runs_scored", failed: 1, with_failed_steps: 0, clean: 2 })
    ).toBe("시나리오 실행 결과 반영 (실패 1 · step 실패 포함 0 · 성공 2)");
  });

  it("describes console error deductions", () => {
    expect(scoreReasonText({ code: "console_errors_deducted", errors: 2, points: 10 })).toBe(
      "브라우저 콘솔 에러 2건 — 실행 점수에서 10점 감점 (1건당 5점, 실행당 최대 20점)"
    );
  });

  it("falls back to the raw code for unknown reasons", () => {
    expect(scoreReasonText({ code: "mystery" })).toBe("mystery");
  });
});

describe("buildBreakdownSummary", () => {
  it("explains zeroed categories, exclusions, the overall score, and the gate", () => {
    const summary = buildBreakdownSummary(breakdownFixture());

    expect(summary).toContain("Lighthouse 검사가 실패해 웹 성능·접근성·SEO/기본 품질 항목이 0점 처리");
    expect(summary).toContain("기능 안정성·회귀 안정성 항목(40%)은 이번 평가에서 제외");
    expect(summary).toContain("평가된 60% 가중치 기준으로 종합 42점");
    expect(summary).toContain("등급이 최대 D로 제한");
  });

  it("omits the gate sentence when no gate fired", () => {
    const summary = buildBreakdownSummary(breakdownFixture({ gate: null }));

    expect(summary).not.toContain("등급이 최대");
  });
});

describe("labels", () => {
  it("maps category keys and gate codes to Korean labels", () => {
    expect(scoreCategoryLabel("web_performance")).toBe("웹 성능");
    expect(
      scoreGateLabel({
        code: "lighthouse_failed",
        deployment_risk: "RISK",
        grade_cap: "D",
        detail: null
      })
    ).toBe("Lighthouse 검사 실패");
  });
});
