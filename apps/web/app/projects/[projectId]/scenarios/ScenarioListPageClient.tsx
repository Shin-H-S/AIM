"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  createScenario,
  createScenarioRun,
  fetchScenarios,
  getApiBaseUrl,
  type CreateScenarioRunResult,
  type ScenarioListResult,
  type TestScenarioPayload,
  type TestStepPayload,
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

const supportedActions: TestStepAction[] = [
  "navigate",
  "click",
  "fill",
  "wait",
  "assert_element_exists",
  "assert_text_exists",
  "assert_url",
  "take_screenshot"
];

const actionHelp: Record<TestStepAction, string> = {
  navigate: "Target에 이동할 URL을 입력합니다.",
  click: "Target에 클릭할 CSS selector를 입력합니다.",
  fill: "Target에 입력 필드 selector, Value에 입력값을 넣습니다.",
  wait: "Timeout에 대기 시간을 ms 단위로 입력합니다.",
  assert_element_exists: "Target에 존재해야 하는 CSS selector를 입력합니다.",
  assert_text_exists: "Value에 화면에 보여야 하는 텍스트를 입력합니다.",
  assert_url: "Value에 기대 URL 또는 URL 조각을 입력합니다.",
  take_screenshot: "추가 입력 없이 현재 화면을 캡처합니다."
};

type ScenarioCreateState =
  | "idle"
  | "creating"
  | "success"
  | "invalid"
  | "unauthorized"
  | "not-found"
  | "unavailable";

type ScenarioStepFormState = {
  id: string;
  action: TestStepAction;
  target: string;
  value: string;
  timeoutMs: string;
  isCritical: boolean;
};

type ScenarioFormState = {
  name: string;
  description: string;
  isActive: boolean;
  steps: ScenarioStepFormState[];
};

export function ScenarioListPageClient({ projectId }: { projectId: string }) {
  const [accessToken, setAccessToken] = useState("");
  const [result, setResult] = useState<ScenarioListResult | null>(null);
  const [createdRunResult, setCreatedRunResult] = useState<CreateScenarioRunResult | null>(null);
  const [scenarioForm, setScenarioForm] = useState<ScenarioFormState>(() =>
    createInitialScenarioForm()
  );
  const [nextStepIndex, setNextStepIndex] = useState(2);
  const [createState, setCreateState] = useState<ScenarioCreateState>("idle");
  const [createMessage, setCreateMessage] = useState<string | null>(null);
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

  const createScenarioFromForm = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setCreateMessage(null);

      if (!trimmedToken) {
        setCreateState("unauthorized");
        setCreateMessage("로그인 세션이 없습니다. 로그인 후 다시 시도하세요.");
        return;
      }

      const payloadResult = buildScenarioPayload(scenarioForm);
      if (!payloadResult.ok) {
        setCreateState("invalid");
        setCreateMessage(payloadResult.message);
        return;
      }

      setCreateState("creating");
      const nextResult = await createScenario({
        projectId,
        accessToken: trimmedToken,
        payload: payloadResult.payload
      });

      if (nextResult.state !== "success") {
        if (nextResult.state === "unauthorized") {
          clearStoredAccessTokenIfMatches(trimmedToken);
        }

        setCreateState(nextResult.state);
        setCreateMessage(scenarioCreateStateMessage[nextResult.state]);
        return;
      }

      setResult((currentResult) =>
        currentResult?.state === "success"
          ? {
              state: "success",
              scenarios: [nextResult.scenario, ...currentResult.scenarios]
            }
          : currentResult
      );
      setScenarioForm(createInitialScenarioForm());
      setNextStepIndex(2);
      setCreateState("success");
      setCreateMessage("Scenario를 생성했습니다. 목록에서 바로 실행할 수 있습니다.");
      setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
    },
    [projectId, scenarioForm, trimmedToken]
  );

  function updateScenarioStep(stepId: string, nextStep: Partial<ScenarioStepFormState>) {
    setScenarioForm((currentForm) => ({
      ...currentForm,
      steps: currentForm.steps.map((step) =>
        step.id === stepId
          ? {
              ...step,
              ...nextStep
            }
          : step
      )
    }));
  }

  function addScenarioStep() {
    setScenarioForm((currentForm) => ({
      ...currentForm,
      steps: [...currentForm.steps, createScenarioStepForm(`step-${nextStepIndex}`)]
    }));
    setNextStepIndex((currentIndex) => currentIndex + 1);
  }

  function removeScenarioStep(stepId: string) {
    setScenarioForm((currentForm) => {
      if (currentForm.steps.length <= 1) {
        return currentForm;
      }

      return {
        ...currentForm,
        steps: currentForm.steps.filter((step) => step.id !== stepId)
      };
    });
  }

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

        {trimmedToken && (
          <ScenarioCreateForm
            createMessage={createMessage}
            createState={createState}
            form={scenarioForm}
            onAddStep={addScenarioStep}
            onChange={setScenarioForm}
            onRemoveStep={removeScenarioStep}
            onSubmit={createScenarioFromForm}
            onUpdateStep={updateScenarioStep}
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
                아직 생성된 scenario가 없습니다. 위 폼으로 첫 critical user flow를 등록하세요.
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

function ScenarioCreateForm({
  createMessage,
  createState,
  form,
  onAddStep,
  onChange,
  onRemoveStep,
  onSubmit,
  onUpdateStep
}: {
  createMessage: string | null;
  createState: ScenarioCreateState;
  form: ScenarioFormState;
  onAddStep: () => void;
  onChange: (form: ScenarioFormState) => void;
  onRemoveStep: (stepId: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onUpdateStep: (stepId: string, nextStep: Partial<ScenarioStepFormState>) => void;
}) {
  return (
    <form
      className="rounded-3xl border border-cyan-300/20 bg-cyan-300/[0.04] p-6"
      onSubmit={onSubmit}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-300">
            Scenario builder
          </p>
          <h2 className="mt-3 text-2xl font-bold">새 Scenario 생성</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
            핵심 사용자 흐름을 step 단위로 작성합니다. destructive action은 MVP 범위에서
            피하고, 로그인·검색·주요 페이지 접근처럼 안전하게 반복 가능한 흐름부터 등록하세요.
          </p>
        </div>
        <button
          className="rounded-2xl border border-cyan-300/30 px-4 py-2 text-sm font-bold text-cyan-100 transition hover:border-cyan-200 hover:bg-cyan-300/10"
          onClick={onAddStep}
          type="button"
        >
          Step 추가
        </button>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_220px]">
        <label className="block" htmlFor="scenario-name">
          <span className="text-sm font-semibold text-slate-300">Scenario name</span>
          <input
            className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition placeholder:text-slate-600 focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
            id="scenario-name"
            maxLength={120}
            onChange={(event) => onChange({ ...form, name: event.target.value })}
            placeholder="Login flow"
            required
            type="text"
            value={form.name}
          />
        </label>

        <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-300 lg:mt-7">
          <input
            checked={form.isActive}
            className="h-4 w-4 accent-cyan-300"
            onChange={(event) => onChange({ ...form, isActive: event.target.checked })}
            type="checkbox"
          />
          Active scenario
        </label>
      </div>

      <label className="mt-4 block" htmlFor="scenario-description">
        <span className="text-sm font-semibold text-slate-300">Description</span>
        <textarea
          className="mt-2 min-h-24 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition placeholder:text-slate-600 focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
          id="scenario-description"
          maxLength={1000}
          onChange={(event) => onChange({ ...form, description: event.target.value })}
          placeholder="이 scenario가 검증하는 핵심 사용자 흐름을 적어두세요."
          value={form.description}
        />
      </label>

      <div className="mt-6 grid gap-4">
        {form.steps.map((step, index) => (
          <ScenarioStepEditor
            canRemove={form.steps.length > 1}
            index={index}
            key={step.id}
            onRemove={() => onRemoveStep(step.id)}
            onUpdate={(nextStep) => onUpdateStep(step.id, nextStep)}
            step={step}
          />
        ))}
      </div>

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <button
          className="rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={createState === "creating"}
          type="submit"
        >
          {createState === "creating" ? "Scenario 생성 중" : "Scenario 생성"}
        </button>
        <p className="text-xs leading-5 text-slate-400">
          생성 후 목록에 바로 추가됩니다. active 상태라면 수동 ScenarioRun을 실행할 수 있습니다.
        </p>
      </div>

      <ScenarioCreateNotice createMessage={createMessage} createState={createState} />
    </form>
  );
}

function ScenarioStepEditor({
  canRemove,
  index,
  onRemove,
  onUpdate,
  step
}: {
  canRemove: boolean;
  index: number;
  onRemove: () => void;
  onUpdate: (step: Partial<ScenarioStepFormState>) => void;
  step: ScenarioStepFormState;
}) {
  return (
    <article className="rounded-2xl border border-white/10 bg-slate-950/70 p-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-slate-100">Step #{index + 1}</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">{actionHelp[step.action]}</p>
        </div>
        <button
          className="rounded-xl border border-white/10 px-3 py-2 text-xs font-bold text-slate-300 transition hover:border-rose-300/50 hover:text-rose-100 disabled:cursor-not-allowed disabled:opacity-40"
          disabled={!canRemove}
          onClick={onRemove}
          type="button"
        >
          삭제
        </button>
      </div>

      <div className="grid gap-3 lg:grid-cols-[220px_1fr_1fr_180px]">
        <label className="block" htmlFor={`scenario-step-action-${step.id}`}>
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
            Action
          </span>
          <select
            className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-900 px-3 py-3 text-sm text-slate-100 outline-none focus:border-cyan-300/60"
            id={`scenario-step-action-${step.id}`}
            onChange={(event) => onUpdate({ action: event.target.value as TestStepAction })}
            value={step.action}
          >
            {supportedActions.map((action) => (
              <option key={action} value={action}>
                {actionLabels[action]}
              </option>
            ))}
          </select>
        </label>

        <StepInput
          label="Target"
          onChange={(value) => onUpdate({ target: value })}
          placeholder={getTargetPlaceholder(step.action)}
          value={step.target}
        />
        <StepInput
          label="Value"
          onChange={(value) => onUpdate({ value })}
          placeholder={getValuePlaceholder(step.action)}
          value={step.value}
        />
        <StepInput
          label="Timeout ms"
          onChange={(value) => onUpdate({ timeoutMs: value })}
          placeholder={step.action === "wait" ? "1000" : "선택"}
          type="number"
          value={step.timeoutMs}
        />
      </div>

      <label className="mt-4 flex items-center gap-3 text-sm text-slate-300">
        <input
          checked={step.isCritical}
          className="h-4 w-4 accent-cyan-300"
          onChange={(event) => onUpdate({ isCritical: event.target.checked })}
          type="checkbox"
        />
        Critical step
      </label>
    </article>
  );
}

function StepInput({
  label,
  onChange,
  placeholder,
  type = "text",
  value
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  type?: "text" | "number";
  value: string;
}) {
  return (
    <label className="block">
      <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
        {label}
      </span>
      <input
        className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-900 px-3 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-300/60"
        min={type === "number" ? 1 : undefined}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        type={type}
        value={value}
      />
    </label>
  );
}

function ScenarioCreateNotice({
  createMessage,
  createState
}: {
  createMessage: string | null;
  createState: ScenarioCreateState;
}) {
  if (createState === "idle" || createState === "creating" || !createMessage) {
    return null;
  }

  return (
    <div className="mt-5">
      <Notice
        description={createMessage}
        title={createState === "success" ? "Scenario 생성 완료" : "Scenario 생성 실패"}
        tone={createState === "success" ? "info" : "danger"}
      />
    </div>
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

function createScenarioStepForm(id: string): ScenarioStepFormState {
  return {
    id,
    action: "navigate",
    target: "",
    value: "",
    timeoutMs: "",
    isCritical: true
  };
}

function createInitialScenarioForm(): ScenarioFormState {
  return {
    name: "",
    description: "",
    isActive: true,
    steps: [createScenarioStepForm("step-1")]
  };
}

type ScenarioPayloadBuildResult =
  | {
      ok: true;
      payload: TestScenarioPayload;
    }
  | {
      ok: false;
      message: string;
    };

function buildScenarioPayload(form: ScenarioFormState): ScenarioPayloadBuildResult {
  const name = form.name.trim();
  if (!name) {
    return {
      ok: false,
      message: "Scenario name을 입력하세요."
    };
  }

  if (form.steps.length === 0) {
    return {
      ok: false,
      message: "Scenario에는 최소 1개 이상의 step이 필요합니다."
    };
  }

  const steps: TestStepPayload[] = [];

  for (const [index, step] of form.steps.entries()) {
    const target = normalizeOptionalText(step.target);
    const value = normalizeOptionalText(step.value);
    const timeoutResult = normalizeTimeout(step.timeoutMs);

    if (!timeoutResult.ok) {
      return {
        ok: false,
        message: `Step #${index + 1}: timeout은 1~120000ms 사이의 정수여야 합니다.`
      };
    }

    if (requiresTarget(step.action) && !target) {
      return {
        ok: false,
        message: `Step #${index + 1}: ${actionLabels[step.action]} action은 target이 필요합니다.`
      };
    }

    if (step.action === "fill" && !value) {
      return {
        ok: false,
        message: `Step #${index + 1}: 입력 action은 value가 필요합니다.`
      };
    }

    if (requiresValue(step.action) && !value) {
      return {
        ok: false,
        message: `Step #${index + 1}: ${actionLabels[step.action]} action은 value가 필요합니다.`
      };
    }

    if (step.action === "wait" && timeoutResult.value === null) {
      return {
        ok: false,
        message: `Step #${index + 1}: 대기 action은 timeout ms가 필요합니다.`
      };
    }

    steps.push({
      action: step.action,
      target,
      value,
      timeout_ms: timeoutResult.value,
      is_critical: step.isCritical
    });
  }

  return {
    ok: true,
    payload: {
      name,
      description: normalizeOptionalText(form.description),
      is_active: form.isActive,
      steps
    }
  };
}

function normalizeOptionalText(value: string): string | null {
  const normalized = value.trim();
  return normalized ? normalized : null;
}

function normalizeTimeout(value: string):
  | {
      ok: true;
      value: number | null;
    }
  | {
      ok: false;
    } {
  const normalized = value.trim();
  if (!normalized) {
    return {
      ok: true,
      value: null
    };
  }

  const timeoutMs = Number(normalized);
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 120_000) {
    return { ok: false };
  }

  return {
    ok: true,
    value: timeoutMs
  };
}

function requiresTarget(action: TestStepAction): boolean {
  return action === "navigate" || action === "click" || action === "assert_element_exists" || action === "fill";
}

function requiresValue(action: TestStepAction): boolean {
  return action === "assert_text_exists" || action === "assert_url";
}

function getTargetPlaceholder(action: TestStepAction): string {
  if (action === "navigate") {
    return "https://example.com/login";
  }

  if (action === "click" || action === "fill" || action === "assert_element_exists") {
    return "CSS selector";
  }

  return "선택";
}

function getValuePlaceholder(action: TestStepAction): string {
  if (action === "fill") {
    return "입력할 값";
  }

  if (action === "assert_text_exists") {
    return "기대 텍스트";
  }

  if (action === "assert_url") {
    return "기대 URL 또는 URL 조각";
  }

  return "선택";
}

const scenarioCreateStateMessage: Record<
  Exclude<ScenarioCreateState, "idle" | "creating" | "success">,
  string
> = {
  invalid: "입력값을 확인하세요. action별 필수 target, value, timeout을 채워야 합니다.",
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "Project를 찾을 수 없습니다. Dashboard에서 Project 상태를 다시 확인하세요.",
  unavailable: "Scenario 생성 요청에 실패했습니다. API 서버 상태를 확인하세요."
};
