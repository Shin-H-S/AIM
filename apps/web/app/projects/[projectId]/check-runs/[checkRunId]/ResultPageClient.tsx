"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArtifactDownloadButton } from "@/components/ArtifactDownloadButton";
import {
  fetchCheckRunDetail,
  getApiBaseUrl,
  type AIReportSummary,
  type Artifact,
  type AvailabilityResult,
  type CheckRunDetail,
  type CheckRunDetailResult,
  type CheckRunStatus,
  type LighthouseResult,
  type RunComparison,
  type ScoreResult,
  type ScenarioRun,
  type ScenarioRunStatus,
  type SslResult
} from "@/lib/api";

const POLLING_INTERVAL_MS = 3_000;
const ACTIVE_STATUSES = new Set<CheckRunStatus>(["QUEUED", "RUNNING", "ANALYZING"]);

const statusLabels: Record<CheckRunStatus, string> = {
  QUEUED: "대기 중",
  RUNNING: "실행 중",
  ANALYZING: "분석 중",
  COMPLETED: "완료",
  FAILED: "실패",
  CANCELLED: "취소됨"
};

const scenarioRunStatusLabels: Record<ScenarioRunStatus, string> = {
  QUEUED: "대기 중",
  RUNNING: "실행 중",
  COMPLETED: "완료",
  FAILED: "실패",
  CANCELLED: "취소됨"
};

const riskLabels: Record<ScoreResult["deployment_risk"], string> = {
  STABLE: "안정",
  WARNING: "주의",
  RISK: "위험"
};

export function ResultPageClient({
  projectId,
  checkRunId
}: {
  projectId: string;
  checkRunId: string;
}) {
  const [accessToken, setAccessToken] = useState("");
  const [result, setResult] = useState<CheckRunDetailResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const trimmedToken = accessToken.trim();
  const checkRun = result?.state === "success" ? result.checkRun : null;
  const shouldPoll = checkRun ? ACTIVE_STATUSES.has(checkRun.status) : false;

  const refresh = useCallback(async () => {
    if (!trimmedToken) {
      setResult(null);
      return;
    }

    setIsLoading(true);
    const nextResult = await fetchCheckRunDetail({
      projectId,
      checkRunId,
      accessToken: trimmedToken
    });
    setResult(nextResult);
    setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
    setIsLoading(false);
  }, [checkRunId, projectId, trimmedToken]);

  useEffect(() => {
    if (!shouldPoll || !trimmedToken) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refresh();
    }, POLLING_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [refresh, shouldPoll, trimmedToken]);

  const apiBaseUrlLabel = useMemo(() => {
    try {
      return getApiBaseUrl();
    } catch {
      return "잘못된 NEXT_PUBLIC_API_URL";
    }
  }, []);

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <header className="flex flex-col gap-6 rounded-3xl border border-white/10 bg-white/[0.03] p-6">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.28em] text-cyan-300">
              AIM Scan Result
            </p>
            <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
              CheckRun 결과
            </h1>
            <p className="mt-4 text-sm leading-6 text-slate-300">
              이 화면은 <code className="text-cyan-200">{apiBaseUrlLabel}</code>의 CheckRun 단건
              API를 polling해서 상태와 저장된 scanner result를 보여줍니다.
            </p>
          </div>

          <div className="grid gap-3 text-sm text-slate-300 sm:grid-cols-2">
            <Identifier label="Project ID" value={projectId} />
            <Identifier label="CheckRun ID" value={checkRunId} />
          </div>

          <form
            className="grid gap-3 md:grid-cols-[1fr_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              void refresh();
            }}
          >
            <label className="flex flex-col gap-2 text-sm">
              <span className="font-medium text-slate-200">Bearer token</span>
              <input
                className="rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none ring-cyan-400/0 transition focus:border-cyan-300 focus:ring-4 focus:ring-cyan-400/10"
                type="password"
                value={accessToken}
                placeholder="로그인 API에서 받은 access_token을 입력하세요"
                onChange={(event) => setAccessToken(event.target.value)}
              />
            </label>
            <button
              className="self-end rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
              type="submit"
              disabled={!trimmedToken || isLoading}
            >
              {isLoading ? "조회 중" : "결과 조회"}
            </button>
          </form>
        </header>

        {!trimmedToken && (
          <Notice
            tone="info"
            title="인증 토큰이 필요합니다"
            description="현재 웹에는 로그인 UI가 없으므로, API 로그인 응답의 access_token을 직접 입력해야 합니다."
          />
        )}

        {result?.state === "unauthorized" && (
          <Notice
            tone="danger"
            title="인증 실패"
            description="토큰이 없거나 만료되었거나, 이 프로젝트에 접근할 권한이 없습니다."
          />
        )}

        {result?.state === "not-found" && (
          <Notice
            tone="danger"
            title="CheckRun을 찾을 수 없습니다"
            description="Project ID, CheckRun ID 또는 현재 사용자 권한을 확인하세요."
          />
        )}

        {result?.state === "unavailable" && (
          <Notice
            tone="danger"
            title="API 요청 실패"
            description="API 서버 실행 상태와 NEXT_PUBLIC_API_URL 설정을 확인하세요."
          />
        )}

        {checkRun && (
          <>
            <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
              <StatusSummary
                checkRun={checkRun}
                shouldPoll={shouldPoll}
                lastUpdatedAt={lastUpdatedAt}
              />
              <TimelineCard checkRun={checkRun} />
            </section>

            <ScoreCard result={checkRun.score_result} />
            <AIReportSummaryCard report={checkRun.ai_report} />
            <ComparisonCard result={checkRun.comparison_result} />
            <LinkedScenarioRunsCard
              projectId={projectId}
              scenarioRuns={checkRun.linked_scenario_runs}
            />

            <section className="grid gap-4 lg:grid-cols-2">
              <AvailabilityCard result={checkRun.availability_result} />
              <SslCard result={checkRun.ssl_result} />
              <LighthouseCard result={checkRun.lighthouse_result} />
              <ArtifactCard accessToken={trimmedToken} artifacts={checkRun.artifacts} />
            </section>
          </>
        )}
      </section>
    </main>
  );
}

function Identifier({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
        {label}
      </p>
      <p className="break-all font-mono text-xs text-slate-200">{value}</p>
    </div>
  );
}

function StatusSummary({
  checkRun,
  shouldPoll,
  lastUpdatedAt
}: {
  checkRun: CheckRunDetail;
  shouldPoll: boolean;
  lastUpdatedAt: string | null;
}) {
  const badgeClassName = getStatusBadgeClassName(checkRun.status);

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">실행 상태</h2>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${badgeClassName}`}>
          {statusLabels[checkRun.status]}
        </span>
      </div>
      <dl className="grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
        <Metric label="Trigger" value={checkRun.trigger_source} />
        <Metric label="Polling" value={shouldPoll ? "자동 새로고침 중" : "중지됨"} />
        <Metric label="Failure" value={checkRun.failure_reason ?? "없음"} />
        <Metric label="Last refresh" value={lastUpdatedAt ?? "아직 없음"} />
      </dl>
    </article>
  );
}

function TimelineCard({ checkRun }: { checkRun: CheckRunDetail }) {
  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <h2 className="mb-5 text-xl font-semibold">타임라인</h2>
      <dl className="grid gap-4 text-sm text-slate-300">
        <Metric label="Queued" value={formatDateTime(checkRun.queued_at)} />
        <Metric label="Started" value={formatDateTime(checkRun.started_at)} />
        <Metric label="Finished" value={formatDateTime(checkRun.finished_at)} />
        <Metric label="Updated" value={formatDateTime(checkRun.updated_at)} />
      </dl>
    </article>
  );
}

function ScoreCard({ result }: { result: ScoreResult | null }) {
  if (!result) {
    return <EmptyResultCard title="Score" description="아직 계산된 score result가 없습니다." />;
  }

  const riskClassName = getRiskBadgeClassName(result.deployment_risk);

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Deterministic score
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <p className="text-5xl font-black tracking-tight">{result.grade}</p>
            <p className="pb-1 text-xl font-semibold text-slate-200">
              {result.overall_score}/100
            </p>
          </div>
          <p className="mt-3 text-sm text-slate-400">
            현재 구현된 scanner 기준 {result.evaluated_weight}% 가중치만 평가했습니다.
          </p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${riskClassName}`}>
          {riskLabels[result.deployment_risk]}
        </span>
      </div>

      {result.gate_reason && (
        <div className="mt-5">
          <Notice
            tone={result.deployment_risk === "RISK" ? "danger" : "info"}
            title="Risk gate 적용"
            description={result.gate_reason}
          />
        </div>
      )}

      <dl className="mt-5 grid gap-4 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-3">
        <Metric label="Availability" value={formatScore(result.availability_score)} />
        <Metric
          label="Functional stability"
          value={formatScore(result.functional_stability_score)}
        />
        <Metric label="Web performance" value={formatScore(result.web_performance_score)} />
        <Metric label="Accessibility" value={formatScore(result.accessibility_score)} />
        <Metric label="SEO/basic quality" value={formatScore(result.seo_basic_quality_score)} />
        <Metric
          label="Regression stability"
          value={formatScore(result.regression_stability_score)}
        />
        <Metric label="Scoring version" value={result.scoring_version} />
        <Metric label="Updated" value={formatDateTime(result.updated_at)} />
      </dl>
    </article>
  );
}

function AIReportSummaryCard({ report }: { report: AIReportSummary | null }) {
  if (!report) {
    return (
      <EmptyResultCard
        title="AI diagnosis"
        description="아직 저장된 AI 진단 요약이 없습니다. CheckRun이 terminal 상태가 된 뒤 worker가 리포트를 생성합니다."
      />
    );
  }

  const riskClassName = getRiskBadgeClassName(report.deployment_risk);

  return (
    <article className="rounded-3xl border border-cyan-300/20 bg-cyan-300/[0.04] p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">
            AI diagnosis
          </p>
          <h2 className="mt-3 text-2xl font-bold">근거 기반 진단 요약</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">{report.summary}</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${riskClassName}`}>
          {riskLabels[report.deployment_risk]}
        </span>
      </div>

      {report.gate_reason && (
        <div className="mt-5">
          <Notice
            tone={report.deployment_risk === "RISK" ? "danger" : "info"}
            title="진단 근거"
            description={report.gate_reason}
          />
        </div>
      )}

      <dl className="mt-5 grid gap-4 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Grade" value={report.grade} />
        <Metric label="Overall score" value={`${report.overall_score}/100`} />
        <Metric label="Generated" value={formatDateTime(report.generated_at)} />
        <Metric label="Updated" value={formatDateTime(report.updated_at)} />
      </dl>

      <p className="mt-5 rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-xs leading-5 text-slate-400">
        이 요약은 AIM이 수집한 score, scanner result, scenario evidence를 바탕으로 생성됩니다.
        내부 원인이나 소스 코드 위치를 확정 사실처럼 표시하지 않습니다.
      </p>
    </article>
  );
}

function ComparisonCard({ result }: { result: RunComparison | null }) {
  if (!result) {
    return (
      <EmptyResultCard
        title="Previous run comparison"
        description="비교 가능한 이전 run이 아직 없습니다."
      />
    );
  }

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Previous run comparison
          </p>
          <h2 className="mt-3 text-2xl font-bold">직전 run 대비 변화</h2>
          <p className="mt-3 text-sm leading-6 text-slate-300">{result.summary}</p>
        </div>
        <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-bold text-slate-300 ring-1 ring-white/10">
          {result.comparison_type}
        </span>
      </div>
      <dl className="mt-5 grid gap-4 text-sm text-slate-300 sm:grid-cols-2 lg:grid-cols-3">
        <Metric label="Baseline run" value={result.baseline_check_run_id} />
        <Metric label="Overall score" value={formatDelta(result.overall_score_delta)} />
        <Metric label="Availability" value={formatDelta(result.availability_score_delta)} />
        <Metric label="Performance score" value={formatDelta(result.performance_score_delta)} />
        <Metric
          label="Web performance"
          value={formatDelta(result.web_performance_score_delta)}
        />
        <Metric label="Accessibility" value={formatDelta(result.accessibility_score_delta)} />
        <Metric
          label="SEO/basic quality"
          value={formatDelta(result.seo_basic_quality_score_delta)}
        />
        <Metric
          label="Response time"
          value={formatMillisecondsDelta(result.response_time_delta_ms)}
        />
        <Metric
          label="Risk changed"
          value={result.deployment_risk_changed ? "예" : "아니오"}
        />
      </dl>
    </article>
  );
}

function LinkedScenarioRunsCard({
  projectId,
  scenarioRuns
}: {
  projectId: string;
  scenarioRuns: ScenarioRun[];
}) {
  const summary = summarizeScenarioRuns(scenarioRuns);

  if (scenarioRuns.length === 0) {
    return (
      <EmptyResultCard
        title="Linked ScenarioRuns"
        description="이 CheckRun에 연결된 ScenarioRun이 없습니다."
      />
    );
  }

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Functional checks
          </p>
          <h2 className="mt-2 text-xl font-semibold">연결된 ScenarioRun</h2>
        </div>
        <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-300 ring-1 ring-cyan-400/20">
          {scenarioRuns.length}개
        </span>
      </div>

      <div className={`mb-5 rounded-2xl border p-4 ${getScenarioSummaryClassName(summary)}`}>
        <p className="font-semibold">{getScenarioSummaryTitle(summary)}</p>
        <p className="mt-2 text-sm opacity-80">{getScenarioSummaryDescription(summary)}</p>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-5">
          <Metric label="Total" value={`${summary.total}개`} />
          <Metric label="Failed" value={`${summary.failed}개`} />
          <Metric label="Active" value={`${summary.active}개`} />
          <Metric label="Completed" value={`${summary.completed}개`} />
          <Metric label="Cancelled" value={`${summary.cancelled}개`} />
        </dl>
      </div>

      <ul className="grid gap-3">
        {scenarioRuns.map((scenarioRun) => {
          const isFailed = scenarioRun.status === "FAILED";

          return (
            <li
              className={`rounded-2xl border p-4 text-sm text-slate-300 ${
                isFailed
                  ? "border-rose-400/20 bg-rose-400/10"
                  : "border-white/10 bg-slate-900/60"
              }`}
              key={scenarioRun.id}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-slate-100">ScenarioRun</p>
                  <p className="mt-2 break-all font-mono text-xs text-slate-400">
                    {scenarioRun.id}
                  </p>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${getStatusBadgeClassName(
                    scenarioRun.status
                  )}`}
                >
                  {scenarioRunStatusLabels[scenarioRun.status]}
                </span>
              </div>
              {isFailed && (
                <p className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-950/40 p-3 text-sm text-rose-100">
                  우선 확인 필요: {scenarioRun.failure_reason ?? "실패 사유가 기록되지 않았습니다."}
                </p>
              )}
              <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label="Scenario ID" value={scenarioRun.scenario_id} />
                <Metric label="Trigger" value={scenarioRun.trigger_source} />
                <Metric label="Duration" value={formatMilliseconds(scenarioRun.duration_ms)} />
                <Metric label="Queued" value={formatDateTime(scenarioRun.queued_at)} />
                <Metric label="Started" value={formatDateTime(scenarioRun.started_at)} />
                <Metric label="Finished" value={formatDateTime(scenarioRun.finished_at)} />
                <Metric label="Failure" value={scenarioRun.failure_reason ?? "없음"} />
              </dl>
              <a
                className="mt-4 inline-flex rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-3 py-2 text-xs font-bold text-cyan-100 transition hover:border-cyan-200 hover:bg-cyan-300/20"
                href={`/projects/${projectId}/scenarios/${scenarioRun.scenario_id}/runs/${scenarioRun.id}`}
              >
                ScenarioRun 결과 보기
              </a>
            </li>
          );
        })}
      </ul>
    </article>
  );
}

type ScenarioRunSummary = {
  total: number;
  failed: number;
  active: number;
  completed: number;
  cancelled: number;
};

function summarizeScenarioRuns(scenarioRuns: ScenarioRun[]): ScenarioRunSummary {
  return scenarioRuns.reduce<ScenarioRunSummary>(
    (summary, scenarioRun) => {
      if (scenarioRun.status === "FAILED") {
        summary.failed += 1;
      }

      if (scenarioRun.status === "QUEUED" || scenarioRun.status === "RUNNING") {
        summary.active += 1;
      }

      if (scenarioRun.status === "COMPLETED") {
        summary.completed += 1;
      }

      if (scenarioRun.status === "CANCELLED") {
        summary.cancelled += 1;
      }

      return summary;
    },
    {
      total: scenarioRuns.length,
      failed: 0,
      active: 0,
      completed: 0,
      cancelled: 0
    }
  );
}

function getScenarioSummaryTitle(summary: ScenarioRunSummary) {
  if (summary.failed > 0) {
    return `실패한 ScenarioRun ${summary.failed}개`;
  }

  if (summary.active > 0) {
    return "ScenarioRun 실행 대기 또는 진행 중";
  }

  if (summary.cancelled > 0) {
    return "취소된 ScenarioRun 포함";
  }

  return "연결된 ScenarioRun 모두 성공";
}

function getScenarioSummaryDescription(summary: ScenarioRunSummary) {
  if (summary.failed > 0) {
    return "핵심 사용자 흐름 실패는 배포 위험 판단에서 우선 확인해야 할 신호입니다. 상세 step 결과와 screenshot 근거를 확인하세요.";
  }

  if (summary.active > 0) {
    return "아직 terminal 상태가 아닌 ScenarioRun이 있어 functional stability 판단이 확정되지 않았습니다.";
  }

  if (summary.cancelled > 0) {
    return "취소된 ScenarioRun은 성공 근거로 볼 수 없으므로 수동 확인 또는 재실행이 필요합니다.";
  }

  return "모든 linked ScenarioRun이 완료되어 functional stability 판단 근거로 사용할 수 있습니다.";
}

function getScenarioSummaryClassName(summary: ScenarioRunSummary) {
  if (summary.failed > 0) {
    return "border-rose-400/20 bg-rose-400/10 text-rose-100";
  }

  if (summary.active > 0) {
    return "border-cyan-400/20 bg-cyan-400/10 text-cyan-100";
  }

  if (summary.cancelled > 0) {
    return "border-amber-400/20 bg-amber-400/10 text-amber-100";
  }

  return "border-emerald-400/20 bg-emerald-400/10 text-emerald-100";
}

function AvailabilityCard({ result }: { result: AvailabilityResult | null }) {
  if (!result) {
    return <EmptyResultCard title="Availability" description="아직 availability 결과가 없습니다." />;
  }

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <ResultHeader
        title="Availability"
        isHealthy={result.is_available}
        healthyLabel="사용 가능"
        unhealthyLabel="사용 불가"
      />
      <dl className="mt-5 grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
        <Metric label="Status code" value={formatNullable(result.status_code)} />
        <Metric label="Response time" value={formatMilliseconds(result.response_time_ms)} />
        <Metric label="Redirects" value={String(result.redirect_count)} />
        <Metric label="HTTPS" value={result.uses_https ? "사용" : "미사용"} />
        <Metric label="Timed out" value={result.timed_out ? "예" : "아니오"} />
        <Metric label="Failure" value={result.failure_reason ?? "없음"} />
      </dl>
      <p className="mt-5 break-all text-xs text-slate-400">
        Final URL: {result.final_url ?? "없음"}
      </p>
    </article>
  );
}

function SslCard({ result }: { result: SslResult | null }) {
  if (!result) {
    return <EmptyResultCard title="SSL" description="아직 SSL inspection 결과가 없습니다." />;
  }

  const isHealthy = result.is_applicable ? result.is_valid === true : true;

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <ResultHeader
        title="SSL"
        isHealthy={isHealthy}
        healthyLabel={result.is_applicable ? "유효" : "대상 아님"}
        unhealthyLabel="문제 있음"
      />
      <dl className="mt-5 grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
        <Metric label="Applicable" value={result.is_applicable ? "예" : "아니오"} />
        <Metric label="Valid" value={formatBoolean(result.is_valid)} />
        <Metric label="Expires at" value={formatDateTime(result.expires_at)} />
        <Metric
          label="Days left"
          value={
            result.days_until_expiration === null
              ? "알 수 없음"
              : `${result.days_until_expiration}일`
          }
        />
        <Metric label="Failure" value={result.failure_reason ?? "없음"} />
      </dl>
      <p className="mt-5 break-all text-xs text-slate-400">Service URL: {result.service_url}</p>
    </article>
  );
}

function LighthouseCard({ result }: { result: LighthouseResult | null }) {
  if (!result) {
    return (
      <EmptyResultCard title="Lighthouse" description="아직 Lighthouse 결과가 없습니다." />
    );
  }

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <ResultHeader
        title="Lighthouse"
        isHealthy={result.is_successful}
        healthyLabel="실행 성공"
        unhealthyLabel="실행 실패"
      />
      <dl className="mt-5 grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
        <Metric label="Performance" value={formatScore(result.performance_score)} />
        <Metric label="Accessibility" value={formatScore(result.accessibility_score)} />
        <Metric label="SEO" value={formatScore(result.seo_score)} />
        <Metric label="Best practices" value={formatScore(result.best_practices_score)} />
        <Metric label="LCP" value={formatMilliseconds(result.largest_contentful_paint_ms)} />
        <Metric label="CLS" value={formatDecimal(result.cumulative_layout_shift)} />
        <Metric label="TBT" value={formatMilliseconds(result.total_blocking_time_ms)} />
        <Metric label="Raw JSON artifact" value={result.raw_json_artifact_id ?? "없음"} />
        <Metric label="Failure" value={result.failure_reason ?? "없음"} />
      </dl>
      <p className="mt-5 break-all text-xs text-slate-400">Service URL: {result.service_url}</p>
    </article>
  );
}

function ArtifactCard({
  accessToken,
  artifacts
}: {
  accessToken: string;
  artifacts: Artifact[];
}) {
  if (artifacts.length === 0) {
    return <EmptyResultCard title="Artifacts" description="아직 저장된 artifact metadata가 없습니다." />;
  }

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Artifacts</h2>
        <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-300 ring-1 ring-cyan-400/20">
          {artifacts.length}개
        </span>
      </div>
      <ul className="grid gap-3">
        {artifacts.map((artifact) => (
          <li
            className="rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-sm text-slate-300"
            key={artifact.id}
          >
            <p className="font-semibold text-slate-100">{artifact.artifact_type}</p>
            <p className="mt-2 break-all font-mono text-xs text-slate-400">
              {artifact.storage_backend}:{artifact.storage_path}
            </p>
            <dl className="mt-3 grid gap-3 sm:grid-cols-2">
              <Metric label="Content type" value={artifact.content_type} />
              <Metric label="Size" value={formatBytes(artifact.size_bytes)} />
              <Metric label="Created" value={formatDateTime(artifact.created_at)} />
              <Metric label="SHA-256" value={artifact.checksum_sha256} />
            </dl>
            <div className="mt-4">
              <ArtifactDownloadButton artifactId={artifact.id} accessToken={accessToken} />
            </div>
          </li>
        ))}
      </ul>
    </article>
  );
}

function EmptyResultCard({ title, description }: { title: string; description: string }) {
  return (
    <article className="rounded-3xl border border-dashed border-white/10 bg-white/[0.02] p-6">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-4 text-sm text-slate-400">{description}</p>
    </article>
  );
}

function ResultHeader({
  title,
  isHealthy,
  healthyLabel,
  unhealthyLabel
}: {
  title: string;
  isHealthy: boolean;
  healthyLabel: string;
  unhealthyLabel: string;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-xl font-semibold">{title}</h2>
      <span
        className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${
          isHealthy
            ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20"
            : "bg-rose-400/10 text-rose-300 ring-rose-400/20"
        }`}
      >
        {isHealthy ? healthyLabel : unhealthyLabel}
      </span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</dt>
      <dd className="mt-1 break-words text-slate-200">{value}</dd>
    </div>
  );
}

function Notice({
  tone,
  title,
  description
}: {
  tone: "info" | "danger";
  title: string;
  description: string;
}) {
  const className =
    tone === "info"
      ? "border-cyan-400/20 bg-cyan-400/10 text-cyan-100"
      : "border-rose-400/20 bg-rose-400/10 text-rose-100";

  return (
    <article className={`rounded-3xl border p-6 ${className}`}>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm opacity-80">{description}</p>
    </article>
  );
}

function getStatusBadgeClassName(status: CheckRunStatus | ScenarioRunStatus) {
  if (status === "COMPLETED") {
    return "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20";
  }

  if (status === "FAILED" || status === "CANCELLED") {
    return "bg-rose-400/10 text-rose-300 ring-rose-400/20";
  }

  return "bg-cyan-400/10 text-cyan-300 ring-cyan-400/20";
}

function getRiskBadgeClassName(risk: ScoreResult["deployment_risk"]) {
  if (risk === "STABLE") {
    return "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20";
  }

  if (risk === "RISK") {
    return "bg-rose-400/10 text-rose-300 ring-rose-400/20";
  }

  return "bg-amber-400/10 text-amber-300 ring-amber-400/20";
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "없음";
  }

  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "medium"
  }).format(new Date(value));
}

function formatMilliseconds(value: number | null) {
  return value === null ? "알 수 없음" : `${value}ms`;
}

function formatNullable(value: number | null) {
  return value === null ? "없음" : String(value);
}

function formatScore(value: number | null) {
  return value === null ? "알 수 없음" : `${value}/100`;
}

function formatDecimal(value: number | null) {
  return value === null ? "알 수 없음" : String(value);
}

function formatDelta(value: number | null) {
  if (value === null) {
    return "알 수 없음";
  }

  if (value > 0) {
    return `+${value}`;
  }

  return String(value);
}

function formatMillisecondsDelta(value: number | null) {
  if (value === null) {
    return "알 수 없음";
  }

  if (value > 0) {
    return `+${value}ms 느려짐`;
  }

  if (value < 0) {
    return `${value}ms 개선`;
  }

  return "0ms";
}

function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }

  return `${(value / 1024).toFixed(1)} KB`;
}

function formatBoolean(value: boolean | null) {
  if (value === null) {
    return "대상 아님";
  }

  return value ? "예" : "아니오";
}
