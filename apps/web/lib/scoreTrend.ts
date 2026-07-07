import type { CheckRunScoreSummary, CheckRunSummary } from "./api";
import type { ScoreTrendSeries } from "@/components/charts";

const trendSeriesDefs: {
  key: string;
  label: string;
  pick: (score: CheckRunScoreSummary) => number | null | undefined;
}[] = [
  { key: "overall", label: "종합", pick: (score) => score.overall_score },
  { key: "availability", label: "가용성", pick: (score) => score.availability_score },
  {
    key: "functional_stability",
    label: "기능 안정성",
    pick: (score) => score.functional_stability_score
  },
  { key: "web_performance", label: "웹 성능", pick: (score) => score.web_performance_score },
  { key: "accessibility", label: "접근성", pick: (score) => score.accessibility_score },
  {
    key: "seo_basic_quality",
    label: "SEO/기본 품질",
    pick: (score) => score.seo_basic_quality_score
  }
];

export function formatTrendLabel(value: string): string {
  const date = new Date(value);
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${date.getMonth() + 1}/${date.getDate()} ${hours}:${minutes}`;
}

// 최신순으로 내려오는 CheckRun 목록을 오래된 순 추이 시리즈로 변환한다.
// 점수가 없는 실행과 값이 비어 있는 카테고리는 건너뛴다.
export function buildScoreTrendSeries(checkRuns: CheckRunSummary[]): ScoreTrendSeries[] {
  const oldestFirst = [...checkRuns].reverse();

  return trendSeriesDefs.map((def) => ({
    key: def.key,
    label: def.label,
    points: oldestFirst.flatMap((checkRun) => {
      const value = checkRun.score ? def.pick(checkRun.score) : null;
      return value === null || value === undefined
        ? []
        : [{ label: formatTrendLabel(checkRun.queued_at), score: value }];
    })
  }));
}

// 카드 렌더링 여부 판단용 — 종합 점수가 2개 이상일 때만 추이가 의미 있다.
export function scoredRunCount(series: ScoreTrendSeries[]): number {
  return series[0]?.points.length ?? 0;
}
