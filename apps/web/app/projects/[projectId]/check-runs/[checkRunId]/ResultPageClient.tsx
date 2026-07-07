"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArtifactDownloadButton } from "@/components/ArtifactDownloadButton";
import { AIReportDetailPanel } from "./AIReportDetailPanel";
import {
  cancelCheckRun,
  clearProjectBaseline,
  fetchBaselineComparison,
  fetchCheckRunAIReport,
  fetchCheckRunDetail,
  fetchProject,
  setProjectBaseline,
  type AIReportDetailResult,
  type AIReportSummary,
  type Artifact,
  type AvailabilityResult,
  type BaselineComparisonResult,
  type CheckRunDetail,
  type CheckRunDetailResult,
  type CheckRunStatus,
  type LighthouseResult,
  type LighthouseTopAudit,
  type Project,
  type ProjectDetailResult,
  type RunComparison,
  type ScoreBreakdown,
  type ScoreResult,
  type ScenarioRun,
  type SslResult
} from "@/lib/api";
import { buildAvailabilityAdvice, buildSslAdvice } from "@/lib/advice";
import {
  RingGauge,
  ScoreBandLegend,
  ScoreDonut,
  scoreBarClassName,
  ThresholdBar
} from "@/components/charts";
import { clearStoredAccessTokenIfMatches, getStoredAccessToken } from "@/lib/auth";
import { formatDetailDateTime, formatMilliseconds } from "@/lib/format";
import {
  buildBreakdownSummary,
  scoreCategoryLabel,
  scoreGateLabel,
  scoreReasonText
} from "@/lib/scoreBreakdown";
import {
  Badge,
  CheckRunStatusBadge,
  InfoHint,
  LinkButton,
  LoginRequiredNotice,
  Metric,
  Notice,
  RefreshButton,
  ScenarioRunStatusBadge
} from "@/components/ui";

const POLLING_INTERVAL_MS = 3_000;
const ACTIVE_STATUSES = new Set<CheckRunStatus>(["QUEUED", "RUNNING", "ANALYZING"]);

const riskLabels: Record<ScoreResult["deployment_risk"], string> = {
  STABLE: "안정",
  WARNING: "주의",
  RISK: "위험"
};

type CheckRunResultPageState =
  | { state: "checking" }
  | { state: "signed-out" }
  | CheckRunDetailResult;

export function ResultPageClient({
  projectId,
  checkRunId
}: {
  projectId: string;
  checkRunId: string;
}) {
  const [result, setResult] = useState<CheckRunResultPageState>({ state: "checking" });
  const [sessionToken, setSessionToken] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [aiReportDetailResult, setAIReportDetailResult] =
    useState<AIReportDetailResult | null>(null);
  const [isAIReportDetailLoading, setIsAIReportDetailLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [projectResult, setProjectResult] = useState<ProjectDetailResult | null>(null);
  const [baselineComparisonResult, setBaselineComparisonResult] =
    useState<BaselineComparisonResult | null>(null);
  const [isBaselineMutating, setIsBaselineMutating] = useState(false);
  const [baselineActionError, setBaselineActionError] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const checkRun = result.state === "success" ? result.checkRun : null;
  const shouldPoll = checkRun ? ACTIVE_STATUSES.has(checkRun.status) : false;
  const project = projectResult?.state === "success" ? projectResult.project : null;
  const baselineCheckRunId = project?.baseline_check_run_id ?? null;
  const isCheckRunTerminal = checkRun ? !ACTIVE_STATUSES.has(checkRun.status) : false;
  const visibleAIReportDetailResult =
    checkRun?.ai_report &&
    aiReportDetailResult?.state === "success" &&
    aiReportDetailResult.report.id !== checkRun.ai_report.id
      ? null
      : aiReportDetailResult;

  const loadCheckRun = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (!accessToken) {
      setResult({ state: "signed-out" });
      setSessionToken("");
      return;
    }

    setIsLoading(true);
    const nextResult = await fetchCheckRunDetail({
      projectId,
      checkRunId,
      accessToken
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
    }

    setResult(nextResult);
    setSessionToken(accessToken);
    if (nextResult.state !== "success" || nextResult.checkRun.ai_report === null) {
      setAIReportDetailResult(null);
    }
    setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
    setIsLoading(false);
  }, [checkRunId, projectId]);

  const loadProject = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (!accessToken) {
      setProjectResult(null);
      return;
    }

    const nextResult = await fetchProject({
      projectId,
      accessToken
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
    }

    setProjectResult(nextResult);
  }, [projectId]);

  const refresh = useCallback(async () => {
    await Promise.all([loadCheckRun(), loadProject()]);
  }, [loadCheckRun, loadProject]);

  const loadAIReportDetail = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (!accessToken) {
      setAIReportDetailResult(null);
      return;
    }

    setIsAIReportDetailLoading(true);
    const nextResult = await fetchCheckRunAIReport({
      projectId,
      checkRunId,
      accessToken
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
    }

    setAIReportDetailResult(nextResult);
    setIsAIReportDetailLoading(false);
  }, [checkRunId, projectId]);

  useEffect(() => {
    queueMicrotask(() => {
      void refresh();
    });
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    const accessToken = getStoredAccessToken();

    if (
      !accessToken ||
      !baselineCheckRunId ||
      baselineCheckRunId === checkRunId ||
      !isCheckRunTerminal
    ) {
      queueMicrotask(() => {
        if (!cancelled) {
          setBaselineComparisonResult(null);
        }
      });

      return () => {
        cancelled = true;
      };
    }

    void (async () => {
      const nextResult = await fetchBaselineComparison({
        projectId,
        checkRunId,
        accessToken
      });

      if (cancelled) {
        return;
      }

      if (nextResult.state === "unauthorized") {
        clearStoredAccessTokenIfMatches(accessToken);
      }

      setBaselineComparisonResult(nextResult);
    })();

    return () => {
      cancelled = true;
    };
  }, [baselineCheckRunId, checkRunId, isCheckRunTerminal, projectId]);

  const handleSetBaseline = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (!accessToken || isBaselineMutating) {
      return;
    }

    setIsBaselineMutating(true);
    setBaselineActionError(null);
    const mutationResult = await setProjectBaseline({
      projectId,
      checkRunId,
      accessToken
    });

    if (mutationResult.state === "success") {
      setProjectResult({ state: "success", project: mutationResult.project });
    } else if (mutationResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
      setBaselineActionError("인증이 만료되었습니다. 다시 로그인한 뒤 시도하세요.");
    } else if (mutationResult.state === "conflict") {
      setBaselineActionError(
        "terminal 상태이고 score가 계산된 CheckRun만 baseline으로 지정할 수 있습니다."
      );
    } else if (mutationResult.state === "not-found") {
      setBaselineActionError("프로젝트 또는 CheckRun을 찾을 수 없습니다.");
    } else {
      setBaselineActionError("baseline 설정 요청이 실패했습니다. API 서버 상태를 확인하세요.");
    }

    setIsBaselineMutating(false);
  }, [checkRunId, isBaselineMutating, projectId]);

  const handleClearBaseline = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (!accessToken || isBaselineMutating) {
      return;
    }

    setIsBaselineMutating(true);
    setBaselineActionError(null);
    const mutationResult = await clearProjectBaseline({
      projectId,
      accessToken
    });

    if (mutationResult.state === "success") {
      setProjectResult({ state: "success", project: mutationResult.project });
    } else if (mutationResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
      setBaselineActionError("인증이 만료되었습니다. 다시 로그인한 뒤 시도하세요.");
    } else if (mutationResult.state === "not-found") {
      setBaselineActionError("프로젝트를 찾을 수 없습니다.");
    } else {
      setBaselineActionError("baseline 해제 요청이 실패했습니다. API 서버 상태를 확인하세요.");
    }

    setIsBaselineMutating(false);
  }, [isBaselineMutating, projectId]);

  useEffect(() => {
    if (!shouldPoll) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refresh();
    }, POLLING_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [refresh, shouldPoll]);

  const handleCancelCheckRun = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (!accessToken || isCancelling) {
      return;
    }

    setIsCancelling(true);
    setCancelError(null);
    const cancelResult = await cancelCheckRun({
      projectId,
      checkRunId,
      accessToken
    });

    if (cancelResult.state === "success") {
      await loadCheckRun();
    } else if (cancelResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
      setCancelError("인증이 만료되었습니다. 다시 로그인한 뒤 시도하세요.");
    } else if (cancelResult.state === "not-found") {
      setCancelError("CheckRun을 찾을 수 없습니다.");
    } else {
      setCancelError("취소 요청이 실패했습니다. API 서버 상태를 확인하세요.");
    }

    setIsCancelling(false);
  }, [checkRunId, isCancelling, loadCheckRun, projectId]);

  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <header className="flex flex-col gap-6 rounded-3xl border border-slate-200 bg-white p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-cyan-700">
                AIM Scan Result
              </p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
                CheckRun 결과
              </h1>
              <p className="mt-4 text-sm leading-6 text-slate-600">
                검사 상태와 수집된 결과를 보여줍니다. 검사가 진행 중이면 자동으로
                새로고침됩니다.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <LinkButton href={`/projects/${projectId}/check-runs`} label="CheckRun 이력" />
              <RefreshButton isLoading={isLoading} onClick={() => void refresh()} />
            </div>
          </div>
        </header>

        {result.state === "checking" && (
          <Notice
            tone="info"
            title="로그인 세션 확인 중"
            description="저장된 로그인 세션이 있으면 자동으로 CheckRun 결과를 조회합니다."
          />
        )}

        {result.state === "signed-out" && <LoginRequiredNotice />}

        {result.state === "unauthorized" && <LoginRequiredNotice expired />}

        {result.state === "not-found" && (
          <Notice
            tone="danger"
            title="CheckRun을 찾을 수 없습니다"
            description="Project ID, CheckRun ID 또는 현재 사용자 권한을 확인하세요."
          />
        )}

        {result.state === "unavailable" && (
          <Notice
            tone="danger"
            title="요청 실패"
            description="서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
          />
        )}

        {checkRun && (
          <>
            <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
              <StatusSummary
                cancelError={cancelError}
                checkRun={checkRun}
                isCancelling={isCancelling}
                lastUpdatedAt={lastUpdatedAt}
                onCancel={() => void handleCancelCheckRun()}
                shouldPoll={shouldPoll}
              />
              <TimelineCard checkRun={checkRun} />
            </section>

            <ScoreCard result={checkRun.score_result} />
            <ComparisonCard result={checkRun.comparison_result} />
            <BaselineComparisonCard
              actionError={baselineActionError}
              checkRun={checkRun}
              comparisonResult={baselineComparisonResult}
              isMutating={isBaselineMutating}
              onClearBaseline={handleClearBaseline}
              onSetBaseline={handleSetBaseline}
              project={project}
            />
            <LinkedScenarioRunsCard
              projectId={projectId}
              scenarioRuns={checkRun.linked_scenario_runs}
            />

            <section className="grid gap-4 lg:grid-cols-2">
              <AvailabilityCard
                responseTimeThresholdMs={project?.response_time_threshold_ms ?? null}
                result={checkRun.availability_result}
              />
              <SslCard result={checkRun.ssl_result} />
              <LighthouseCard result={checkRun.lighthouse_result} />
              <ArtifactCard accessToken={sessionToken} artifacts={checkRun.artifacts} />
            </section>

            <AIReportSummaryCard
              detailResult={visibleAIReportDetailResult}
              isLoadingDetail={isAIReportDetailLoading}
              onLoadDetail={loadAIReportDetail}
              report={checkRun.ai_report}
              topAudits={checkRun.lighthouse_result?.top_audits ?? null}
            />
          </>
        )}
      </section>
    </main>
  );
}

function StatusSummary({
  cancelError,
  checkRun,
  isCancelling,
  lastUpdatedAt,
  onCancel,
  shouldPoll
}: {
  cancelError: string | null;
  checkRun: CheckRunDetail;
  isCancelling: boolean;
  lastUpdatedAt: string | null;
  onCancel: () => void;
  shouldPoll: boolean;
}) {
  return (
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 bg-white p-6"
      id="run-status-card"
    >
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">실행 상태</h2>
        <CheckRunStatusBadge status={checkRun.status} />
      </div>
      <dl className="grid gap-4 text-sm text-slate-600 sm:grid-cols-2">
        <Metric
          hint="검사를 시작한 방식입니다 — manual은 수동 실행, scheduled는 정기 스캔."
          label="Trigger"
          value={checkRun.trigger_source}
        />
        <Metric label="Polling" value={shouldPoll ? "자동 새로고침 중" : "중지됨"} />
        <Metric label="Failure" value={checkRun.failure_reason ?? "없음"} />
        <Metric label="Last refresh" value={lastUpdatedAt ?? "아직 없음"} />
      </dl>

      {shouldPoll && (
        <div className="mt-5">
          <button
            className="rounded-2xl border border-rose-300 bg-rose-50 px-4 py-2 text-sm font-bold text-rose-800 transition hover:border-rose-500 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isCancelling}
            onClick={onCancel}
            type="button"
          >
            {isCancelling ? "취소 요청 중" : "이 CheckRun 취소"}
          </button>
          <p className="mt-2 text-xs text-slate-500">
            대기·실행·분석 중인 CheckRun만 취소할 수 있습니다.
          </p>
        </div>
      )}

      {cancelError && (
        <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
          {cancelError}
        </p>
      )}
    </article>
  );
}

function TimelineCard({ checkRun }: { checkRun: CheckRunDetail }) {
  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6">
      <h2 className="mb-5 text-xl font-semibold">타임라인</h2>
      <dl className="grid gap-4 text-sm text-slate-600">
        <Metric label="Queued" value={formatDetailDateTime(checkRun.queued_at)} />
        <Metric label="Started" value={formatDetailDateTime(checkRun.started_at)} />
        <Metric label="Finished" value={formatDetailDateTime(checkRun.finished_at)} />
        <Metric label="Updated" value={formatDetailDateTime(checkRun.updated_at)} />
      </dl>
    </article>
  );
}

export function ScoreCard({ result }: { result: ScoreResult | null }) {
  if (!result) {
    return <EmptyResultCard title="Score" description="아직 계산된 score result가 없습니다." />;
  }

  const riskClassName = getRiskBadgeClassName(result.deployment_risk);
  const categoryGauges = [
    {
      hint: "HTTP 응답 성공 여부와 응답 속도로 계산한 접속 안정성 점수입니다.",
      key: "availability",
      score: result.availability_score
    },
    {
      hint: "핵심 사용자 흐름(시나리오) 실행이 성공했는지에 대한 점수입니다.",
      key: "functional_stability",
      score: result.functional_stability_score
    },
    {
      hint: "Lighthouse 성능 점수 — 페이지 로딩 속도 지표를 기반으로 합니다.",
      key: "web_performance",
      score: result.web_performance_score
    },
    {
      hint: "Lighthouse 접근성 점수 — 색 대비, 스크린 리더 지원 같은 접근성 기준입니다.",
      key: "accessibility",
      score: result.accessibility_score
    },
    {
      hint: "Lighthouse SEO 점수와 웹 권장사항 점수의 평균입니다.",
      key: "seo_basic_quality",
      score: result.seo_basic_quality_score
    },
    {
      hint: "이전 결과 대비 나빠지지 않았는지 보는 항목입니다. (준비 중)",
      key: "regression_stability",
      score: result.regression_stability_score
    }
  ];

  return (
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 bg-white p-6"
      id="score-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-700">
          Deterministic score
          <InfoHint text="수집된 검사 데이터에 고정된 규칙을 적용해 자동 계산한 점수입니다." />
        </p>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${riskClassName}`}>
          {riskLabels[result.deployment_risk]}
        </span>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-x-8 gap-y-5">
        <ScoreDonut
          grade={result.grade}
          risk={result.deployment_risk}
          score={result.overall_score}
        />
        <div className="min-w-56 max-w-md flex-1">
          <p className="break-keep text-sm leading-6 text-slate-600">
            전체 평가 항목 중{" "}
            <span className="font-bold text-slate-900">{result.evaluated_weight}%</span>가 이번
            점수에 반영되었습니다.
          </p>
          <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-cyan-500"
              style={{ width: `${result.evaluated_weight}%` }}
            />
          </div>
          <p className="mt-1.5 text-[11px] font-semibold text-slate-400">
            반영 {result.evaluated_weight}% · 제외 {100 - result.evaluated_weight}%
          </p>
        </div>
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

      <div className="mt-6 flex flex-wrap gap-x-5 gap-y-5">
        {categoryGauges.map((category) => (
          <RingGauge
            hint={category.hint}
            key={category.key}
            label={scoreCategoryLabel(category.key)}
            score={category.score}
          />
        ))}
      </div>
      <ScoreBandLegend showExcluded />

      {result.score_breakdown && <ScoreBreakdownSection breakdown={result.score_breakdown} />}

      <p className="mt-5 text-xs text-slate-500">
        Updated: {formatDetailDateTime(result.updated_at)}
      </p>
    </article>
  );
}

function ScoreBreakdownSection({ breakdown }: { breakdown: ScoreBreakdown }) {
  return (
    <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-700">
        점수는 이렇게 계산됐어요
      </p>
      <p className="mt-2 break-keep text-sm leading-6 text-slate-600">
        {buildBreakdownSummary(breakdown)}
      </p>

      {breakdown.gate && (
        <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          등급 제한: {scoreGateLabel(breakdown.gate)} → 최대 {breakdown.gate.grade_cap}
        </p>
      )}

      <ul className="mt-4 grid gap-3">
        {breakdown.categories.map((category) => (
          <li key={category.key}>
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="font-semibold text-slate-700">
                {scoreCategoryLabel(category.key)}
                <span className="ml-2 text-xs font-semibold text-slate-400">
                  {category.weight}%
                </span>
              </span>
              <span
                className={
                  category.score === null
                    ? "text-xs font-semibold text-slate-400"
                    : "font-bold text-slate-900"
                }
              >
                {category.score === null ? "평가 제외" : `${category.score}점`}
              </span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-200">
              {category.score !== null && category.score > 0 && (
                <div
                  className={`h-full rounded-full ${scoreBarClassName(category.score)}`}
                  style={{ width: `${category.score}%` }}
                />
              )}
            </div>
            <p className="mt-1.5 break-keep text-xs leading-5 text-slate-500">
              {category.reasons.map((reason) => scoreReasonText(reason)).join(" · ")}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AIReportSummaryCard({
  detailResult,
  isLoadingDetail,
  onLoadDetail,
  report,
  topAudits
}: {
  detailResult: AIReportDetailResult | null;
  isLoadingDetail: boolean;
  onLoadDetail: () => void;
  report: AIReportSummary | null;
  topAudits: LighthouseTopAudit[] | null;
}) {
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
    <article className="rounded-3xl border border-cyan-200 bg-cyan-50/60 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-700">
            AI diagnosis
            <InfoHint text="수집된 근거만을 바탕으로 AI가 작성한 진단 요약입니다." />
          </p>
          <h2 className="mt-3 text-2xl font-bold">근거 기반 진단 요약</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">{report.summary}</p>
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

      <dl className="mt-5 grid gap-4 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          hint="종합 점수의 등급입니다 — 90점 이상 A, 80 이상 B, 70 이상 C, 50 이상 D, 그 미만 F."
          label="Grade"
          value={report.grade}
        />
        <Metric
          hint="카테고리 점수를 가중치로 평균 낸 종합 점수입니다."
          label="Overall score"
          value={`${report.overall_score}/100`}
        />
        <Metric label="Generated" value={formatDetailDateTime(report.generated_at)} />
        <Metric label="Updated" value={formatDetailDateTime(report.updated_at)} />
      </dl>

      <p className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs leading-5 text-slate-500">
        이 요약은 AIM이 수집한 score, scanner result, scenario evidence를 바탕으로 생성됩니다.
        내부 원인이나 소스 코드 위치를 확정 사실처럼 표시하지 않습니다.
      </p>

      <div className="mt-5">
        <button
          className="rounded-2xl border border-cyan-300 bg-cyan-50 px-4 py-3 text-sm font-bold text-cyan-700 transition hover:border-cyan-500 hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isLoadingDetail}
          onClick={onLoadDetail}
          type="button"
        >
          {isLoadingDetail
            ? "상세 진단 불러오는 중"
            : detailResult?.state === "success"
              ? "상세 진단 새로고침"
              : "상세 진단 보기"}
        </button>
      </div>

      {detailResult?.state === "unauthorized" && (
        <div className="mt-5">
          <Notice
            tone="danger"
            title="AIReport 인증 실패"
            description="토큰이 없거나 만료되었거나, 이 리포트에 접근할 권한이 없습니다."
          />
        </div>
      )}

      {detailResult?.state === "not-found" && (
        <div className="mt-5">
          <Notice
            tone="info"
            title="AIReport 상세 없음"
            description="요약은 있지만 전체 리포트가 아직 저장되지 않았거나, CheckRun 권한을 다시 확인해야 합니다."
          />
        </div>
      )}

      {detailResult?.state === "unavailable" && (
        <div className="mt-5">
          <Notice
            tone="danger"
            title="AIReport 요청 실패"
            description="API 서버 상태와 네트워크 연결을 확인한 뒤 다시 시도하세요."
          />
        </div>
      )}

      {detailResult?.state === "success" && (
        <AIReportDetailPanel report={detailResult.report} topAudits={topAudits} />
      )}
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
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 bg-white p-6"
      id="comparison-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-700">
            Previous run comparison
          </p>
          <h2 className="mt-3 text-2xl font-bold">직전 run 대비 변화</h2>
          <p className="mt-3 text-sm leading-6 text-slate-600">{result.summary}</p>
        </div>
        <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-bold text-slate-600 ring-1 ring-slate-200">
          {result.comparison_type}
        </span>
      </div>
      <dl className="mt-5 grid gap-4 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-3">
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

function BaselineComparisonCard({
  actionError,
  checkRun,
  comparisonResult,
  isMutating,
  onClearBaseline,
  onSetBaseline,
  project
}: {
  actionError: string | null;
  checkRun: CheckRunDetail;
  comparisonResult: BaselineComparisonResult | null;
  isMutating: boolean;
  onClearBaseline: () => void;
  onSetBaseline: () => void;
  project: Project | null;
}) {
  if (!project) {
    return (
      <EmptyResultCard
        title="Baseline comparison"
        description="프로젝트 정보를 불러온 뒤 baseline 지정과 비교를 사용할 수 있습니다."
      />
    );
  }

  const baselineCheckRunId = project.baseline_check_run_id;
  const isCurrentBaseline = baselineCheckRunId === checkRun.id;
  const isTerminal = !ACTIVE_STATUSES.has(checkRun.status);
  const canPin = isTerminal && checkRun.score_result !== null;

  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-700">
            Baseline comparison
          </p>
          <h2 className="mt-3 text-2xl font-bold">Baseline 대비 변화</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            프로젝트 baseline은 배포 전 마지막 정상 run 같은 기준점입니다. 직전 run 비교와 달리
            항상 같은 기준과 비교하므로 배포가 실제로 나아졌는지 판단할 수 있습니다.
          </p>
        </div>
        {isCurrentBaseline && (
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700 ring-1 ring-emerald-200">
            현재 baseline
          </span>
        )}
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-3">
        {isCurrentBaseline ? (
          <button
            className="rounded-2xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm font-bold text-rose-800 transition hover:border-rose-500 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={isMutating}
            onClick={onClearBaseline}
            type="button"
          >
            {isMutating ? "baseline 해제 중" : "baseline 해제"}
          </button>
        ) : (
          <button
            className="rounded-2xl border border-cyan-300 bg-cyan-50 px-4 py-3 text-sm font-bold text-cyan-700 transition hover:border-cyan-500 hover:bg-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canPin || isMutating}
            onClick={onSetBaseline}
            type="button"
          >
            {isMutating ? "baseline 지정 중" : "이 run을 baseline으로 지정"}
          </button>
        )}
        {!isCurrentBaseline && !canPin && (
          <p className="text-xs text-slate-500">
            terminal 상태이고 score가 계산된 run만 baseline으로 지정할 수 있습니다.
          </p>
        )}
      </div>

      {actionError && (
        <div className="mt-5">
          <Notice tone="danger" title="Baseline 요청 실패" description={actionError} />
        </div>
      )}

      <div className="mt-5">
        <BaselineComparisonBody
          baselineCheckRunId={baselineCheckRunId}
          comparisonResult={comparisonResult}
          isCurrentBaseline={isCurrentBaseline}
          isTerminal={isTerminal}
        />
      </div>
    </article>
  );
}

function BaselineComparisonBody({
  baselineCheckRunId,
  comparisonResult,
  isCurrentBaseline,
  isTerminal
}: {
  baselineCheckRunId: string | null;
  comparisonResult: BaselineComparisonResult | null;
  isCurrentBaseline: boolean;
  isTerminal: boolean;
}) {
  if (!baselineCheckRunId) {
    return (
      <Notice
        tone="info"
        title="아직 baseline이 없습니다"
        description="terminal 상태의 run에서 baseline을 지정하면 이후 모든 run을 같은 기준과 비교할 수 있습니다."
      />
    );
  }

  if (isCurrentBaseline) {
    return (
      <Notice
        tone="info"
        title="이 run이 프로젝트 baseline입니다"
        description="다른 CheckRun 결과 페이지에서 이 baseline 대비 변화를 확인할 수 있습니다."
      />
    );
  }

  if (!isTerminal) {
    return (
      <Notice
        tone="info"
        title="run이 아직 완료되지 않았습니다"
        description="CheckRun이 terminal 상태가 되면 baseline 비교를 계산합니다."
      />
    );
  }

  if (!comparisonResult) {
    return <p className="text-sm text-slate-500">baseline 비교를 불러오는 중입니다.</p>;
  }

  if (comparisonResult.state === "unauthorized") {
    return (
      <Notice
        tone="danger"
        title="baseline 비교 인증 실패"
        description="토큰이 만료되었거나 이 프로젝트에 접근할 권한이 없습니다."
      />
    );
  }

  if (comparisonResult.state === "not-found") {
    return (
      <Notice
        tone="danger"
        title="baseline run을 찾을 수 없습니다"
        description="baseline으로 지정된 CheckRun이 더 이상 존재하지 않습니다. baseline을 다시 지정하세요."
      />
    );
  }

  if (comparisonResult.state === "conflict") {
    return (
      <Notice
        tone="info"
        title="baseline 비교를 계산할 수 없습니다"
        description="baseline 또는 이 run에 score result가 없어 비교할 수 없습니다."
      />
    );
  }

  if (comparisonResult.state === "unavailable") {
    return (
      <Notice
        tone="danger"
        title="baseline 비교 요청 실패"
        description="API 서버 상태와 네트워크 연결을 확인한 뒤 다시 시도하세요."
      />
    );
  }

  const comparison = comparisonResult.comparison;

  return (
    <div>
      <p className="text-sm leading-6 text-slate-600">{comparison.summary}</p>
      <dl className="mt-5 grid gap-4 text-sm text-slate-600 sm:grid-cols-2 lg:grid-cols-3">
        <Metric label="Overall score" value={formatDelta(comparison.overall_score_delta)} />
        <Metric label="Availability" value={formatDelta(comparison.availability_score_delta)} />
        <Metric
          label="Performance score"
          value={formatDelta(comparison.performance_score_delta)}
        />
        <Metric
          label="Web performance"
          value={formatDelta(comparison.web_performance_score_delta)}
        />
        <Metric
          label="Accessibility"
          value={formatDelta(comparison.accessibility_score_delta)}
        />
        <Metric
          label="SEO/basic quality"
          value={formatDelta(comparison.seo_basic_quality_score_delta)}
        />
        <Metric
          label="Response time"
          value={formatMillisecondsDelta(comparison.response_time_delta_ms)}
        />
        <Metric
          label="Deployment risk"
          value={`${riskLabels[comparison.baseline_deployment_risk]} → ${
            riskLabels[comparison.current_deployment_risk]
          }`}
        />
      </dl>
    </div>
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
      <article
        className="scroll-mt-24 rounded-3xl border border-slate-200 bg-white p-6"
        id="scenario-runs-card"
      >
        <h2 className="text-xl font-semibold text-slate-900">Linked ScenarioRuns</h2>
        <p className="mt-3 text-sm leading-6 text-slate-500">
          이 CheckRun에 연결된 ScenarioRun이 없습니다. Project의 Scenario 목록에서 수동 실행
          이력과 설정을 확인할 수 있습니다.
        </p>
        <Link
          className="mt-5 inline-flex rounded-xl border border-cyan-300 bg-cyan-50 px-3 py-2 text-xs font-bold text-cyan-700 transition hover:border-cyan-500 hover:bg-cyan-100"
          href={`/projects/${projectId}/scenarios`}
        >
          Scenario 목록 보기
        </Link>
      </article>
    );
  }

  return (
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 bg-white p-6"
      id="scenario-runs-card"
    >
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-700">
            Functional checks
          </p>
          <h2 className="mt-2 text-xl font-semibold">연결된 ScenarioRun</h2>
        </div>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
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
              className={`rounded-2xl border p-4 text-sm text-slate-600 ${
                isFailed
                  ? "border-rose-200 bg-rose-50"
                  : "border-slate-200 bg-slate-50"
              }`}
              key={scenarioRun.id}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <p className="font-semibold text-slate-900">ScenarioRun</p>
                <ScenarioRunStatusBadge status={scenarioRun.status} />
              </div>
              {isFailed && (
                <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-100 p-3 text-sm text-rose-800">
                  우선 확인 필요: {scenarioRun.failure_reason ?? "실패 사유가 기록되지 않았습니다."}
                </p>
              )}
              <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label="Trigger" value={scenarioRun.trigger_source} />
                <Metric label="Duration" value={formatMilliseconds(scenarioRun.duration_ms)} />
                <Metric label="Queued" value={formatDetailDateTime(scenarioRun.queued_at)} />
                <Metric label="Started" value={formatDetailDateTime(scenarioRun.started_at)} />
                <Metric label="Finished" value={formatDetailDateTime(scenarioRun.finished_at)} />
                <Metric label="Failure" value={scenarioRun.failure_reason ?? "없음"} />
              </dl>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link
                  className="inline-flex rounded-xl border border-cyan-300 bg-cyan-50 px-3 py-2 text-xs font-bold text-cyan-700 transition hover:border-cyan-500 hover:bg-cyan-100"
                  href={`/projects/${projectId}/scenarios/${scenarioRun.scenario_id}/runs/${scenarioRun.id}`}
                >
                  ScenarioRun 결과 보기
                </Link>
                <Link
                  className="inline-flex rounded-xl border border-slate-200 px-3 py-2 text-xs font-bold text-slate-700 transition hover:border-cyan-400 hover:text-cyan-700"
                  href={`/projects/${projectId}/scenarios/${scenarioRun.scenario_id}/runs`}
                >
                  ScenarioRun 목록 보기
                </Link>
              </div>
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
    return "border-rose-200 bg-rose-50 text-rose-800";
  }

  if (summary.active > 0) {
    return "border-cyan-200 bg-cyan-50 text-cyan-700";
  }

  if (summary.cancelled > 0) {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }

  return "border-emerald-200 bg-emerald-50 text-emerald-800";
}

export function AvailabilityCard({
  responseTimeThresholdMs,
  result
}: {
  responseTimeThresholdMs: number | null;
  result: AvailabilityResult | null;
}) {
  if (!result) {
    return <EmptyResultCard title="Availability" description="아직 availability 결과가 없습니다." />;
  }

  const responseTimeMs = result.response_time_ms;
  const thresholdMs =
    responseTimeThresholdMs !== null && responseTimeThresholdMs > 0
      ? responseTimeThresholdMs
      : null;
  const showResponseTimeBar = responseTimeMs !== null && thresholdMs !== null;

  return (
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 bg-white p-6"
      id="availability-card"
    >
      <ResultHeader
        title="Availability"
        isHealthy={result.is_available}
        healthyLabel="사용 가능"
        unhealthyLabel="사용 불가"
      />
      <dl className="mt-5 grid gap-4 text-sm text-slate-600 sm:grid-cols-2">
        <Metric
          hint="서버가 반환한 HTTP 상태 코드입니다 — 200이면 정상 응답."
          label="Status code"
          value={formatNullable(result.status_code)}
        />
        {!showResponseTimeBar && (
          <Metric
            hint="요청 후 첫 응답을 받기까지 걸린 시간입니다."
            label="Response time"
            value={formatMilliseconds(result.response_time_ms)}
          />
        )}
        <Metric
          hint="최종 페이지에 도달할 때까지 거친 리다이렉트 횟수입니다."
          label="Redirects"
          value={String(result.redirect_count)}
        />
        <Metric
          hint="암호화된 HTTPS로 서비스되고 있는지 여부입니다."
          label="HTTPS"
          value={result.uses_https ? "사용" : "미사용"}
        />
        <Metric
          hint="제한 시간 안에 응답하지 못했는지 여부입니다."
          label="Timed out"
          value={result.timed_out ? "예" : "아니오"}
        />
        <Metric label="Failure" value={result.failure_reason ?? "없음"} />
      </dl>
      {showResponseTimeBar && (
        <div className="mt-5 border-t border-slate-200 pt-4">
          <ThresholdBar
            goodLabel={`임계값 ${formatMilliseconds(thresholdMs)}`}
            goodTo={thresholdMs}
            hint={`요청 후 첫 응답을 받기까지 걸린 시간입니다. 프로젝트 임계값(${formatMilliseconds(
              thresholdMs
            )}) 이내가 목표입니다.`}
            label="Response time"
            max={Math.max(thresholdMs * 2.5, responseTimeMs * 1.15)}
            midLabel={formatMilliseconds(thresholdMs * 2)}
            midTo={thresholdMs * 2}
            value={responseTimeMs}
            valueLabel={formatMilliseconds(responseTimeMs)}
          />
        </div>
      )}
      <AdviceList items={buildAvailabilityAdvice(result, responseTimeThresholdMs)} />
      <p className="mt-5 break-all text-xs text-slate-500">
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
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 bg-white p-6"
      id="ssl-card"
    >
      <ResultHeader
        title="SSL"
        isHealthy={isHealthy}
        healthyLabel={result.is_applicable ? "유효" : "대상 아님"}
        unhealthyLabel="문제 있음"
      />
      <dl className="mt-5 grid gap-4 text-sm text-slate-600 sm:grid-cols-2">
        <Metric
          hint="HTTPS를 사용하는 서비스만 인증서 검사 대상이 됩니다."
          label="Applicable"
          value={result.is_applicable ? "예" : "아니오"}
        />
        <Metric
          hint="인증서가 신뢰할 수 있고 만료되지 않았는지 여부입니다."
          label="Valid"
          value={formatBoolean(result.is_valid)}
        />
        <Metric label="Expires at" value={formatDetailDateTime(result.expires_at)} />
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
      <AdviceList items={buildSslAdvice(result)} />
      <p className="mt-5 break-all text-xs text-slate-500">Service URL: {result.service_url}</p>
    </article>
  );
}

function AdviceList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-700">권장 조치</p>
      <ul className="mt-2 grid gap-2 text-sm leading-6 text-amber-900">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function LighthouseCard({ result }: { result: LighthouseResult | null }) {
  if (!result) {
    return (
      <EmptyResultCard title="Lighthouse" description="아직 Lighthouse 결과가 없습니다." />
    );
  }

  return (
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 bg-white p-6"
      id="lighthouse-card"
    >
      <ResultHeader
        title="Lighthouse"
        isHealthy={result.is_successful}
        healthyLabel="실행 성공"
        unhealthyLabel="실행 실패"
      />
      <div className="mt-5 flex flex-wrap gap-x-6 gap-y-5">
        <RingGauge
          hint="로딩 속도 지표를 종합한 Lighthouse 성능 점수입니다. (100점 만점)"
          label="Performance"
          score={result.performance_score}
        />
        <RingGauge
          hint="색 대비, 스크린 리더 지원 같은 접근성 기준 점수입니다. (100점 만점)"
          label="Accessibility"
          score={result.accessibility_score}
        />
        <RingGauge
          hint="검색 엔진이 페이지를 잘 이해할 수 있는지에 대한 점수입니다. (100점 만점)"
          label="SEO"
          score={result.seo_score}
        />
        <RingGauge
          hint="웹 개발 권장사항을 얼마나 지키는지에 대한 점수입니다. (100점 만점)"
          label="Best practices"
          score={result.best_practices_score}
        />
      </div>
      <ScoreBandLegend />
      {(result.largest_contentful_paint_ms !== null ||
        result.cumulative_layout_shift !== null ||
        result.total_blocking_time_ms !== null) && (
        <div className="mt-6 grid gap-5 border-t border-slate-200 pt-5">
          <ThresholdBar
            goodLabel="2.5초"
            goodTo={2500}
            hint="Largest Contentful Paint — 주요 콘텐츠가 화면에 그려지기까지 걸린 시간입니다. (2.5초 이내 권장)"
            label="LCP"
            max={Math.max(5000, (result.largest_contentful_paint_ms ?? 0) * 1.15)}
            midLabel="4초"
            midTo={4000}
            value={result.largest_contentful_paint_ms}
            valueLabel={formatMilliseconds(result.largest_contentful_paint_ms)}
          />
          <ThresholdBar
            goodLabel="0.1"
            goodTo={0.1}
            hint="Cumulative Layout Shift — 로딩 중 화면 요소가 밀리는 정도입니다. (0.1 이하 권장)"
            label="CLS"
            max={Math.max(0.4, (result.cumulative_layout_shift ?? 0) * 1.15)}
            midLabel="0.25"
            midTo={0.25}
            value={result.cumulative_layout_shift}
            valueLabel={formatDecimal(result.cumulative_layout_shift)}
          />
          <ThresholdBar
            goodLabel="200ms"
            goodTo={200}
            hint="Total Blocking Time — 로딩 중 입력 반응이 막혀 있던 시간입니다. (200ms 이하 권장)"
            label="TBT"
            max={Math.max(1000, (result.total_blocking_time_ms ?? 0) * 1.15)}
            midLabel="600ms"
            midTo={600}
            value={result.total_blocking_time_ms}
            valueLabel={formatMilliseconds(result.total_blocking_time_ms)}
          />
        </div>
      )}
      {result.failure_reason && (
        <p className="mt-5 break-keep rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm leading-6 text-rose-800">
          실패 사유: {result.failure_reason}
        </p>
      )}
      <LighthouseTopAuditList audits={result.top_audits} isSuccessful={result.is_successful} />
      <p className="mt-5 break-all text-xs text-slate-500">Service URL: {result.service_url}</p>
    </article>
  );
}

function LighthouseTopAuditList({
  audits,
  isSuccessful
}: {
  audits: LighthouseTopAudit[] | null;
  isSuccessful: boolean;
}) {
  if (audits === null) {
    return null;
  }

  if (audits.length === 0) {
    if (!isSuccessful) {
      return null;
    }

    return (
      <p className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
        Lighthouse가 발견한 주요 개선 기회가 없습니다.
      </p>
    );
  }

  return (
    <div className="mt-5 border-t border-slate-200 pt-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-700">
        개선 기회 Top {audits.length}
      </p>
      <ol className="mt-3 grid gap-2">
        {audits.map((audit, index) => {
          const impact = formatAuditImpact(audit);

          return (
            <li className="rounded-2xl border border-slate-200 bg-slate-50 p-3" key={audit.id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="text-sm font-semibold leading-5 text-slate-900">
                  {index + 1}. {audit.title}
                </p>
                <Badge label={formatAuditCategory(audit.category)} />
              </div>
              {impact && <p className="mt-1 text-xs text-slate-500">{impact}</p>}
            </li>
          );
        })}
      </ol>
    </div>
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
    <article className="rounded-3xl border border-slate-200 bg-white p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Artifacts</h2>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
          {artifacts.length}개
        </span>
      </div>
      <ul className="grid gap-3">
        {artifacts.map((artifact) => (
          <li
            className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600"
            key={artifact.id}
          >
            <p className="font-semibold text-slate-900">{artifact.artifact_type}</p>
            <dl className="mt-3 grid gap-3 sm:grid-cols-2">
              <Metric label="Size" value={formatBytes(artifact.size_bytes)} />
              <Metric label="Created" value={formatDetailDateTime(artifact.created_at)} />
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
    <article className="rounded-3xl border border-dashed border-slate-200 bg-white/60 p-6">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-4 text-sm text-slate-500">{description}</p>
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
            ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
            : "bg-rose-50 text-rose-700 ring-rose-200"
        }`}
      >
        {isHealthy ? healthyLabel : unhealthyLabel}
      </span>
    </div>
  );
}

function getRiskBadgeClassName(risk: ScoreResult["deployment_risk"]) {
  if (risk === "STABLE") {
    return "bg-emerald-50 text-emerald-700 ring-emerald-200";
  }

  if (risk === "RISK") {
    return "bg-rose-50 text-rose-700 ring-rose-200";
  }

  return "bg-amber-50 text-amber-700 ring-amber-200";
}

function formatNullable(value: number | null) {
  return value === null ? "없음" : String(value);
}

const auditCategoryLabels: Record<string, string> = {
  performance: "성능",
  accessibility: "접근성",
  seo: "SEO",
  "best-practices": "권장사항"
};

function formatAuditCategory(category: string) {
  return auditCategoryLabels[category] ?? category;
}

function formatAuditImpact(audit: LighthouseTopAudit) {
  if (audit.display_value) {
    return audit.display_value;
  }

  const savings: string[] = [];
  if (audit.savings_ms !== null && audit.savings_ms > 0) {
    savings.push(`약 ${formatMilliseconds(audit.savings_ms)} 단축 가능`);
  }
  if (audit.savings_bytes !== null && audit.savings_bytes > 0) {
    savings.push(`약 ${Math.round(audit.savings_bytes / 1024)}KB 절감 가능`);
  }

  return savings.length > 0 ? savings.join(" · ") : null;
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
