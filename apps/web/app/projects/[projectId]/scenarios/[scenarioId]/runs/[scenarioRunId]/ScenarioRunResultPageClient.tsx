"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArtifactDownloadButton } from "@/components/ArtifactDownloadButton";
import { ArtifactImagePreview } from "@/components/ArtifactImagePreview";
import {
  fetchScenarioRunDetail,
  getApiBaseUrl,
  type ConsoleError,
  type NetworkFailure,
  type ScenarioRunDetail,
  type ScenarioRunDetailResult,
  type ScenarioRunStatus,
  type StepResult,
  type StepResultStatus,
  type TestStepAction
} from "@/lib/api";

const POLLING_INTERVAL_MS = 3_000;
const ACTIVE_STATUSES = new Set<ScenarioRunStatus>(["QUEUED", "RUNNING"]);

const statusLabels: Record<ScenarioRunStatus, string> = {
  QUEUED: "대기 중",
  RUNNING: "실행 중",
  COMPLETED: "완료",
  FAILED: "실패",
  CANCELLED: "취소됨"
};

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

export function ScenarioRunResultPageClient({
  projectId,
  scenarioId,
  scenarioRunId
}: {
  projectId: string;
  scenarioId: string;
  scenarioRunId: string;
}) {
  const [accessToken, setAccessToken] = useState("");
  const [result, setResult] = useState<ScenarioRunDetailResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const trimmedToken = accessToken.trim();
  const scenarioRun = result?.state === "success" ? result.scenarioRun : null;
  const shouldPoll = scenarioRun ? ACTIVE_STATUSES.has(scenarioRun.status) : false;

  const refresh = useCallback(async () => {
    if (!trimmedToken) {
      setResult(null);
      return;
    }

    setIsLoading(true);
    const nextResult = await fetchScenarioRunDetail({
      projectId,
      scenarioId,
      scenarioRunId,
      accessToken: trimmedToken
    });
    setResult(nextResult);
    setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
    setIsLoading(false);
  }, [projectId, scenarioId, scenarioRunId, trimmedToken]);

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
              AIM Scenario Result
            </p>
            <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
              ScenarioRun 결과
            </h1>
            <p className="mt-4 text-sm leading-6 text-slate-300">
              이 화면은 <code className="text-cyan-200">{apiBaseUrlLabel}</code>의
              ScenarioRun 단건 API를 polling해서 step 결과와 실패 근거를 보여줍니다.
            </p>
          </div>

          <div className="grid gap-3 text-sm text-slate-300 md:grid-cols-3">
            <Identifier label="Project ID" value={projectId} />
            <Identifier label="Scenario ID" value={scenarioId} />
            <Identifier label="ScenarioRun ID" value={scenarioRunId} />
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
            title="ScenarioRun을 찾을 수 없습니다"
            description="Project ID, Scenario ID, ScenarioRun ID 또는 현재 사용자 권한을 확인하세요."
          />
        )}

        {result?.state === "unavailable" && (
          <Notice
            tone="danger"
            title="API 요청 실패"
            description="API 서버 실행 상태와 NEXT_PUBLIC_API_URL 설정을 확인하세요."
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

            <StepResultsCard accessToken={trimmedToken} stepResults={scenarioRun.step_results} />

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
  scenarioRun,
  shouldPoll,
  lastUpdatedAt
}: {
  scenarioRun: ScenarioRunDetail;
  shouldPoll: boolean;
  lastUpdatedAt: string | null;
}) {
  const badgeClassName = getStatusBadgeClassName(scenarioRun.status);

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">실행 상태</h2>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${badgeClassName}`}>
          {statusLabels[scenarioRun.status]}
        </span>
      </div>
      <dl className="grid gap-4 text-sm text-slate-300 sm:grid-cols-2">
        <Metric label="Trigger" value={scenarioRun.trigger_source} />
        <Metric label="Linked CheckRun" value={scenarioRun.check_run_id ?? "없음"} />
        <Metric label="Polling" value={shouldPoll ? "자동 새로고침 중" : "중지됨"} />
        <Metric label="Duration" value={formatMilliseconds(scenarioRun.duration_ms)} />
        <Metric label="Failure" value={scenarioRun.failure_reason ?? "없음"} />
        <Metric label="Last refresh" value={lastUpdatedAt ?? "아직 없음"} />
      </dl>
    </article>
  );
}

function TimelineCard({ scenarioRun }: { scenarioRun: ScenarioRunDetail }) {
  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <h2 className="mb-5 text-xl font-semibold">타임라인</h2>
      <dl className="grid gap-4 text-sm text-slate-300">
        <Metric label="Queued" value={formatDateTime(scenarioRun.queued_at)} />
        <Metric label="Started" value={formatDateTime(scenarioRun.started_at)} />
        <Metric label="Finished" value={formatDateTime(scenarioRun.finished_at)} />
        <Metric label="Updated" value={formatDateTime(scenarioRun.updated_at)} />
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
        title="Step results"
        description="아직 저장된 step-level 결과가 없습니다."
      />
    );
  }

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Step results</h2>
        <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-300 ring-1 ring-cyan-400/20">
          {stepResults.length}개
        </span>
      </div>
      <ol className="grid gap-3">
        {stepResults.map((stepResult) => (
          <li
            className="rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-sm text-slate-300"
            key={stepResult.id}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-slate-100">
                  #{stepResult.step_order} {actionLabels[stepResult.action]}
                </p>
                <p className="mt-2 break-all font-mono text-xs text-slate-400">
                  {stepResult.target ?? "target 없음"}
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
            <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Metric label="Duration" value={formatMilliseconds(stepResult.duration_ms)} />
              <Metric label="Started" value={formatDateTime(stepResult.started_at)} />
              <Metric label="Finished" value={formatDateTime(stepResult.finished_at)} />
              <Metric
                label="Screenshot artifact"
                value={stepResult.failure_screenshot_artifact_id ?? "없음"}
              />
            </dl>
            {stepResult.error_message && (
              <p className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 p-3 text-sm text-rose-100">
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
                  alt={`Step #${stepResult.step_order} 실패 스크린샷`}
                />
              </div>
            )}
          </li>
        ))}
      </ol>
    </article>
  );
}

function ConsoleErrorsCard({ consoleErrors }: { consoleErrors: ConsoleError[] }) {
  if (consoleErrors.length === 0) {
    return (
      <EmptyResultCard
        title="Console errors"
        description="저장된 browser console error가 없습니다."
      />
    );
  }

  return (
    <EvidenceListCard
      count={consoleErrors.length}
      title="Console errors"
      items={consoleErrors.map((consoleError) => ({
        id: consoleError.id,
        title: consoleError.message,
        subtitle: consoleError.source_url ?? "source 없음",
        details: [
          ["Level", consoleError.level],
          ["Line", formatNullable(consoleError.line_number)],
          ["Column", formatNullable(consoleError.column_number)],
          ["Created", formatDateTime(consoleError.created_at)]
        ]
      }))}
    />
  );
}

function NetworkFailuresCard({ networkFailures }: { networkFailures: NetworkFailure[] }) {
  if (networkFailures.length === 0) {
    return (
      <EmptyResultCard
        title="Network failures"
        description="저장된 failed network request가 없습니다."
      />
    );
  }

  return (
    <EvidenceListCard
      count={networkFailures.length}
      title="Network failures"
      items={networkFailures.map((networkFailure) => ({
        id: networkFailure.id,
        title: networkFailure.request_url,
        subtitle: networkFailure.failure_text ?? "failure text 없음",
        details: [
          ["Method", networkFailure.method],
          ["Resource", networkFailure.resource_type ?? "알 수 없음"],
          ["Created", formatDateTime(networkFailure.created_at)]
        ]
      }))}
    />
  );
}

function EvidenceListCard({
  title,
  count,
  items
}: {
  title: string;
  count: number;
  items: {
    id: string;
    title: string;
    subtitle: string;
    details: [string, string][];
  }[];
}) {
  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">{title}</h2>
        <span className="rounded-full bg-rose-400/10 px-3 py-1 text-xs font-bold text-rose-300 ring-1 ring-rose-400/20">
          {count}개
        </span>
      </div>
      <ul className="grid gap-3">
        {items.map((item) => (
          <li
            className="rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-sm text-slate-300"
            key={item.id}
          >
            <p className="break-words font-semibold text-slate-100">{item.title}</p>
            <p className="mt-2 break-all font-mono text-xs text-slate-400">{item.subtitle}</p>
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
    <article className="rounded-3xl border border-dashed border-white/10 bg-white/[0.02] p-6">
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="mt-4 text-sm text-slate-400">{description}</p>
    </article>
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

function getStatusBadgeClassName(status: ScenarioRunStatus) {
  if (status === "COMPLETED") {
    return "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20";
  }

  if (status === "FAILED" || status === "CANCELLED") {
    return "bg-rose-400/10 text-rose-300 ring-rose-400/20";
  }

  return "bg-cyan-400/10 text-cyan-300 ring-cyan-400/20";
}

function getStepStatusBadgeClassName(status: StepResultStatus) {
  if (status === "PASSED") {
    return "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20";
  }

  if (status === "FAILED") {
    return "bg-rose-400/10 text-rose-300 ring-rose-400/20";
  }

  return "bg-slate-700 text-slate-300 ring-white/10";
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
