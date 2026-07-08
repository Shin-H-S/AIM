"use client";

import { useCallback, useEffect, useState } from "react";
import { ArtifactDownloadButton } from "@/components/ArtifactDownloadButton";
import { ArtifactImagePreview } from "@/components/ArtifactImagePreview";
import {
  fetchScenarioRunDetail,
  type ConsoleError,
  type NetworkFailure,
  type ScenarioRunDetail,
  type ScenarioRunDetailResult,
  type ScenarioRunStatus,
  type StepResult,
  type StepResultStatus,
  type TestStepAction
} from "@/lib/api";
import { clearStoredAccessTokenIfMatches, getStoredAccessToken } from "@/lib/auth";
import { formatDetailDateTime, formatMilliseconds } from "@/lib/format";
import { triggerSourceLabel } from "@/lib/statusLabels";
import {
  LinkButton,
  LoginRequiredNotice,
  Metric,
  Notice,
  RefreshButton,
  ScenarioRunStatusBadge
} from "@/components/ui";

const POLLING_INTERVAL_MS = 3_000;
const ACTIVE_STATUSES = new Set<ScenarioRunStatus>(["QUEUED", "RUNNING"]);

const stepStatusLabels: Record<StepResultStatus, string> = {
  PASSED: "성공",
  FAILED: "실패",
  SKIPPED: "건너뜀"
};

const actionLabels: Record<TestStepAction, string> = {
  navigate: "페이지 이동",
  click: "클릭",
  fill: "입력",
  wait: "대기",
  assert_element_exists: "요소 존재 확인",
  assert_text_exists: "텍스트 확인",
  assert_url: "URL 확인",
  take_screenshot: "스크린샷"
};

type ScenarioRunResultPageState =
  | { state: "checking" }
  | { state: "signed-out" }
  | ScenarioRunDetailResult;

export function ScenarioRunResultPageClient({
  projectId,
  scenarioId,
  scenarioRunId
}: {
  projectId: string;
  scenarioId: string;
  scenarioRunId: string;
}) {
  const [result, setResult] = useState<ScenarioRunResultPageState>({ state: "checking" });
  const [sessionToken, setSessionToken] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const scenarioRun = result.state === "success" ? result.scenarioRun : null;
  const shouldPoll = scenarioRun ? ACTIVE_STATUSES.has(scenarioRun.status) : false;

  const loadScenarioRun = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (!accessToken) {
      setResult({ state: "signed-out" });
      setSessionToken("");
      return;
    }

    setIsLoading(true);
    const nextResult = await fetchScenarioRunDetail({
      projectId,
      scenarioId,
      scenarioRunId,
      accessToken
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
    }

    setResult(nextResult);
    setSessionToken(accessToken);
    setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
    setIsLoading(false);
  }, [projectId, scenarioId, scenarioRunId]);

  useEffect(() => {
    queueMicrotask(() => {
      void loadScenarioRun();
    });
  }, [loadScenarioRun]);

  useEffect(() => {
    if (!shouldPoll) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void loadScenarioRun();
    }, POLLING_INTERVAL_MS);

    return () => window.clearInterval(intervalId);
  }, [loadScenarioRun, shouldPoll]);

  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <header className="flex flex-col gap-6 rounded-3xl border border-slate-200 bg-white p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-cyan-700">
                AIM 시나리오 결과
              </p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
                시나리오 실행 결과
              </h1>
              <p className="mt-4 text-sm leading-6 text-slate-600">
                시나리오 실행의 단계별 결과와 실패 근거를 보여줍니다. 실행 중에는
                자동으로 새로고침됩니다.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <LinkButton
                href={`/projects/${projectId}/scenarios/${scenarioId}/runs`}
                label="실행 목록"
              />
              <RefreshButton isLoading={isLoading} onClick={() => void loadScenarioRun()} />
            </div>
          </div>
        </header>

        {result.state === "checking" && (
          <Notice
            tone="info"
            title="로그인 세션 확인 중"
            description="저장된 로그인 세션이 있으면 자동으로 시나리오 실행 결과를 조회합니다."
          />
        )}

        {result.state === "signed-out" && <LoginRequiredNotice />}

        {result.state === "unauthorized" && <LoginRequiredNotice expired />}

        {result.state === "not-found" && (
          <Notice
            tone="danger"
            title="시나리오 실행을 찾을 수 없습니다"
            description="프로젝트 ID, 시나리오 ID, 실행 ID 또는 현재 사용자 권한을 확인하세요."
          />
        )}

        {result.state === "unavailable" && (
          <Notice
            tone="danger"
            title="요청 실패"
            description="서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
          />
        )}

        {scenarioRun && (
          <>
            <section className="grid gap-4 lg:grid-cols-[1fr_1fr]">
              <StatusSummary
                scenarioRun={scenarioRun}
                shouldPoll={shouldPoll}
                lastUpdatedAt={lastUpdatedAt}
              />
              <TimelineCard scenarioRun={scenarioRun} />
            </section>

            <StepResultsCard accessToken={sessionToken} stepResults={scenarioRun.step_results} />

            <EvidenceSummaryCard
              consoleErrors={scenarioRun.console_errors}
              networkFailures={scenarioRun.network_failures}
            />

            <section className="grid gap-4 lg:grid-cols-2">
              <ConsoleErrorsCard consoleErrors={scenarioRun.console_errors} />
              <NetworkFailuresCard networkFailures={scenarioRun.network_failures} />
            </section>
          </>
        )}
      </section>
    </main>
  );
}

function StatusSummary({
  scenarioRun,
  shouldPoll,
  lastUpdatedAt
}: {
  scenarioRun: ScenarioRunDetail;
  shouldPoll: boolean;
  lastUpdatedAt: string | null;
}) {
  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">실행 상태</h2>
        <ScenarioRunStatusBadge status={scenarioRun.status} />
      </div>
      <dl className="grid gap-4 text-sm text-slate-600 sm:grid-cols-2">
        <Metric label="트리거" value={triggerSourceLabel(scenarioRun.trigger_source)} />
        <Metric label="소요 시간" value={formatMilliseconds(scenarioRun.duration_ms)} />
        <Metric label="자동 새로고침" value={shouldPoll ? "실행 중" : "중지됨"} />
        <Metric label="마지막 갱신" value={lastUpdatedAt ?? "아직 없음"} />
        <Metric label="실패 사유" value={scenarioRun.failure_reason ?? "없음"} />
      </dl>
    </article>
  );
}

function TimelineCard({ scenarioRun }: { scenarioRun: ScenarioRunDetail }) {
  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6">
      <h2 className="mb-5 text-xl font-semibold">타임라인</h2>
      <dl className="grid gap-4 text-sm text-slate-600">
        <Metric label="대기 시각" value={formatDetailDateTime(scenarioRun.queued_at)} />
        <Metric label="시작 시각" value={formatDetailDateTime(scenarioRun.started_at)} />
        <Metric label="종료 시각" value={formatDetailDateTime(scenarioRun.finished_at)} />
        <Metric label="갱신 시각" value={formatDetailDateTime(scenarioRun.updated_at)} />
      </dl>
    </article>
  );
}

function StepResultsCard({
  accessToken,
  stepResults
}: {
  accessToken: string;
  stepResults: StepResult[];
}) {
  if (stepResults.length === 0) {
    return (
      <EmptyResultCard
        title="단계별 결과"
        description="아직 저장된 단계별 결과가 없습니다."
      />
    );
  }

  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">단계별 결과</h2>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
          {stepResults.length}개
        </span>
      </div>
      <ol className="grid gap-3">
        {stepResults.map((stepResult) => (
          <li
            className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600"
            key={stepResult.id}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-slate-900">
                  #{stepResult.step_order} {actionLabels[stepResult.action]}
                </p>
                <p className="mt-2 break-all font-mono text-xs text-slate-500">
                  {stepResult.target ?? "대상 없음"}
                </p>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${getStepStatusBadgeClassName(
                  stepResult.status
                )}`}
              >
                {stepStatusLabels[stepResult.status]}
              </span>
            </div>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <Metric label="소요 시간" value={formatMilliseconds(stepResult.duration_ms)} />
              <Metric label="시작 시각" value={formatDetailDateTime(stepResult.started_at)} />
              <Metric label="종료 시각" value={formatDetailDateTime(stepResult.finished_at)} />
            </dl>
            {stepResult.error_message && (
              <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
                {stepResult.error_message}
              </p>
            )}
            {stepResult.failure_screenshot_artifact_id && (
              <div className="mt-4 grid gap-3">
                <ArtifactDownloadButton
                  artifactId={stepResult.failure_screenshot_artifact_id}
                  accessToken={accessToken}
                  label="실패 스크린샷 다운로드"
                />
                <ArtifactImagePreview
                  artifactId={stepResult.failure_screenshot_artifact_id}
                  accessToken={accessToken}
                  alt={`단계 #${stepResult.step_order} 실패 스크린샷`}
                />
              </div>
            )}
          </li>
        ))}
      </ol>
    </article>
  );
}

function EvidenceSummaryCard({
  consoleErrors,
  networkFailures
}: {
  consoleErrors: ConsoleError[];
  networkFailures: NetworkFailure[];
}) {
  const totalEvidenceCount = consoleErrors.length + networkFailures.length;
  const hasEvidence = totalEvidenceCount > 0;
  const className = hasEvidence
    ? "border-rose-200 bg-rose-50 text-rose-800"
    : "border-emerald-200 bg-emerald-50 text-emerald-800";

  return (
    <article className={`rounded-3xl border p-6 ${className}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] opacity-80">
            브라우저 근거
          </p>
          <h2 className="mt-3 text-2xl font-bold">
            {hasEvidence ? "추가 실패 근거가 수집되었습니다" : "추가 브라우저 근거 없음"}
          </h2>
          <p className="mt-3 text-sm leading-6 opacity-80">
            {getEvidenceSummaryDescription(consoleErrors, networkFailures)}
          </p>
        </div>
        <span className="rounded-full bg-black/20 px-3 py-1 text-xs font-bold ring-1 ring-slate-200">
          {totalEvidenceCount}개
        </span>
      </div>
      <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-3">
        <Metric label="콘솔 오류" value={`${consoleErrors.length}개`} />
        <Metric label="네트워크 실패" value={`${networkFailures.length}개`} />
        <Metric label="전체 근거" value={`${totalEvidenceCount}개`} />
      </dl>
    </article>
  );
}

function getEvidenceSummaryDescription(
  consoleErrors: ConsoleError[],
  networkFailures: NetworkFailure[]
) {
  if (networkFailures.length > 0 && consoleErrors.length > 0) {
    return "브라우저 콘솔 오류와 실패한 네트워크 요청이 함께 기록되었습니다. 실패 단계와 같은 시간대의 요청 실패를 우선 확인하세요.";
  }

  if (networkFailures.length > 0) {
    return "실패한 네트워크 요청이 기록되었습니다. API, 정적 리소스, 리다이렉트, CORS, 차단된 요청 여부를 상세 카드에서 확인하세요.";
  }

  if (consoleErrors.length > 0) {
    return "브라우저 콘솔 오류(console.error)가 기록되었습니다. 사용자 흐름 실패와 직접 관련된 클라이언트 오류인지 상세 카드에서 확인하세요.";
  }

  return "실행 중 저장된 콘솔 오류 또는 실패한 네트워크 요청이 없습니다.";
}

function ConsoleErrorsCard({ consoleErrors }: { consoleErrors: ConsoleError[] }) {
  if (consoleErrors.length === 0) {
    return (
      <EmptyResultCard
        title="콘솔 오류"
        description="저장된 브라우저 콘솔 오류가 없습니다."
      />
    );
  }

  return (
    <EvidenceListCard
      count={consoleErrors.length}
      description="브라우저에서 수집한 console.error 근거입니다. 메시지, 발생 URL, 줄/열 위치를 확인해 사용자 흐름 실패와의 연관성을 판단하세요."
      title="브라우저 콘솔 오류"
      items={consoleErrors.map((consoleError) => ({
        id: consoleError.id,
        title: consoleError.message,
        subtitle: consoleError.source_url ?? "발생 위치 없음",
        details: [
          ["수준", consoleError.level],
          ["줄", formatNullable(consoleError.line_number)],
          ["열", formatNullable(consoleError.column_number)],
          ["기록 시각", formatDetailDateTime(consoleError.created_at)]
        ]
      }))}
    />
  );
}

function NetworkFailuresCard({ networkFailures }: { networkFailures: NetworkFailure[] }) {
  if (networkFailures.length === 0) {
    return (
      <EmptyResultCard
        title="네트워크 실패"
        description="저장된 실패한 네트워크 요청이 없습니다."
      />
    );
  }

  return (
    <EvidenceListCard
      count={networkFailures.length}
      description="Playwright 실행 중 실패한 네트워크 요청 근거입니다. API 요청 실패나 필수 리소스 로딩 실패 여부를 먼저 확인하세요."
      title="실패한 네트워크 요청"
      items={networkFailures.map((networkFailure) => ({
        id: networkFailure.id,
        title: networkFailure.request_url,
        subtitle: networkFailure.failure_text ?? "실패 사유 없음",
        details: [
          ["메서드", networkFailure.method],
          ["리소스 유형", networkFailure.resource_type ?? "알 수 없음"],
          ["기록 시각", formatDetailDateTime(networkFailure.created_at)]
        ]
      }))}
    />
  );
}

function EvidenceListCard({
  title,
  count,
  description,
  items
}: {
  title: string;
  count: number;
  description: string;
  items: {
    id: string;
    title: string;
    subtitle: string;
    details: [string, string][];
  }[];
}) {
  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-rose-700">
            근거
          </p>
          <h2 className="mt-2 text-xl font-semibold">{title}</h2>
          <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
        </div>
        <span className="rounded-full bg-rose-50 px-3 py-1 text-xs font-bold text-rose-700 ring-1 ring-rose-200">
          {count}개
        </span>
      </div>
      <ul className="grid gap-3">
        {items.map((item) => (
          <li
            className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-slate-600"
            key={item.id}
          >
            <p className="break-words font-semibold text-slate-900">{item.title}</p>
            <p className="mt-2 break-all font-mono text-xs text-slate-500">{item.subtitle}</p>
            <dl className="mt-4 grid gap-3 sm:grid-cols-2">
              {item.details.map(([label, value]) => (
                <Metric key={label} label={label} value={value} />
              ))}
            </dl>
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

function getStepStatusBadgeClassName(status: StepResultStatus) {
  if (status === "PASSED") {
    return "bg-emerald-50 text-emerald-700 ring-emerald-200";
  }

  if (status === "FAILED") {
    return "bg-rose-50 text-rose-700 ring-rose-200";
  }

  return "bg-slate-200 text-slate-600 ring-slate-200";
}

function formatNullable(value: number | null) {
  return value === null ? "없음" : String(value);
}
