"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ArtifactDownloadButton } from "@/components/ArtifactDownloadButton";
import { AIReportDetailPanel } from "./AIReportDetailPanel";
import { InvestigationCard, type InvestigationCardState } from "./InvestigationCard";
import {
  cancelCheckRun,
  clearProjectBaseline,
  fetchAgentInvestigation,
  fetchBaselineComparison,
  fetchCheckRunAIReport,
  fetchCheckRunDetail,
  fetchProject,
  requestAgentInvestigation,
  setProjectBaseline,
  type AgentInvestigation,
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
import { scoringPresetLabel, triggerSourceLabel } from "@/lib/statusLabels";
import {
  RingGauge,
  ScoreBandLegend,
  ScoreDonut,
  scoreBarClassName,
  ThresholdBar
} from "@/components/charts";
import { clearStoredAccessTokenIfMatches, getStoredAccessToken } from "@/lib/auth";
import {
  formatDateTime,
  formatDetailDateTime,
  formatDuration,
  formatMilliseconds
} from "@/lib/format";
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
  LoginRequiredNotice,
  Metric,
  Notice,
  RefreshButton,
  ScenarioRunStatusBadge
} from "@/components/ui";

const POLLING_INTERVAL_MS = 3_000;
const ACTIVE_STATUSES = new Set<CheckRunStatus>(["QUEUED", "RUNNING", "ANALYZING"]);
const MAX_AI_REPORT_WAIT_POLLS = 60;

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
  const [reportWaitPolls, setReportWaitPolls] = useState(0);
  const [investigation, setInvestigation] = useState<AgentInvestigation | null>(null);
  const [investigationState, setInvestigationState] =
    useState<InvestigationCardState>("idle");
  const checkRun = result.state === "success" ? result.checkRun : null;
  const isAIReportPending = checkRun?.status === "COMPLETED" && checkRun.ai_report === null;
  const isAwaitingAIReport = isAIReportPending && reportWaitPolls < MAX_AI_REPORT_WAIT_POLLS;
  const shouldPoll = checkRun
    ? ACTIVE_STATUSES.has(checkRun.status) || isAwaitingAIReport
    : false;
  const project = projectResult?.state === "success" ? projectResult.project : null;
  const baselineCheckRunId = project?.baseline_check_run_id ?? null;
  const isCheckRunTerminal = checkRun ? !ACTIVE_STATUSES.has(checkRun.status) : false;
  const visibleAIReportDetailResult =
    checkRun?.ai_report &&
    aiReportDetailResult?.state === "success" &&
    aiReportDetailResult.report.id !== checkRun.ai_report.id
      ? null
      : aiReportDetailResult;

  const loadInvestigation = useCallback(async () => {
    if (!isCheckRunTerminal) {
      return;
    }
    const accessToken = getStoredAccessToken();
    if (!accessToken) {
      return;
    }
    const nextResult = await fetchAgentInvestigation({
      projectId,
      checkRunId,
      accessToken
    });
    if (nextResult.state === "success") {
      setInvestigation(nextResult.investigation);
      setInvestigationState("idle");
    } else if (nextResult.state === "not-found") {
      setInvestigation(null);
      setInvestigationState((prev) => (prev === "requested" ? "requested" : "missing"));
    } else if (nextResult.state === "unauthorized") {
      setInvestigationState("unauthorized");
    } else {
      setInvestigationState("error");
    }
  }, [checkRunId, isCheckRunTerminal, projectId]);

  useEffect(() => {
    queueMicrotask(() => {
      void loadInvestigation();
    });
  }, [loadInvestigation]);

  const handleRequestInvestigation = useCallback(async () => {
    const accessToken = getStoredAccessToken();
    if (!accessToken) {
      setInvestigationState("unauthorized");
      return;
    }
    setInvestigationState("loading");
    const requestResult = await requestAgentInvestigation({
      projectId,
      checkRunId,
      accessToken
    });
    if (requestResult.state === "conflict") {
      await loadInvestigation();
      return;
    }
    if (requestResult.state === "unauthorized") {
      setInvestigationState("unauthorized");
      return;
    }
    if (requestResult.state !== "accepted") {
      setInvestigationState("error");
      return;
    }
    setInvestigationState("requested");
    // 조사는 재검사를 포함하면 몇 분 걸릴 수 있다 — 핸들러 안에서
    // 한정 폴링(10초 × 30회)으로 완료를 기다린다.
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 10_000));
      const pollResult = await fetchAgentInvestigation({
        projectId,
        checkRunId,
        accessToken
      });
      if (pollResult.state === "success") {
        setInvestigation(pollResult.investigation);
        setInvestigationState("idle");
        return;
      }
      if (pollResult.state !== "not-found") {
        return;
      }
    }
  }, [checkRunId, loadInvestigation, projectId]);

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
    if (nextResult.state === "success" && nextResult.checkRun.ai_report !== null) {
      setReportWaitPolls(0);
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
        "종료 상태이고 점수가 계산된 검사만 기준점으로 지정할 수 있습니다."
      );
    } else if (mutationResult.state === "not-found") {
      setBaselineActionError("프로젝트 또는 검사를 찾을 수 없습니다.");
    } else {
      setBaselineActionError("기준점 설정 요청이 실패했습니다. API 서버 상태를 확인하세요.");
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
      setBaselineActionError("기준점 해제 요청이 실패했습니다. API 서버 상태를 확인하세요.");
    }

    setIsBaselineMutating(false);
  }, [isBaselineMutating, projectId]);

  useEffect(() => {
    if (!shouldPoll) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void refresh();
      if (isAIReportPending) {
        setReportWaitPolls((count) => count + 1);
      }
    }, POLLING_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [isAIReportPending, refresh, shouldPoll]);

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
      setCancelError("검사를 찾을 수 없습니다.");
    } else {
      setCancelError("취소 요청이 실패했습니다. API 서버 상태를 확인하세요.");
    }

    setIsCancelling(false);
  }, [checkRunId, isCancelling, loadCheckRun, projectId]);

  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-8">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <Link
              aria-label="검사 이력으로 돌아가기"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-400 transition hover:border-cyan-400 hover:text-cyan-700 dark:hover:text-cyan-300"
              href={`/projects/${projectId}/check-runs`}
              title="검사 이력으로 돌아가기"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 16 16">
                <path
                  d="M10 4L6 8l4 4"
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.75"
                />
              </svg>
            </Link>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">검사 결과</h1>
                {checkRun && <CheckRunStatusBadge status={checkRun.status} />}
                {shouldPoll && (
                  <span className="text-xs font-bold text-cyan-600 dark:text-cyan-400">자동 새로고침 중</span>
                )}
              </div>
              {checkRun && (
                <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
                  {triggerSourceLabel(checkRun.trigger_source)}
                  {checkRun.deploy_ref ? ` (${checkRun.deploy_ref.slice(0, 7)})` : ""} ·{" "}
                  {formatDateTime(checkRun.queued_at)} · 소요{" "}
                  {formatDuration(checkRun.started_at, checkRun.finished_at)}
                  {lastUpdatedAt ? ` · 갱신 ${lastUpdatedAt}` : ""}
                </p>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {checkRun && (
              <HeaderBaselineAction
                checkRun={checkRun}
                isMutating={isBaselineMutating}
                onClearBaseline={handleClearBaseline}
                onSetBaseline={handleSetBaseline}
                project={project}
              />
            )}
            {checkRun && ACTIVE_STATUSES.has(checkRun.status) && (
              <button
                className="rounded-2xl border border-rose-300 dark:border-rose-800 bg-rose-50 dark:bg-rose-950 px-4 py-2 text-sm font-bold text-rose-800 dark:text-rose-300 transition hover:border-rose-500 hover:bg-rose-100 dark:hover:bg-rose-900/60 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isCancelling}
                onClick={() => void handleCancelCheckRun()}
                type="button"
              >
                {isCancelling ? "취소 요청 중" : "검사 취소"}
              </button>
            )}
            <RefreshButton isLoading={isLoading} onClick={() => void refresh()} />
          </div>
        </header>

        {result.state === "checking" && (
          <Notice
            tone="info"
            title="로그인 세션 확인 중"
            description="저장된 로그인 세션이 있으면 자동으로 검사 결과를 조회합니다."
          />
        )}

        {result.state === "signed-out" && <LoginRequiredNotice />}

        {result.state === "unauthorized" && <LoginRequiredNotice expired />}

        {result.state === "not-found" && (
          <Notice
            tone="danger"
            title="검사를 찾을 수 없습니다"
            description="프로젝트 ID, 검사 ID 또는 현재 사용자 권한을 확인하세요."
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
            {checkRun.failure_reason && (
              <Notice
                description={checkRun.failure_reason}
                title="검사 실패 사유"
                tone="danger"
              />
            )}
            {cancelError && (
              <Notice description={cancelError} title="취소 요청 실패" tone="danger" />
            )}

            <VerdictCard
              aiReport={checkRun.ai_report}
              detailResult={visibleAIReportDetailResult}
              isGeneratingReport={isAwaitingAIReport}
              isLoadingDetail={isAIReportDetailLoading}
              onLoadDetail={loadAIReportDetail}
              result={checkRun.score_result}
              status={checkRun.status}
              topAudits={checkRun.lighthouse_result?.top_audits ?? null}
            />

            <InvestigationCard
              canRequest={isCheckRunTerminal}
              investigation={investigation}
              onRequest={() => void handleRequestInvestigation()}
              state={investigationState}
            />

            <DeltaStripCard
              actionError={baselineActionError}
              baselineComparisonResult={baselineComparisonResult}
              checkRun={checkRun}
              comparison={checkRun.comparison_result}
              project={project}
            />

            <DetailSections
              accessToken={sessionToken}
              checkRun={checkRun}
              projectId={projectId}
              qualityScoreThreshold={project?.quality_score_threshold ?? null}
              responseTimeThresholdMs={project?.response_time_threshold_ms ?? null}
            />
          </>
        )}
      </section>
    </main>
  );
}

const verdictCategoryKeys = [
  "availability",
  "functional_stability",
  "web_performance",
  "accessibility",
  "seo_basic_quality",
  "regression_stability"
] as const;

function getVerdictCategoryScore(
  result: ScoreResult,
  key: (typeof verdictCategoryKeys)[number]
): number | null {
  if (key === "availability") {
    return result.availability_score;
  }

  if (key === "functional_stability") {
    return result.functional_stability_score;
  }

  if (key === "web_performance") {
    return result.web_performance_score;
  }

  if (key === "accessibility") {
    return result.accessibility_score;
  }

  if (key === "regression_stability") {
    return result.regression_stability_score;
  }

  return result.seo_basic_quality_score;
}

function CategoryBar({ label, score }: { label: string; score: number | null }) {
  return (
    <div className="flex items-center gap-2 py-1">
      <span className="w-24 shrink-0 break-keep text-xs text-slate-500 dark:text-slate-400">{label}</span>
      <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        {score !== null && score > 0 && (
          <div
            className={`h-full rounded-full ${scoreBarClassName(score)}`}
            style={{ width: `${score}%` }}
          />
        )}
      </div>
      <span className="w-8 shrink-0 text-right text-xs font-bold text-slate-700 dark:text-slate-200">
        {score === null ? "–" : Math.round(score)}
      </span>
    </div>
  );
}

function VerdictCard({
  aiReport,
  detailResult,
  isGeneratingReport,
  isLoadingDetail,
  onLoadDetail,
  result,
  status,
  topAudits
}: {
  aiReport: AIReportSummary | null;
  detailResult: AIReportDetailResult | null;
  isGeneratingReport: boolean;
  isLoadingDetail: boolean;
  onLoadDetail: () => void;
  result: ScoreResult | null;
  status: CheckRunStatus;
  topAudits: LighthouseTopAudit[] | null;
}) {
  return (
    <article className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
      {result ? (
        <div className="flex flex-wrap items-center gap-x-8 gap-y-5">
          <div className="flex items-center gap-5">
            <ScoreDonut
              grade={result.grade}
              risk={result.deployment_risk}
              score={result.overall_score}
            />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-3xl font-black tracking-tight text-slate-900 dark:text-white">
                  {result.overall_score}점
                </span>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${getRiskBadgeClassName(result.deployment_risk)}`}
                >
                  {riskLabels[result.deployment_risk]}
                </span>
              </div>
              {result.gate_reason && (
                <p className="mt-2 max-w-60 break-keep text-xs leading-5 text-amber-700 dark:text-amber-300">
                  {result.gate_reason}
                </p>
              )}
              <p className="mt-2 text-[11px] font-semibold text-slate-400 dark:text-slate-500">
                평가 항목 반영 {result.evaluated_weight}%
              </p>
            </div>
          </div>
          <div className="min-w-56 flex-1">
            {verdictCategoryKeys.map((key) => (
              <CategoryBar
                key={key}
                label={scoreCategoryLabel(key)}
                score={getVerdictCategoryScore(result, key)}
              />
            ))}
          </div>
        </div>
      ) : (
        <p className="text-sm leading-6 text-slate-500 dark:text-slate-400">
          {ACTIVE_STATUSES.has(status)
            ? "검사가 진행 중입니다. 완료되면 점수와 AI 진단이 여기에 표시됩니다."
            : "이 검사에는 계산된 점수가 없습니다. 실패한 검사는 점수 대신 실패 사유를 확인하세요."}
        </p>
      )}

      <div className="mt-5 border-t border-slate-200 dark:border-slate-800 pt-4">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-400">
          AI 진단
          <InfoHint text="수집된 근거만을 바탕으로 AI가 작성한 진단 요약입니다. 점수와 이슈 목록은 결정론 규칙이 계산하며 AI는 서술만 작성합니다." />
        </p>
        {aiReport ? (
          <>
            <p className="mt-2 break-keep text-sm leading-6 text-slate-700 dark:text-slate-200">
              {aiReport.summary}
            </p>
            <div className="mt-3">
              <button
                className="rounded-xl border border-cyan-300 dark:border-cyan-800 bg-cyan-50 dark:bg-cyan-950 px-3 py-1.5 text-xs font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-500 hover:bg-cyan-100 dark:hover:bg-cyan-900/60 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={isLoadingDetail}
                onClick={onLoadDetail}
                type="button"
              >
                {isLoadingDetail
                  ? "상세 진단 불러오는 중"
                  : detailResult?.state === "success"
                    ? "상세 진단 새로고침"
                    : "이슈별 영향·조치 보기"}
              </button>
            </div>
            {detailResult?.state === "unauthorized" && (
              <p className="mt-3 text-xs font-semibold text-rose-600 dark:text-rose-400">
                토큰이 없거나 만료되었거나, 이 리포트에 접근할 권한이 없습니다.
              </p>
            )}
            {detailResult?.state === "not-found" && (
              <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
                요약은 있지만 전체 리포트가 아직 저장되지 않았습니다.
              </p>
            )}
            {detailResult?.state === "unavailable" && (
              <p className="mt-3 text-xs font-semibold text-rose-600 dark:text-rose-400">
                AI 리포트 요청이 실패했습니다. API 서버 상태를 확인한 뒤 다시 시도하세요.
              </p>
            )}
            {detailResult?.state === "success" && (
              <AIReportDetailPanel report={detailResult.report} topAudits={topAudits} />
            )}
          </>
        ) : isGeneratingReport ? (
          <p className="mt-2 text-sm leading-6 text-cyan-700 dark:text-cyan-400">
            AI 진단 리포트를 생성하고 있습니다. 준비되는 대로 자동으로 표시됩니다.
          </p>
        ) : (
          <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
            아직 저장된 AI 진단 요약이 없습니다. 검사가 종료된 뒤 리포트가 생성됩니다.
          </p>
        )}
      </div>
    </article>
  );
}

function DeltaChip({
  label,
  unit = "",
  invert = false,
  value
}: {
  label: string;
  unit?: string;
  invert?: boolean;
  value: number;
}) {
  const isImprovement = invert ? value < 0 : value > 0;
  const chipClassName = isImprovement
    ? "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 ring-emerald-200 dark:ring-emerald-900"
    : "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900";
  const formatted = value > 0 ? `+${value}` : `${value}`;

  return (
    <span
      className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ${chipClassName}`}
    >
      {label} {formatted}
      {unit}
    </span>
  );
}

type DeltaEntry = {
  key: string;
  label: string;
  value: number | null;
};

function buildScoreDeltaEntries(deltas: {
  overall_score_delta: number | null;
  availability_score_delta: number | null;
  performance_score_delta: number | null;
  web_performance_score_delta: number | null;
  accessibility_score_delta: number | null;
  seo_basic_quality_score_delta: number | null;
}): DeltaEntry[] {
  return [
    { key: "overall", label: "종합", value: deltas.overall_score_delta },
    { key: "availability", label: "가용성", value: deltas.availability_score_delta },
    { key: "performance", label: "성능", value: deltas.performance_score_delta },
    { key: "web_performance", label: "웹 성능", value: deltas.web_performance_score_delta },
    { key: "accessibility", label: "접근성", value: deltas.accessibility_score_delta },
    { key: "seo", label: "SEO/품질", value: deltas.seo_basic_quality_score_delta }
  ].filter((entry) => entry.value !== null && entry.value !== 0);
}

function DeltaChipRow({
  entries,
  responseTimeDeltaMs,
  riskChanged
}: {
  entries: DeltaEntry[];
  responseTimeDeltaMs: number | null;
  riskChanged: boolean;
}) {
  const hasResponseChip = responseTimeDeltaMs !== null && responseTimeDeltaMs !== 0;

  if (entries.length === 0 && !hasResponseChip && !riskChanged) {
    return <span className="text-xs text-slate-400 dark:text-slate-500">변화 없음</span>;
  }

  return (
    <>
      {entries.map((entry) => (
        <DeltaChip key={entry.key} label={entry.label} value={entry.value ?? 0} />
      ))}
      {hasResponseChip && (
        <DeltaChip invert label="응답" unit="ms" value={responseTimeDeltaMs} />
      )}
      {riskChanged && (
        <span className="whitespace-nowrap rounded-full bg-amber-50 dark:bg-amber-950 px-2.5 py-0.5 text-xs font-bold text-amber-700 dark:text-amber-300 ring-1 ring-amber-200 dark:ring-amber-900">
          위험 단계 변화
        </span>
      )}
    </>
  );
}

// 기준점 지정/변경/해제는 "이 검사"에 대한 행동이므로 페이지 헤더의 액션 영역에
// 고정 배치한다(2026-07-18 UX 개선). 같은 자리가 상태에 따라 주 버튼(지정) →
// 보조 버튼(변경) → 상태 배지(현재 기준점)로 바뀌어 상태 표시기를 겸한다.
function HeaderBaselineAction({
  checkRun,
  isMutating,
  onClearBaseline,
  onSetBaseline,
  project
}: {
  checkRun: CheckRunDetail;
  isMutating: boolean;
  onClearBaseline: () => void;
  onSetBaseline: () => void;
  project: Project | null;
}) {
  if (!project) {
    return null;
  }

  const baselineCheckRunId = project.baseline_check_run_id;
  const isCurrentBaseline = baselineCheckRunId === checkRun.id;
  const isTerminal = !ACTIVE_STATUSES.has(checkRun.status);
  const canPin = isTerminal && checkRun.score_result !== null;
  const disabledReason = canPin ? undefined : "점수가 있는 종료된 검사만 지정할 수 있습니다";

  if (isCurrentBaseline) {
    return (
      <span className="inline-flex items-center gap-2 whitespace-nowrap rounded-2xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950 px-4 py-2 text-sm font-bold text-emerald-700 dark:text-emerald-400">
        📌 현재 기준점
        <button
          className="text-xs font-bold text-rose-600 dark:text-rose-400 underline underline-offset-2 transition hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={isMutating}
          onClick={onClearBaseline}
          type="button"
        >
          {isMutating ? "해제 중" : "해제"}
        </button>
      </span>
    );
  }

  if (!baselineCheckRunId) {
    return (
      <button
        className="whitespace-nowrap rounded-2xl bg-cyan-600 px-4 py-2 text-sm font-bold text-white shadow-lg shadow-cyan-600/30 transition hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none"
        disabled={!canPin || isMutating}
        onClick={onSetBaseline}
        title={disabledReason}
        type="button"
      >
        {isMutating ? "지정 중" : "📌 이 검사를 기준점으로"}
      </button>
    );
  }

  return (
    <button
      className="whitespace-nowrap rounded-2xl border border-cyan-300 dark:border-cyan-800 bg-white dark:bg-slate-900 px-4 py-2 text-sm font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-500 hover:bg-cyan-50 dark:hover:bg-cyan-950 disabled:cursor-not-allowed disabled:opacity-50"
      disabled={!canPin || isMutating}
      onClick={onSetBaseline}
      title={disabledReason}
      type="button"
    >
      {isMutating ? "변경 중" : "📌 이 검사로 기준 변경"}
    </button>
  );
}

const baselineErrorMessages: Record<
  Exclude<BaselineComparisonResult["state"], "success">,
  string
> = {
  unauthorized: "기준점 비교 인증이 실패했습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "기준점 검사가 더 이상 존재하지 않습니다. 기준점을 다시 지정하세요.",
  conflict: "기준점 또는 이 검사에 점수가 없어 비교할 수 없습니다.",
  unavailable: "기준점 비교 요청이 실패했습니다. 잠시 후 다시 시도하세요."
};

// 행동 버튼은 페이지 헤더(HeaderBaselineAction)로 이동했다.
// 이 행은 기준점의 정체(배지)와 비교 결과(칩)만 보여주는 읽기 전용 영역이다.
function BaselineRow({
  baselineComparisonResult,
  checkRun,
  project
}: {
  baselineComparisonResult: BaselineComparisonResult | null;
  checkRun: CheckRunDetail;
  project: Project | null;
}) {
  if (!project) {
    return <span className="text-xs text-slate-400 dark:text-slate-500">프로젝트 정보를 불러오는 중입니다</span>;
  }

  const baselineCheckRunId = project.baseline_check_run_id;
  const isCurrentBaseline = baselineCheckRunId === checkRun.id;
  const isTerminal = !ACTIVE_STATUSES.has(checkRun.status);

  if (isCurrentBaseline) {
    return (
      <span className="whitespace-nowrap rounded-full bg-emerald-50 dark:bg-emerald-950 px-2.5 py-0.5 text-xs font-bold text-emerald-700 dark:text-emerald-400 ring-1 ring-emerald-200 dark:ring-emerald-900">
        📌 이 검사가 현재 기준점
      </span>
    );
  }

  if (!baselineCheckRunId) {
    return (
      <span className="break-keep rounded-xl bg-cyan-50 dark:bg-cyan-950 px-3 py-1.5 text-xs leading-5 text-cyan-900">
        기준점이 없습니다 — 지정하면 이후 모든 검사가 이 검사와 자동 비교됩니다. 우측 상단
        📌 버튼으로 지정하세요.
      </span>
    );
  }

  if (!isTerminal) {
    return (
      <span className="text-xs text-slate-400 dark:text-slate-500">검사가 종료되면 기준점 비교를 계산합니다</span>
    );
  }

  if (!baselineComparisonResult) {
    return <span className="text-xs text-slate-400 dark:text-slate-500">기준점 비교를 불러오는 중입니다</span>;
  }

  if (baselineComparisonResult.state !== "success") {
    return (
      <span className="text-xs font-semibold text-rose-600 dark:text-rose-400">
        {baselineErrorMessages[baselineComparisonResult.state]}
      </span>
    );
  }

  const comparison = baselineComparisonResult.comparison;
  const riskChanged =
    comparison.baseline_deployment_risk !== comparison.current_deployment_risk;

  return (
    <>
      <Link
        className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-cyan-200 dark:border-cyan-900 bg-cyan-50 dark:bg-cyan-950 px-2.5 py-0.5 text-xs font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-400 hover:text-cyan-800"
        href={`/projects/${project.id}/check-runs/${baselineCheckRunId}`}
        title="기준점 검사 결과로 이동"
      >
        📌 기준 검사 보기
      </Link>
      <DeltaChipRow
        entries={buildScoreDeltaEntries(comparison)}
        responseTimeDeltaMs={comparison.response_time_delta_ms}
        riskChanged={false}
      />
      {riskChanged && (
        <span className="whitespace-nowrap rounded-full bg-amber-50 dark:bg-amber-950 px-2.5 py-0.5 text-xs font-bold text-amber-700 dark:text-amber-300 ring-1 ring-amber-200 dark:ring-amber-900">
          위험 {riskLabels[comparison.baseline_deployment_risk]} →{" "}
          {riskLabels[comparison.current_deployment_risk]}
        </span>
      )}
    </>
  );
}

function DeltaStripCard({
  actionError,
  baselineComparisonResult,
  checkRun,
  comparison,
  project
}: {
  actionError: string | null;
  baselineComparisonResult: BaselineComparisonResult | null;
  checkRun: CheckRunDetail;
  comparison: RunComparison | null;
  project: Project | null;
}) {
  return (
    <article className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
        <span className="w-20 shrink-0 text-xs font-semibold text-slate-400 dark:text-slate-500">직전 대비</span>
        {comparison ? (
          <DeltaChipRow
            entries={buildScoreDeltaEntries(comparison)}
            responseTimeDeltaMs={comparison.response_time_delta_ms}
            riskChanged={comparison.deployment_risk_changed}
          />
        ) : (
          <span className="text-xs text-slate-400 dark:text-slate-500">비교 가능한 이전 검사가 없습니다</span>
        )}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-2 border-t border-slate-100 dark:border-slate-800 pt-3">
        <span className="w-20 shrink-0 text-xs font-semibold text-slate-400 dark:text-slate-500">기준점 대비</span>
        <BaselineRow
          baselineComparisonResult={baselineComparisonResult}
          checkRun={checkRun}
          project={project}
        />
      </div>
      {actionError && (
        <p className="mt-3 text-xs font-semibold text-rose-600 dark:text-rose-400">{actionError}</p>
      )}
    </article>
  );
}

export function ScoreCard({ result }: { result: ScoreResult | null }) {
  if (!result) {
    return <EmptyResultCard title="점수" description="아직 계산된 점수가 없습니다." />;
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
      hint: "직전 검사 대비 카테고리 점수 하락 폭으로 계산한 회귀 안정성입니다. 첫 검사는 평가 제외.",
      key: "regression_stability",
      score: result.regression_stability_score
    }
  ];

  return (
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6"
      id="score-card"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-400">
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
          <p className="break-keep text-sm leading-6 text-slate-600 dark:text-slate-300">
            전체 평가 항목 중{" "}
            <span className="font-bold text-slate-900 dark:text-white">{result.evaluated_weight}%</span>가 이번
            점수에 반영되었습니다.
          </p>
          <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <div
              className="h-full rounded-full bg-cyan-500"
              style={{ width: `${result.evaluated_weight}%` }}
            />
          </div>
          <p className="mt-1.5 text-[11px] font-semibold text-slate-400 dark:text-slate-500">
            반영 {result.evaluated_weight}% · 제외 {100 - result.evaluated_weight}%
          </p>
        </div>
      </div>

      {result.gate_reason && (
        <div className="mt-5">
          <Notice
            tone={result.deployment_risk === "RISK" ? "danger" : "info"}
            title="위험 게이트 적용"
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

      <p className="mt-5 text-xs text-slate-500 dark:text-slate-400">
        갱신 시각: {formatDetailDateTime(result.updated_at)}
      </p>
    </article>
  );
}

function ScoreBreakdownSection({ breakdown }: { breakdown: ScoreBreakdown }) {
  return (
    <div className="mt-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-400">
        점수는 이렇게 계산됐어요
      </p>
      <p className="mt-2 break-keep text-sm leading-6 text-slate-600 dark:text-slate-300">
        {buildBreakdownSummary(breakdown)}
      </p>

      {breakdown.gate && (
        <p className="mt-3 rounded-xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950 p-3 text-sm text-amber-800 dark:text-amber-300">
          등급 제한: {scoreGateLabel(breakdown.gate)} → 최대 {breakdown.gate.grade_cap}
        </p>
      )}

      <ul className="mt-4 grid gap-3">
        {breakdown.categories.map((category) => (
          <li key={category.key}>
            <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="font-semibold text-slate-700 dark:text-slate-200">
                {scoreCategoryLabel(category.key)}
                <span className="ml-2 text-xs font-semibold text-slate-400 dark:text-slate-500">
                  {category.weight}%
                </span>
              </span>
              <span
                className={
                  category.score === null
                    ? "text-xs font-semibold text-slate-400 dark:text-slate-500"
                    : "font-bold text-slate-900 dark:text-white"
                }
              >
                {category.score === null ? "평가 제외" : `${category.score}점`}
              </span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
              {category.score !== null && category.score > 0 && (
                <div
                  className={`h-full rounded-full ${scoreBarClassName(category.score)}`}
                  style={{ width: `${category.score}%` }}
                />
              )}
            </div>
            <p className="mt-1.5 break-keep text-xs leading-5 text-slate-500 dark:text-slate-400">
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
  isGenerating = false,
  isLoadingDetail,
  onLoadDetail,
  report,
  topAudits
}: {
  detailResult: AIReportDetailResult | null;
  isGenerating?: boolean;
  isLoadingDetail: boolean;
  onLoadDetail: () => void;
  report: AIReportSummary | null;
  topAudits: LighthouseTopAudit[] | null;
}) {
  if (!report) {
    return (
      <EmptyResultCard
        title="AI 진단"
        description={
          isGenerating
            ? "AI 진단 리포트를 생성하고 있습니다. 준비되는 대로 자동으로 표시됩니다."
            : "아직 저장된 AI 진단 요약이 없습니다. 검사가 종료된 뒤 리포트가 생성됩니다."
        }
      />
    );
  }

  const riskClassName = getRiskBadgeClassName(report.deployment_risk);

  return (
    <article className="rounded-3xl border border-cyan-200 dark:border-cyan-900 bg-cyan-50/60 dark:bg-cyan-950/40 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-400">
            AI 진단
            <InfoHint text="수집된 근거만을 바탕으로 AI가 작성한 진단 요약입니다." />
          </p>
          <h2 className="mt-3 text-2xl font-bold">근거 기반 진단 요약</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">{report.summary}</p>
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

      <dl className="mt-5 grid gap-4 text-sm text-slate-600 dark:text-slate-300 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          hint="종합 점수의 등급입니다 — 90점 이상 A, 80 이상 B, 70 이상 C, 50 이상 D, 그 미만 F."
          label="등급"
          value={report.grade}
        />
        <Metric
          hint="카테고리 점수를 가중치로 평균 낸 종합 점수입니다."
          label="종합 점수"
          value={`${report.overall_score}/100`}
        />
        <Metric label="생성 시각" value={formatDetailDateTime(report.generated_at)} />
        <Metric label="갱신 시각" value={formatDetailDateTime(report.updated_at)} />
      </dl>

      <p className="mt-5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4 text-xs leading-5 text-slate-500 dark:text-slate-400">
        이 요약은 AIM이 수집한 점수, 스캔 결과, 시나리오 근거를 바탕으로 생성됩니다.
        내부 원인이나 소스 코드 위치를 확정 사실처럼 표시하지 않습니다.
      </p>

      <div className="mt-5">
        <button
          className="rounded-2xl border border-cyan-300 dark:border-cyan-800 bg-cyan-50 dark:bg-cyan-950 px-4 py-3 text-sm font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-500 hover:bg-cyan-100 dark:hover:bg-cyan-900/60 disabled:cursor-not-allowed disabled:opacity-50"
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
            title="AI 리포트 인증 실패"
            description="토큰이 없거나 만료되었거나, 이 리포트에 접근할 권한이 없습니다."
          />
        </div>
      )}

      {detailResult?.state === "not-found" && (
        <div className="mt-5">
          <Notice
            tone="info"
            title="AI 리포트 상세 없음"
            description="요약은 있지만 전체 리포트가 아직 저장되지 않았거나, 검사 접근 권한을 다시 확인해야 합니다."
          />
        </div>
      )}

      {detailResult?.state === "unavailable" && (
        <div className="mt-5">
          <Notice
            tone="danger"
            title="AI 리포트 요청 실패"
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

type DetailTone = "ok" | "warn" | "danger" | "neutral";

const detailToneDotClassName: Record<DetailTone, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  danger: "bg-rose-500",
  neutral: "bg-slate-300"
};

// 요약 한 줄 + 펼침 패널. 데이터가 늦게 도착해도 문제가 있는 섹션은 자동으로 열리되,
// 사용자가 직접 여닫은 뒤에는 그 선택을 우선한다.
function DetailSection({
  children,
  defaultOpen = false,
  summary,
  title,
  tone = "neutral"
}: {
  children: ReactNode;
  defaultOpen?: boolean;
  summary: string;
  title: string;
  tone?: DetailTone;
}) {
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);
  const isOpen = manualOpen ?? defaultOpen;

  return (
    <div>
      <button
        className="flex w-full items-center gap-3 px-5 py-3.5 text-left transition hover:bg-slate-50 dark:hover:bg-slate-800/60"
        onClick={() => setManualOpen(!isOpen)}
        type="button"
      >
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${detailToneDotClassName[tone]}`} />
        <span className="w-24 shrink-0 text-sm font-bold text-slate-900 dark:text-white">{title}</span>
        <span className="min-w-0 flex-1 truncate text-xs text-slate-500 dark:text-slate-400">{summary}</span>
        <svg
          className={`h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500 transition ${isOpen ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 16 16"
        >
          <path
            d="M4 6l4 4 4-4"
            stroke="currentColor"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="1.5"
          />
        </svg>
      </button>
      {isOpen && <div className="border-t border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 p-4">{children}</div>}
    </div>
  );
}

function getAvailabilitySummary(
  result: AvailabilityResult | null,
  responseTimeThresholdMs: number | null
): { summary: string; tone: DetailTone } {
  if (!result) {
    return { summary: "아직 결과가 없습니다", tone: "neutral" };
  }

  if (!result.is_available) {
    return {
      summary: result.failure_reason ?? "서비스에 연결할 수 없습니다",
      tone: "danger"
    };
  }

  const parts: string[] = [];
  if (result.status_code !== null) {
    parts.push(String(result.status_code));
  }
  if (result.response_time_ms !== null) {
    parts.push(`${result.response_time_ms}ms`);
  }
  parts.push(result.uses_https ? "HTTPS" : "HTTP");
  if (result.redirect_count > 0) {
    parts.push(`리다이렉트 ${result.redirect_count}회`);
  }

  const isSlow =
    result.response_time_ms !== null &&
    responseTimeThresholdMs !== null &&
    responseTimeThresholdMs > 0 &&
    result.response_time_ms > responseTimeThresholdMs;

  return { summary: parts.join(" · "), tone: isSlow ? "warn" : "ok" };
}

function getSslSummary(result: SslResult | null): { summary: string; tone: DetailTone } {
  if (!result) {
    return { summary: "아직 결과가 없습니다", tone: "neutral" };
  }

  if (!result.is_applicable) {
    return { summary: "HTTP 서비스 — 검사 대상 아님", tone: "neutral" };
  }

  if (result.is_valid === true) {
    const expiry =
      result.days_until_expiration === null
        ? "유효"
        : `유효 · 만료까지 ${result.days_until_expiration}일`;
    const isExpiringSoon =
      result.days_until_expiration !== null && result.days_until_expiration < 14;
    return { summary: expiry, tone: isExpiringSoon ? "warn" : "ok" };
  }

  return {
    summary: result.failure_reason ?? "인증서에 문제가 있습니다",
    tone: "danger"
  };
}

function getLighthouseSummary(
  result: LighthouseResult | null,
  qualityScoreThreshold: number | null
): { summary: string; tone: DetailTone } {
  if (!result) {
    return { summary: "아직 결과가 없습니다", tone: "neutral" };
  }

  if (!result.is_successful) {
    return { summary: result.failure_reason ?? "실행 실패", tone: "danger" };
  }

  const parts = [
    `성능 ${result.performance_score ?? "–"}`,
    `접근성 ${result.accessibility_score ?? "–"}`,
    `SEO ${result.seo_score ?? "–"}`,
    `권장사항 ${result.best_practices_score ?? "–"}`
  ];
  const isBelowThreshold =
    result.performance_score !== null &&
    qualityScoreThreshold !== null &&
    result.performance_score < qualityScoreThreshold;

  return { summary: parts.join(" · "), tone: isBelowThreshold ? "warn" : "ok" };
}

function getScenarioSummaryLine(scenarioRuns: ScenarioRun[]): {
  summary: string;
  tone: DetailTone;
} {
  const summary = summarizeScenarioRuns(scenarioRuns);

  if (summary.total === 0) {
    return { summary: "연결된 시나리오 실행 없음", tone: "neutral" };
  }

  if (summary.failed > 0) {
    return { summary: `${summary.total}개 실행 · 실패 ${summary.failed}건`, tone: "danger" };
  }

  if (summary.active > 0) {
    return { summary: `${summary.total}개 실행 · 진행 중 ${summary.active}건`, tone: "warn" };
  }

  if (summary.cancelled > 0) {
    return { summary: `${summary.total}개 실행 · 취소 ${summary.cancelled}건`, tone: "warn" };
  }

  return { summary: `${summary.total}개 실행 · 전부 성공`, tone: "ok" };
}

function DetailSections({
  accessToken,
  checkRun,
  projectId,
  qualityScoreThreshold,
  responseTimeThresholdMs
}: {
  accessToken: string;
  checkRun: CheckRunDetail;
  projectId: string;
  qualityScoreThreshold: number | null;
  responseTimeThresholdMs: number | null;
}) {
  const availability = getAvailabilitySummary(
    checkRun.availability_result,
    responseTimeThresholdMs
  );
  const ssl = getSslSummary(checkRun.ssl_result);
  const lighthouse = getLighthouseSummary(checkRun.lighthouse_result, qualityScoreThreshold);
  const scenario = getScenarioSummaryLine(checkRun.linked_scenario_runs);
  const score = checkRun.score_result;
  const breakdownPreset = score?.score_breakdown?.preset;
  const breakdownSummary = score
    ? `${breakdownPreset ? `${scoringPresetLabel(String(breakdownPreset))} 프리셋 · ` : ""}가중 평균 · 반영 ${score.evaluated_weight}%${
        score.score_breakdown?.gate ? " · 등급 상한 적용" : ""
      }`
    : "아직 계산된 점수가 없습니다";

  return (
    <section className="divide-y divide-slate-100 dark:divide-slate-800 overflow-hidden rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
      <DetailSection
        defaultOpen={availability.tone === "danger"}
        summary={availability.summary}
        title="가용성"
        tone={availability.tone}
      >
        <AvailabilityCard
          responseTimeThresholdMs={responseTimeThresholdMs}
          result={checkRun.availability_result}
        />
      </DetailSection>
      <DetailSection
        defaultOpen={ssl.tone === "danger"}
        summary={ssl.summary}
        title="SSL"
        tone={ssl.tone}
      >
        <SslCard result={checkRun.ssl_result} />
      </DetailSection>
      <DetailSection
        defaultOpen={lighthouse.tone === "danger" || lighthouse.tone === "warn"}
        summary={lighthouse.summary}
        title="Lighthouse"
        tone={lighthouse.tone}
      >
        <LighthouseCard result={checkRun.lighthouse_result} />
      </DetailSection>
      <DetailSection
        defaultOpen={scenario.tone === "danger"}
        summary={scenario.summary}
        title="시나리오"
        tone={scenario.tone}
      >
        <LinkedScenarioRunsCard
          projectId={projectId}
          scenarioRuns={checkRun.linked_scenario_runs}
        />
      </DetailSection>
      <DetailSection
        summary={
          checkRun.artifacts.length === 0
            ? "저장된 산출물 없음"
            : `${checkRun.artifacts.length}개`
        }
        title="산출물"
        tone="neutral"
      >
        <ArtifactCard accessToken={accessToken} artifacts={checkRun.artifacts} />
      </DetailSection>
      <DetailSection
        summary={breakdownSummary}
        title="산출 근거"
        tone={score?.score_breakdown?.gate ? "warn" : "neutral"}
      >
        {score?.score_breakdown ? (
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
            <ScoreBreakdownSection breakdown={score.score_breakdown} />
            <ScoreBandLegend showExcluded />
          </div>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">아직 계산된 점수가 없습니다.</p>
        )}
      </DetailSection>
      <DetailSection
        summary={`대기 ${formatDetailDateTime(checkRun.queued_at)}`}
        title="실행 정보"
        tone="neutral"
      >
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
          <dl className="grid gap-4 text-sm text-slate-600 dark:text-slate-300 sm:grid-cols-2">
            <Metric label="대기 시각" value={formatDetailDateTime(checkRun.queued_at)} />
            <Metric label="시작 시각" value={formatDetailDateTime(checkRun.started_at)} />
            <Metric label="종료 시각" value={formatDetailDateTime(checkRun.finished_at)} />
            <Metric label="갱신 시각" value={formatDetailDateTime(checkRun.updated_at)} />
            <Metric
              label="트리거"
              value={`${triggerSourceLabel(checkRun.trigger_source)}${
                checkRun.deploy_ref ? ` (${checkRun.deploy_ref})` : ""
              }`}
            />
            <Metric label="검사 ID" value={checkRun.id} />
          </dl>
        </div>
      </DetailSection>
    </section>
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
        className="scroll-mt-24 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6"
        id="scenario-runs-card"
      >
        <h2 className="text-xl font-semibold text-slate-900 dark:text-white">연결된 시나리오 실행</h2>
        <p className="mt-3 text-sm leading-6 text-slate-500 dark:text-slate-400">
          이 검사에 연결된 시나리오 실행이 없습니다. 프로젝트의 시나리오 목록에서 수동 실행
          이력과 설정을 확인할 수 있습니다.
        </p>
        <Link
          className="mt-5 inline-flex rounded-xl border border-cyan-300 dark:border-cyan-800 bg-cyan-50 dark:bg-cyan-950 px-3 py-2 text-xs font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-500 hover:bg-cyan-100 dark:hover:bg-cyan-900/60"
          href={`/projects/${projectId}/scenarios`}
        >
          시나리오 목록 보기
        </Link>
      </article>
    );
  }

  return (
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6"
      id="scenario-runs-card"
    >
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-400">
            기능 검사
          </p>
          <h2 className="mt-2 text-xl font-semibold">연결된 시나리오 실행</h2>
        </div>
        <span className="rounded-full bg-cyan-50 dark:bg-cyan-950 px-3 py-1 text-xs font-bold text-cyan-700 dark:text-cyan-400 ring-1 ring-cyan-200 dark:ring-cyan-900">
          {scenarioRuns.length}개
        </span>
      </div>

      <div className={`mb-5 rounded-2xl border p-4 ${getScenarioSummaryClassName(summary)}`}>
        <p className="font-semibold">{getScenarioSummaryTitle(summary)}</p>
        <p className="mt-2 text-sm opacity-80">{getScenarioSummaryDescription(summary)}</p>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-5">
          <Metric label="전체" value={`${summary.total}개`} />
          <Metric label="실패" value={`${summary.failed}개`} />
          <Metric label="진행 중" value={`${summary.active}개`} />
          <Metric label="완료" value={`${summary.completed}개`} />
          <Metric label="취소" value={`${summary.cancelled}개`} />
        </dl>
      </div>

      <ul className="grid gap-3">
        {scenarioRuns.map((scenarioRun) => {
          const isFailed = scenarioRun.status === "FAILED";

          return (
            <li
              className={`rounded-2xl border p-4 text-sm text-slate-600 dark:text-slate-300 ${
                isFailed
                  ? "border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950"
                  : "border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50"
              }`}
              key={scenarioRun.id}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <p className="font-semibold text-slate-900 dark:text-white">시나리오 실행</p>
                <ScenarioRunStatusBadge status={scenarioRun.status} />
              </div>
              {isFailed && (
                <p className="mt-4 rounded-2xl border border-rose-200 dark:border-rose-900 bg-rose-100 dark:bg-rose-950 p-3 text-sm text-rose-800 dark:text-rose-300">
                  우선 확인 필요: {scenarioRun.failure_reason ?? "실패 사유가 기록되지 않았습니다."}
                </p>
              )}
              <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Metric label="트리거" value={triggerSourceLabel(scenarioRun.trigger_source)} />
                <Metric label="소요 시간" value={formatMilliseconds(scenarioRun.duration_ms)} />
                <Metric label="대기 시각" value={formatDetailDateTime(scenarioRun.queued_at)} />
                <Metric label="시작 시각" value={formatDetailDateTime(scenarioRun.started_at)} />
                <Metric label="종료 시각" value={formatDetailDateTime(scenarioRun.finished_at)} />
                <Metric label="실패 사유" value={scenarioRun.failure_reason ?? "없음"} />
              </dl>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link
                  className="inline-flex rounded-xl border border-cyan-300 dark:border-cyan-800 bg-cyan-50 dark:bg-cyan-950 px-3 py-2 text-xs font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-500 hover:bg-cyan-100 dark:hover:bg-cyan-900/60"
                  href={`/projects/${projectId}/scenarios/${scenarioRun.scenario_id}/runs/${scenarioRun.id}`}
                >
                  실행 결과 보기
                </Link>
                <Link
                  className="inline-flex rounded-xl border border-slate-200 dark:border-slate-800 px-3 py-2 text-xs font-bold text-slate-700 dark:text-slate-200 transition hover:border-cyan-400 hover:text-cyan-700 dark:hover:text-cyan-300"
                  href={`/projects/${projectId}/scenarios/${scenarioRun.scenario_id}/runs`}
                >
                  실행 목록 보기
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
    return `실패한 시나리오 실행 ${summary.failed}개`;
  }

  if (summary.active > 0) {
    return "시나리오 실행 대기 또는 진행 중";
  }

  if (summary.cancelled > 0) {
    return "취소된 시나리오 실행 포함";
  }

  return "연결된 시나리오 실행 모두 성공";
}

function getScenarioSummaryDescription(summary: ScenarioRunSummary) {
  if (summary.failed > 0) {
    return "핵심 사용자 흐름 실패는 배포 위험 판단에서 우선 확인해야 할 신호입니다. 상세 step 결과와 screenshot 근거를 확인하세요.";
  }

  if (summary.active > 0) {
    return "아직 종료되지 않은 시나리오 실행이 있어 기능 안정성 판단이 확정되지 않았습니다.";
  }

  if (summary.cancelled > 0) {
    return "취소된 시나리오 실행은 성공 근거로 볼 수 없으므로 수동 확인 또는 재실행이 필요합니다.";
  }

  return "연결된 시나리오 실행이 모두 완료되어 기능 안정성 판단 근거로 사용할 수 있습니다.";
}

function getScenarioSummaryClassName(summary: ScenarioRunSummary) {
  if (summary.failed > 0) {
    return "border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950 text-rose-800 dark:text-rose-300";
  }

  if (summary.active > 0) {
    return "border-cyan-200 dark:border-cyan-900 bg-cyan-50 dark:bg-cyan-950 text-cyan-700 dark:text-cyan-400";
  }

  if (summary.cancelled > 0) {
    return "border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950 text-amber-800 dark:text-amber-300";
  }

  return "border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300";
}

export function AvailabilityCard({
  responseTimeThresholdMs,
  result
}: {
  responseTimeThresholdMs: number | null;
  result: AvailabilityResult | null;
}) {
  if (!result) {
    return <EmptyResultCard title="가용성" description="아직 가용성 결과가 없습니다." />;
  }

  const responseTimeMs = result.response_time_ms;
  const thresholdMs =
    responseTimeThresholdMs !== null && responseTimeThresholdMs > 0
      ? responseTimeThresholdMs
      : null;
  const showResponseTimeBar = responseTimeMs !== null && thresholdMs !== null;

  return (
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6"
      id="availability-card"
    >
      <ResultHeader
        title="가용성"
        isHealthy={result.is_available}
        healthyLabel="사용 가능"
        unhealthyLabel="사용 불가"
      />
      <dl className="mt-5 grid gap-4 text-sm text-slate-600 dark:text-slate-300 sm:grid-cols-2">
        <Metric
          hint="서버가 반환한 HTTP 상태 코드입니다 — 200이면 정상 응답."
          label="상태 코드"
          value={formatNullable(result.status_code)}
        />
        {!showResponseTimeBar && (
          <Metric
            hint="요청 후 첫 응답을 받기까지 걸린 시간입니다."
            label="응답 시간"
            value={formatMilliseconds(result.response_time_ms)}
          />
        )}
        <Metric
          hint="최종 페이지에 도달할 때까지 거친 리다이렉트 횟수입니다."
          label="리다이렉트"
          value={String(result.redirect_count)}
        />
        <Metric
          hint="암호화된 HTTPS로 서비스되고 있는지 여부입니다."
          label="HTTPS"
          value={result.uses_https ? "사용" : "미사용"}
        />
        <Metric
          hint="제한 시간 안에 응답하지 못했는지 여부입니다."
          label="시간 초과"
          value={result.timed_out ? "예" : "아니오"}
        />
        <Metric label="실패 사유" value={result.failure_reason ?? "없음"} />
      </dl>
      {showResponseTimeBar && (
        <div className="mt-5 border-t border-slate-200 dark:border-slate-800 pt-4">
          <ThresholdBar
            goodLabel={`임계값 ${formatMilliseconds(thresholdMs)}`}
            goodTo={thresholdMs}
            hint={`요청 후 첫 응답을 받기까지 걸린 시간입니다. 프로젝트 임계값(${formatMilliseconds(
              thresholdMs
            )}) 이내가 목표입니다.`}
            label="응답 시간"
            max={Math.max(thresholdMs * 2.5, responseTimeMs * 1.15)}
            midLabel={formatMilliseconds(thresholdMs * 2)}
            midTo={thresholdMs * 2}
            value={responseTimeMs}
            valueLabel={formatMilliseconds(responseTimeMs)}
          />
        </div>
      )}
      <AdviceList items={buildAvailabilityAdvice(result, responseTimeThresholdMs)} />
      <p className="mt-5 break-all text-xs text-slate-500 dark:text-slate-400">
        최종 URL: {result.final_url ?? "없음"}
      </p>
    </article>
  );
}

function SslCard({ result }: { result: SslResult | null }) {
  if (!result) {
    return <EmptyResultCard title="SSL" description="아직 SSL 인증서 검사 결과가 없습니다." />;
  }

  const isHealthy = result.is_applicable ? result.is_valid === true : true;

  return (
    <article
      className="scroll-mt-24 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6"
      id="ssl-card"
    >
      <ResultHeader
        title="SSL"
        isHealthy={isHealthy}
        healthyLabel={result.is_applicable ? "유효" : "대상 아님"}
        unhealthyLabel="문제 있음"
      />
      <dl className="mt-5 grid gap-4 text-sm text-slate-600 dark:text-slate-300 sm:grid-cols-2">
        <Metric
          hint="HTTPS를 사용하는 서비스만 인증서 검사 대상이 됩니다."
          label="검사 대상"
          value={result.is_applicable ? "예" : "아니오"}
        />
        <Metric
          hint="인증서가 신뢰할 수 있고 만료되지 않았는지 여부입니다."
          label="유효 여부"
          value={formatBoolean(result.is_valid)}
        />
        <Metric label="만료 시각" value={formatDetailDateTime(result.expires_at)} />
        <Metric
          label="남은 기간"
          value={
            result.days_until_expiration === null
              ? "알 수 없음"
              : `${result.days_until_expiration}일`
          }
        />
        <Metric label="실패 사유" value={result.failure_reason ?? "없음"} />
      </dl>
      <AdviceList items={buildSslAdvice(result)} />
      <p className="mt-5 break-all text-xs text-slate-500 dark:text-slate-400">서비스 URL: {result.service_url}</p>
    </article>
  );
}

function AdviceList({ items }: { items: string[] }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div className="mt-5 rounded-2xl border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-700 dark:text-amber-300">권장 조치</p>
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
      className="scroll-mt-24 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6"
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
          label="성능"
          score={result.performance_score}
        />
        <RingGauge
          hint="색 대비, 스크린 리더 지원 같은 접근성 기준 점수입니다. (100점 만점)"
          label="접근성"
          score={result.accessibility_score}
        />
        <RingGauge
          hint="검색 엔진이 페이지를 잘 이해할 수 있는지에 대한 점수입니다. (100점 만점)"
          label="SEO"
          score={result.seo_score}
        />
        <RingGauge
          hint="웹 개발 권장사항을 얼마나 지키는지에 대한 점수입니다. (100점 만점)"
          label="모범 사례"
          score={result.best_practices_score}
        />
      </div>
      <ScoreBandLegend />
      {(result.largest_contentful_paint_ms !== null ||
        result.cumulative_layout_shift !== null ||
        result.total_blocking_time_ms !== null) && (
        <div className="mt-6 grid gap-5 border-t border-slate-200 dark:border-slate-800 pt-5">
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
        <p className="mt-5 break-keep rounded-2xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950 p-3 text-sm leading-6 text-rose-800 dark:text-rose-300">
          실패 사유: {result.failure_reason}
        </p>
      )}
      <LighthouseTopAuditList audits={result.top_audits} isSuccessful={result.is_successful} />
      <p className="mt-5 break-all text-xs text-slate-500 dark:text-slate-400">서비스 URL: {result.service_url}</p>
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
      <p className="mt-5 rounded-2xl border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950 p-3 text-sm text-emerald-800 dark:text-emerald-300">
        Lighthouse가 발견한 주요 개선 기회가 없습니다.
      </p>
    );
  }

  return (
    <div className="mt-5 border-t border-slate-200 dark:border-slate-800 pt-4">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-400">
        개선 Top {audits.length}
      </p>
      <ol className="mt-3 grid gap-2">
        {audits.map((audit, index) => {
          const impact = formatAuditImpact(audit);

          return (
            <li className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-3" key={audit.id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="text-sm font-semibold leading-5 text-slate-900 dark:text-white">
                  {index + 1}. {audit.title}
                </p>
                <Badge label={formatAuditCategory(audit.category)} />
              </div>
              {impact && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{impact}</p>}
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
    return <EmptyResultCard title="산출물" description="아직 저장된 산출물 정보가 없습니다." />;
  }

  return (
    <article className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">산출물</h2>
        <span className="rounded-full bg-cyan-50 dark:bg-cyan-950 px-3 py-1 text-xs font-bold text-cyan-700 dark:text-cyan-400 ring-1 ring-cyan-200 dark:ring-cyan-900">
          {artifacts.length}개
        </span>
      </div>
      <ul className="grid gap-3">
        {artifacts.map((artifact) => (
          <li
            className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4 text-sm text-slate-600 dark:text-slate-300"
            key={artifact.id}
          >
            <p className="font-semibold text-slate-900 dark:text-white">{artifact.artifact_type}</p>
            <dl className="mt-3 grid gap-3 sm:grid-cols-2">
              <Metric label="크기" value={formatBytes(artifact.size_bytes)} />
              <Metric label="생성 시각" value={formatDetailDateTime(artifact.created_at)} />
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
    <article className="rounded-3xl border border-dashed border-slate-200 dark:border-slate-800 bg-white/60 dark:bg-slate-900/60 p-6">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">{description}</p>
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
            ? "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 ring-emerald-200 dark:ring-emerald-900"
            : "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900"
        }`}
      >
        {isHealthy ? healthyLabel : unhealthyLabel}
      </span>
    </div>
  );
}

function getRiskBadgeClassName(risk: ScoreResult["deployment_risk"]) {
  if (risk === "STABLE") {
    return "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 ring-emerald-200 dark:ring-emerald-900";
  }

  if (risk === "RISK") {
    return "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900";
  }

  return "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 ring-amber-200 dark:ring-amber-900";
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
