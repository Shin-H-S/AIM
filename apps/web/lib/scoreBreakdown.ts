import type {
  ScoreBreakdown,
  ScoreBreakdownCategory,
  ScoreBreakdownGate,
  ScoreBreakdownReason
} from "./api";
import { formatMilliseconds } from "./format";

const categoryLabels: Record<string, string> = {
  availability: "가용성",
  functional_stability: "기능 안정성",
  web_performance: "웹 성능",
  accessibility: "접근성",
  seo_basic_quality: "SEO/기본 품질",
  regression_stability: "회귀 안정성"
};

const riskLabels: Record<string, string> = {
  STABLE: "안정",
  WARNING: "주의",
  RISK: "위험"
};

const gateLabels: Record<string, string> = {
  availability_missing: "가용성 검사 결과 없음",
  service_unavailable: "서비스 응답 실패",
  response_time_over_double_threshold: "응답 시간이 임계값의 2배 초과",
  ssl_invalid: "SSL 인증서 무효",
  scenario_failed: "핵심 시나리오 실패",
  lighthouse_failed: "Lighthouse 검사 실패",
  performance_below_threshold: "성능 점수가 품질 임계값 미만"
};

export function scoreCategoryLabel(key: string): string {
  return categoryLabels[key] ?? key;
}

export function scoreGateLabel(gate: ScoreBreakdownGate): string {
  return gateLabels[gate.code] ?? gate.detail ?? gate.code;
}

export function scoreReasonText(reason: ScoreBreakdownReason): string {
  switch (reason.code) {
    case "all_checks_passed":
      return "응답 성공, 모든 감점 항목 통과";
    case "service_unavailable":
      return "서비스가 응답하지 않아 0점 처리";
    case "not_collected":
      return "검사 결과가 수집되지 않아 평가 제외";
    case "no_https":
      return "HTTPS 미사용 −10점";
    case "redirect_chain":
      return `리다이렉트 ${reason.value ?? "다수"}회 −5점`;
    case "response_time_over_threshold":
      return `응답 시간 ${formatMilliseconds(reason.value ?? null)}이 임계값(${formatMilliseconds(
        reason.threshold ?? null
      )})을 초과해 −20점`;
    case "response_time_over_double_threshold":
      return `응답 시간 ${formatMilliseconds(reason.value ?? null)}이 임계값(${formatMilliseconds(
        reason.threshold ?? null
      )})의 2배를 초과해 −40점`;
    case "lighthouse_failed":
      return "Lighthouse 검사 실패로 0점 처리";
    case "lighthouse_score":
      return "Lighthouse 점수를 그대로 반영";
    case "score_not_reported":
      return "Lighthouse가 이 항목의 점수를 제공하지 않아 평가 제외";
    case "average_of_seo_and_best_practices":
      return `SEO ${reason.seo ?? "-"}점과 권장사항 ${reason.best_practices ?? "-"}점의 평균`;
    case "no_scenario_runs":
      return "연결된 시나리오가 없어 평가 제외 — 시나리오를 등록하면 이 항목이 점수에 반영됩니다";
    case "no_scored_scenario_runs":
      return "완료된 시나리오 실행이 없어 평가 제외";
    case "scenario_runs_scored":
      return `시나리오 실행 결과 반영 (실패 ${reason.failed ?? 0} · step 실패 포함 ${
        reason.with_failed_steps ?? 0
      } · 성공 ${reason.clean ?? 0})`;
    case "not_implemented":
      return "준비 중인 항목이라 평가 제외";
    default:
      return reason.code;
  }
}

function evaluatedCategories(breakdown: ScoreBreakdown): ScoreBreakdownCategory[] {
  return breakdown.categories.filter((category) => category.score !== null);
}

function excludedCategories(breakdown: ScoreBreakdown): ScoreBreakdownCategory[] {
  return breakdown.categories.filter((category) => category.score === null);
}

export function buildBreakdownSummary(breakdown: ScoreBreakdown): string {
  const sentences: string[] = [];

  const zeroCategories = evaluatedCategories(breakdown).filter(
    (category) => category.score === 0
  );
  if (zeroCategories.length > 0) {
    const allLighthouseFailures = zeroCategories.every((category) =>
      category.reasons.some((reason) => reason.code === "lighthouse_failed")
    );
    const labels = zeroCategories.map((category) => scoreCategoryLabel(category.key)).join("·");
    sentences.push(
      allLighthouseFailures
        ? `Lighthouse 검사가 실패해 ${labels} 항목이 0점 처리되었습니다.`
        : `${labels} 항목이 0점 처리되었습니다.`
    );
  }

  const excluded = excludedCategories(breakdown);
  if (excluded.length > 0) {
    const labels = excluded.map((category) => scoreCategoryLabel(category.key)).join("·");
    const excludedWeight = excluded.reduce((total, category) => total + category.weight, 0);
    sentences.push(`${labels} 항목(${excludedWeight}%)은 이번 평가에서 제외되었습니다.`);
  }

  sentences.push(
    `평가된 ${breakdown.overall.evaluated_weight}% 가중치 기준으로 종합 ${breakdown.overall.score}점입니다.`
  );

  if (breakdown.gate) {
    sentences.push(
      `${scoreGateLabel(breakdown.gate)}로 위험도 '${
        riskLabels[breakdown.gate.deployment_risk] ?? breakdown.gate.deployment_risk
      }'가 적용되고 등급이 최대 ${breakdown.gate.grade_cap}로 제한되었습니다.`
    );
  }

  return sentences.join(" ");
}
