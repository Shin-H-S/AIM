import { describe, expect, it } from "vitest";
import type { CheckRunSummary } from "./api";
import { buildScoreTrendSeries, formatTrendLabel, scoredRunCount } from "./scoreTrend";

function checkRunFixture(overrides: Partial<CheckRunSummary>): CheckRunSummary {
  return {
    id: "run",
    project_id: "project",
    requested_by_id: "user",
    status: "COMPLETED",
    trigger_source: "manual",
    failure_reason: null,
    queued_at: "2026-07-01T09:00:00Z",
    started_at: null,
    finished_at: null,
    created_at: "2026-07-01T09:00:00Z",
    updated_at: "2026-07-01T09:00:00Z",
    ...overrides
  };
}

// 목록 API는 최신순으로 내려온다.
const checkRuns: CheckRunSummary[] = [
  checkRunFixture({
    id: "latest",
    queued_at: "2026-07-03T09:00:00Z",
    score: {
      overall_score: 90,
      grade: "A",
      deployment_risk: "STABLE",
      availability_score: 100,
      functional_stability_score: null,
      web_performance_score: 85,
      accessibility_score: 95,
      seo_basic_quality_score: 90
    }
  }),
  checkRunFixture({ id: "failed-run", queued_at: "2026-07-02T09:00:00Z", score: null }),
  checkRunFixture({
    id: "oldest",
    queued_at: "2026-07-01T09:00:00Z",
    score: {
      overall_score: 60,
      grade: "D",
      deployment_risk: "WARNING",
      availability_score: 80,
      functional_stability_score: null,
      web_performance_score: 40,
      accessibility_score: 70,
      seo_basic_quality_score: 65
    }
  })
];

describe("buildScoreTrendSeries", () => {
  it("orders points oldest first and skips runs without scores", () => {
    const series = buildScoreTrendSeries(checkRuns);
    const overall = series.find((entry) => entry.key === "overall");

    expect(overall?.points.map((point) => point.score)).toEqual([60, 90]);
    expect(overall?.points[0].label).toBe(formatTrendLabel("2026-07-01T09:00:00Z"));
  });

  it("skips categories whose values are missing", () => {
    const series = buildScoreTrendSeries(checkRuns);
    const functional = series.find((entry) => entry.key === "functional_stability");
    const availability = series.find((entry) => entry.key === "availability");

    expect(functional?.points).toEqual([]);
    expect(availability?.points.map((point) => point.score)).toEqual([80, 100]);
  });

  it("handles score summaries without category fields (older API)", () => {
    const series = buildScoreTrendSeries([
      checkRunFixture({
        id: "old-api",
        score: { overall_score: 70, grade: "C", deployment_risk: "WARNING" }
      })
    ]);

    expect(series.find((entry) => entry.key === "overall")?.points).toHaveLength(1);
    expect(series.find((entry) => entry.key === "availability")?.points).toEqual([]);
  });
});

describe("scoredRunCount", () => {
  it("counts overall points", () => {
    expect(scoredRunCount(buildScoreTrendSeries(checkRuns))).toBe(2);
    expect(scoredRunCount(buildScoreTrendSeries([]))).toBe(0);
  });
});
