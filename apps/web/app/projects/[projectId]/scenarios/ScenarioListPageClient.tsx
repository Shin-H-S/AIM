"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createScenarioRun,
  fetchScenarios,
  getApiBaseUrl,
  type CreateScenarioRunResult,
  type ScenarioListResult,
  type TestScenario,
  type TestStep,
  type TestStepAction
} from "@/lib/api";
import { clearStoredAccessTokenIfMatches, getStoredAccessToken } from "@/lib/auth";

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

export function ScenarioListPageClient({ projectId }: { projectId: string }) {
  const [accessToken, setAccessToken] = useState("");
  const [result, setResult] = useState<ScenarioListResult | null>(null);
  const [createdRunResult, setCreatedRunResult] = useState<CreateScenarioRunResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [hasCheckedStoredToken, setHasCheckedStoredToken] = useState(false);
  const [creatingScenarioId, setCreatingScenarioId] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const trimmedToken = accessToken.trim();
  const scenarios = result?.state === "success" ? result.scenarios : [];

  const loadScenarios = useCallback(async (token: string) => {
    const normalizedToken = token.trim();

    if (!normalizedToken) {
      setResult(null);
      return;
    }

    setIsLoading(true);
    const nextResult = await fetchScenarios({
      projectId,
      accessToken: normalizedToken
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(normalizedToken);
    }

    setResult(nextResult);
    setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
    setIsLoading(false);
  }, [projectId]);

  const refresh = useCallback(async () => {
    await loadScenarios(trimmedToken);
  }, [loadScenarios, trimmedToken]);

  const requestScenarioRun = useCallback(
    async (scenarioId: string) => {
      if (!trimmedToken) {
        return;
      }

      setCreatingScenarioId(scenarioId);
      const nextResult = await createScenarioRun({
        projectId,
        scenarioId,
        accessToken: trimmedToken
      });

      if (nextResult.state === "unauthorized") {
        clearStoredAccessTokenIfMatches(trimmedToken);
      }

      setCreatedRunResult(nextResult);
      setCreatingScenarioId(null);
    },
    [projectId, trimmedToken]
  );

  useEffect(() => {
    const storedAccessToken = getStoredAccessToken();

    queueMicrotask(() => {
      setHasCheckedStoredToken(true);

      if (!storedAccessToken) {
        return;
      }

      setAccessToken(storedAccessToken);
      void loadScenarios(storedAccessToken);
    });
  }, [loadScenarios]);

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
              AIM Scenarios
            </p>
            <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
              Scenario 목록
            </h1>
            <p className="mt-4 text-sm leading-6 text-slate-300">
              이 화면은 <code className="text-cyan-200">{apiBaseUrlLabel}</code>의 Scenario
              API를 사용해서 핵심 사용자 흐름 목록을 조회하고, 수동 ScenarioRun을 생성합니다.
            </p>
          </div>

          <Identifier label="Project ID" value={projectId} />

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
              {isLoading ? "조회 중" : "Scenario 조회"}
            </button>
          </form>
        </header>

        {!hasCheckedStoredToken && (
          <Notice
            tone="info"
            title="로그인 세션 확인 중"
            description="저장된 로그인 세션이 있으면 자동으로 Scenario 목록을 조회합니다."
          />
        )}

        {hasCheckedStoredToken && !trimmedToken && (
          <Notice
            tone="info"
            title="인증 토큰이 필요합니다"
            description="로그인 페이지에서 먼저 로그인하거나, access token을 직접 입력하세요."
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
            title="프로젝트를 찾을 수 없습니다"
            description="Project ID 또는 현재 사용자 권한을 확인하세요."
          />
        )}

        {result?.state === "unavailable" && (
          <Notice
            tone="danger"
            title="API 요청 실패"
            description="API 서버 실행 상태와 NEXT_PUBLIC_API_URL 설정을 확인하세요."
          />
        )}

        {createdRunResult?.state === "success" && (
          <Notice
            tone="info"
            title="ScenarioRun 생성 완료"
            description={`새 ScenarioRun이 ${createdRunResult.scenarioRun.status} 상태로 생성되었습니다.`}
            href={`/projects/${projectId}/scenarios/${createdRunResult.scenarioRun.scenario_id}/runs/${createdRunResult.scenarioRun.id}`}
            hrefLabel="결과 페이지 열기"
          />
        )}

        {createdRunResult?.state === "conflict" && (
          <Notice
            tone="danger"
            title="ScenarioRun 생성 실패"
            description="비활성 scenario는 실행할 수 없습니다."
          />
        )}

        {createdRunResult?.state === "unauthorized" && (
          <Notice
            tone="danger"
            title="ScenarioRun 생성 인증 실패"
            description="토큰이 없거나 만료되었거나, 이 프로젝트에 접근할 권한이 없습니다."
          />
        )}

        {createdRunResult?.state === "not-found" && (
          <Notice
            tone="danger"
            title="ScenarioRun 생성 대상 없음"
            description="Project ID 또는 Scenario ID를 확인하세요."
          />
        )}

        {createdRunResult?.state === "unavailable" && (
          <Notice
            tone="danger"
            title="ScenarioRun 생성 요청 실패"
            description="API 서버 또는 queue 상태를 확인하세요."
          />
        )}

        {result?.state === "success" && (
          <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold">저장된 Scenario</h2>
                <p className="mt-2 text-sm text-slate-400">
                  마지막 조회: {lastUpdatedAt ?? "아직 없음"}
                </p>
              </div>
              <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-300 ring-1 ring-cyan-400/20">
                {scenarios.length}개
              </span>
            </div>

            {scenarios.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-5 text-sm text-slate-400">
                아직 생성된 scenario가 없습니다. API로 scenario를 먼저 등록하세요.
              </p>
            ) : (
              <ul className="grid gap-4">
                {scenarios.map((scenario) => (
                  <ScenarioCard
                    creatingScenarioId={creatingScenarioId}
                    key={scenario.id}
                    onRun={() => void requestScenarioRun(scenario.id)}
                    scenario={scenario}
                  />
                ))}
              </ul>
            )}
          </section>
        )}
      </section>
    </main>
  );
}

function ScenarioCard({
  scenario,
  creatingScenarioId,
  onRun
}: {
  scenario: TestScenario;
  creatingScenarioId: string | null;
  onRun: () => void;
}) {
  const isCreating = creatingScenarioId === scenario.id;

  return (
    <li className="rounded-2xl border border-white/10 bg-slate-900/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-lg font-semibold text-slate-100">{scenario.name}</h3>
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${
                scenario.is_active
                  ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20"
                  : "bg-slate-700 text-slate-300 ring-white/10"
              }`}
            >
              {scenario.is_active ? "활성" : "비활성"}
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-400">
            {scenario.description ?? "설명이 없습니다."}
          </p>
          <p className="mt-3 break-all font-mono text-xs text-slate-500">{scenario.id}</p>
        </div>
        <button
          className="rounded-2xl bg-cyan-300 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!scenario.is_active || isCreating}
          onClick={onRun}
          type="button"
        >
          {isCreating ? "실행 생성 중" : "ScenarioRun 생성"}
        </button>
      </div>

      <div className="mt-5">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          Steps
        </p>
        <ol className="grid gap-2">
          {scenario.steps.map((step) => (
            <StepRow key={step.id} step={step} />
          ))}
        </ol>
      </div>
    </li>
  );
}

function StepRow({ step }: { step: TestStep }) {
  return (
    <li className="rounded-2xl border border-white/10 bg-slate-950/60 p-3 text-sm text-slate-300">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-medium text-slate-100">
          #{step.step_order} {actionLabels[step.action]}
        </p>
        <span
          className={`rounded-full px-2 py-1 text-[11px] font-bold ring-1 ${
            step.is_critical
              ? "bg-rose-400/10 text-rose-300 ring-rose-400/20"
              : "bg-slate-700 text-slate-300 ring-white/10"
          }`}
        >
          {step.is_critical ? "critical" : "non-critical"}
        </span>
      </div>
      <dl className="mt-3 grid gap-3 sm:grid-cols-3">
        <Metric label="Target" value={step.target ?? "없음"} />
        <Metric label="Value" value={step.value ?? "없음"} />
        <Metric label="Timeout" value={step.timeout_ms === null ? "기본값" : `${step.timeout_ms}ms`} />
      </dl>
    </li>
  );
}

function Identifier({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-sm text-slate-300">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
        {label}
      </p>
      <p className="break-all font-mono text-xs text-slate-200">{value}</p>
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
  description,
  href,
  hrefLabel
}: {
  tone: "info" | "danger";
  title: string;
  description: string;
  href?: string;
  hrefLabel?: string;
}) {
  const className =
    tone === "info"
      ? "border-cyan-400/20 bg-cyan-400/10 text-cyan-100"
      : "border-rose-400/20 bg-rose-400/10 text-rose-100";

  return (
    <article className={`rounded-3xl border p-6 ${className}`}>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm opacity-80">{description}</p>
      {href && hrefLabel && (
        <a className="mt-4 inline-flex text-sm font-bold underline" href={href}>
          {hrefLabel}
        </a>
      )}
    </article>
  );
}
