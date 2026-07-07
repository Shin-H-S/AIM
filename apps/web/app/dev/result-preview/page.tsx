"use client";

import { useEffect, useState } from "react";
import {
  AIReportSummaryCard,
  AvailabilityCard,
  LighthouseCard,
  ScoreCard
} from "@/app/projects/[projectId]/check-runs/[checkRunId]/ResultPageClient";
import type {
  AIReportDetail,
  AIReportDetailResult,
  AIReportSummary,
  AvailabilityResult,
  LighthouseResult,
  LighthouseTopAudit,
  ScoreResult
} from "@/lib/api";

const DEMO_TIMESTAMP = "2026-07-07T10:00:00Z";

const topAudits: LighthouseTopAudit[] = [
  {
    id: "render-blocking-resources",
    category: "performance",
    title: "렌더링 차단 리소스 제거하기",
    display_value: "잠재적 절감치: 1,860ms",
    score: 0.4,
    savings_ms: 1860,
    savings_bytes: 120000
  },
  {
    id: "uses-optimized-images",
    category: "performance",
    title: "이미지를 효율적으로 인코딩하기",
    display_value: null,
    score: 0.5,
    savings_ms: 900,
    savings_bytes: 250000
  }
];

const scoreResult: ScoreResult = {
  availability_score: 100,
  functional_stability_score: null,
  web_performance_score: 0,
  accessibility_score: 0,
  seo_basic_quality_score: 0,
  regression_stability_score: null,
  overall_score: 42,
  evaluated_weight: 60,
  grade: "F",
  deployment_risk: "RISK",
  gate_reason: "Lighthouse CLI failed.",
  score_breakdown: {
    version: 1,
    categories: [
      {
        key: "availability",
        weight: 25,
        score: 100,
        reasons: [{ code: "all_checks_passed" }]
      },
      {
        key: "functional_stability",
        weight: 30,
        score: null,
        reasons: [{ code: "no_scenario_runs" }]
      },
      {
        key: "web_performance",
        weight: 20,
        score: 0,
        reasons: [{ code: "lighthouse_failed" }]
      },
      {
        key: "accessibility",
        weight: 10,
        score: 0,
        reasons: [{ code: "lighthouse_failed" }]
      },
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
    overall: { score: 42, evaluated_weight: 60, grade_before_gate: "F" }
  },
  scoring_version: "2026-06-28.scenario-v1",
  created_at: DEMO_TIMESTAMP,
  updated_at: DEMO_TIMESTAMP
};

const availabilityResult: AvailabilityResult = {
  service_url: "https://example.com/",
  final_url: "https://example.com/",
  is_available: true,
  status_code: 200,
  response_time_ms: 1365,
  redirect_count: 1,
  uses_https: true,
  timed_out: false,
  failure_reason: null,
  created_at: DEMO_TIMESTAMP,
  updated_at: DEMO_TIMESTAMP
};

const lighthouseResult: LighthouseResult = {
  service_url: "https://example.com/",
  is_successful: true,
  performance_score: 45,
  accessibility_score: 90,
  seo_score: 88,
  best_practices_score: 92,
  largest_contentful_paint_ms: 4200,
  cumulative_layout_shift: 0.2,
  total_blocking_time_ms: 600,
  top_audits: topAudits,
  raw_json_artifact_id: null,
  failure_reason: null,
  created_at: DEMO_TIMESTAMP,
  updated_at: DEMO_TIMESTAMP
};

const aiReportSummary: AIReportSummary = {
  id: "demo-report",
  check_run_id: "demo-check-run",
  summary:
    "이 검사는 위험 등급 F(42/100)입니다. Lighthouse 검사 실패가 점수 하락의 가장 큰 원인이며, 성능 개선 기회 2건과 응답 시간 회귀가 함께 확인되었습니다.",
  overall_score: 42,
  grade: "F",
  deployment_risk: "RISK",
  gate_reason: "Lighthouse CLI failed.",
  generated_at: DEMO_TIMESTAMP,
  created_at: DEMO_TIMESTAMP,
  updated_at: DEMO_TIMESTAMP
};

const aiReportDetail: AIReportDetail = {
  ...aiReportSummary,
  schema_version: "2026-06-30.ai-diagnosis-report.v1",
  input_schema_version: "2026-06-29.ai-diagnosis-input.v1",
  report_json: {
    schema_version: "2026-06-30.ai-diagnosis-report.v1",
    input_schema_version: "2026-06-29.ai-diagnosis-input.v1",
    project_id: "demo-project",
    check_run_id: "demo-check-run",
    generated_at: DEMO_TIMESTAMP,
    summary: aiReportSummary.summary,
    score: {
      overall_score: 42,
      grade: "F",
      deployment_risk: "RISK",
      gate_reason: "Lighthouse CLI failed.",
      evidence_ids: ["score-result"]
    },
    top_issues: [
      {
        id: "lighthouse-improvement-opportunities",
        priority: 1,
        title:
          "Lighthouse found improvement opportunities: 렌더링 차단 리소스 제거하기, 이미지를 효율적으로 인코딩하기",
        statement_type: "confirmed_observation",
        severity: "warning",
        category: "web_quality",
        summary:
          "Lighthouse found improvement opportunities: 렌더링 차단 리소스 제거하기, 이미지를 효율적으로 인코딩하기.",
        evidence_ids: [
          "lighthouse-result",
          "lighthouse-audit-render-blocking-resources",
          "lighthouse-audit-uses-optimized-images"
        ],
        expected_user_impact:
          "메인 페이지 로딩이 느려 방문자가 콘텐츠를 보기까지 오래 기다립니다. 특히 모바일 환경에서 이탈 가능성이 높습니다.",
        recommended_next_action:
          "render-blocking-resources 항목부터 처리하세요. 차단 스크립트에 defer를 적용하면 약 1.9초 단축이 예상되고, 이미지 인코딩을 최적화하면 0.9초를 더 줄일 수 있습니다.",
        unknown_reason: null
      },
      {
        id: "availability-response-time-threshold",
        priority: 2,
        title: "Response time exceeded the configured project threshold",
        statement_type: "confirmed_observation",
        severity: "warning",
        category: "availability",
        summary: "Response time exceeded the configured project threshold.",
        evidence_ids: ["availability-result"],
        expected_user_impact: "첫 응답이 느려 페이지 진입 체감 속도가 떨어집니다.",
        recommended_next_action:
          "서버 처리 시간(TTFB)과 DB 쿼리를 먼저 점검하고, CDN·응답 캐시 적용을 검토하세요.",
        unknown_reason: null
      }
    ],
    improved_areas: [],
    regressed_areas: [
      {
        id: "response_time_ms-regressed",
        category: "regression",
        summary: "Response time regressed by 365 ms compared with the baseline.",
        evidence_ids: ["run-comparison"],
        metric_name: "response_time_ms",
        previous_value: null,
        current_value: null,
        delta: 365
      }
    ],
    generation_warnings: []
  }
};

const aiReportDetailResult: AIReportDetailResult = {
  state: "success",
  report: aiReportDetail
};

// 배포 전 UI 검수용 갤러리: 결과 페이지의 실제 컴포넌트를 예시 데이터로 렌더링한다.
// 타임스탬프 포맷이 서버/브라우저 ICU 버전에 따라 달라 hydration mismatch가 나므로
// 마운트 후에만 렌더링한다(클라이언트 전용 dev 페이지).
export default function ResultPreviewPage() {
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    queueMicrotask(() => setIsMounted(true));
  }, []);

  if (!isMounted) {
    return null;
  }

  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <p className="rounded-2xl border border-dashed border-slate-300 bg-white/60 p-4 text-sm text-slate-500">
          개발용 미리보기 — 결과 페이지의 실제 컴포넌트를 예시 데이터로 렌더링합니다. 실제
          검사 데이터와 무관합니다.
        </p>

        <ScoreCard result={scoreResult} />

        <LighthouseCard result={lighthouseResult} />

        <AvailabilityCard responseTimeThresholdMs={1000} result={availabilityResult} />

        <AIReportSummaryCard
          detailResult={aiReportDetailResult}
          isLoadingDetail={false}
          onLoadDetail={() => undefined}
          report={aiReportSummary}
          topAudits={topAudits}
        />
      </section>
    </main>
  );
}
