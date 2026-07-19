"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  createScenario,
  createScenarioRun,
  deleteScenario,
  fetchScenarios,
  updateScenario,
  type CreateScenarioRunResult,
  type DeleteScenarioResult,
  type ScenarioListResult,
  type TestScenarioPayload,
  type TestStepPayload,
  type TestScenario,
  type TestStep,
  type TestStepAction,
  type UpdateScenarioResult
} from "@/lib/api";
import { clearStoredAccessTokenIfMatches, getStoredAccessToken } from "@/lib/auth";
import { runStatusLabel } from "@/lib/statusLabels";
import {
  LinkButton,
  LoginRequiredNotice,
  Metric,
  Notice,
  RefreshButton
} from "@/components/ui";

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
  navigate: "대상에 이동할 URL을 입력합니다.",
  click: "대상에 클릭할 CSS 선택자를 입력합니다.",
  fill: "대상에 입력 필드 선택자, 값에 입력할 내용을 넣습니다. 비밀번호 같은 민감값은 {{secret:이름}} 참조로 넣으면 DB에 저장되지 않고 서버의 SCENARIO_SECRET_이름 설정에서 실행 시점에 주입됩니다.",
  wait: "제한 시간에 대기 시간을 ms 단위로 입력합니다.",
  assert_element_exists: "대상에 존재해야 하는 CSS 선택자를 입력합니다.",
  assert_text_exists: "값에 화면에 보여야 하는 텍스트를 입력합니다.",
  assert_url: "값에 현재 URL에 포함되어야 하는 URL 또는 URL 조각을 입력합니다.",
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

type ScenarioMutationActionResult =
  | {
      state: "success";
      message: string;
      scenario?: TestScenario;
    }
  | {
      state: Exclude<ScenarioCreateState, "idle" | "creating" | "success">;
      message: string;
    };

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

type ScenarioListPageState =
  | { state: "checking" }
  | { state: "signed-out" }
  | ScenarioListResult;

export function ScenarioListPageClient({ projectId }: { projectId: string }) {
  const [result, setResult] = useState<ScenarioListPageState>({ state: "checking" });
  const [createdRunResult, setCreatedRunResult] = useState<CreateScenarioRunResult | null>(null);
  const [scenarioForm, setScenarioForm] = useState<ScenarioFormState>(() =>
    createInitialScenarioForm()
  );
  const [nextStepIndex, setNextStepIndex] = useState(2);
  const [createState, setCreateState] = useState<ScenarioCreateState>("idle");
  const [createMessage, setCreateMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [creatingScenarioId, setCreatingScenarioId] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const scenarios = result.state === "success" ? result.scenarios : [];

  const loadScenarios = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (!accessToken) {
      setResult({ state: "signed-out" });
      return;
    }

    setIsLoading(true);
    const nextResult = await fetchScenarios({
      projectId,
      accessToken
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
    }

    setResult(nextResult);
    setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
    setIsLoading(false);
  }, [projectId]);

  const requestScenarioRun = useCallback(
    async (scenarioId: string) => {
      const accessToken = getStoredAccessToken();

      if (!accessToken) {
        return;
      }

      setCreatingScenarioId(scenarioId);
      const nextResult = await createScenarioRun({
        projectId,
        scenarioId,
        accessToken
      });

      if (nextResult.state === "unauthorized") {
        clearStoredAccessTokenIfMatches(accessToken);
      }

      setCreatedRunResult(nextResult);
      setCreatingScenarioId(null);
    },
    [projectId]
  );

  const createScenarioFromForm = useCallback(
    async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      setCreateMessage(null);

      const accessToken = getStoredAccessToken();

      if (!accessToken) {
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
        accessToken,
        payload: payloadResult.payload
      });

      if (nextResult.state !== "success") {
        if (nextResult.state === "unauthorized") {
          clearStoredAccessTokenIfMatches(accessToken);
        }

        setCreateState(nextResult.state);
        setCreateMessage(scenarioCreateStateMessage[nextResult.state]);
        return;
      }

      setResult((currentResult) =>
        currentResult.state === "success"
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
    [projectId, scenarioForm]
  );

  const updateScenarioFromPayload = useCallback(
    async (
      scenarioId: string,
      payload: TestScenarioPayload
    ): Promise<ScenarioMutationActionResult> => {
      const accessToken = getStoredAccessToken();

      if (!accessToken) {
        return {
          state: "unauthorized",
          message: "로그인 세션이 없습니다. 로그인 후 다시 시도하세요."
        };
      }

      const nextResult = await updateScenario({
        projectId,
        scenarioId,
        accessToken,
        payload
      });

      if (nextResult.state !== "success") {
        if (nextResult.state === "unauthorized") {
          clearStoredAccessTokenIfMatches(accessToken);
        }

        return {
          state: nextResult.state,
          message: scenarioUpdateStateMessage[nextResult.state]
        };
      }

      setResult((currentResult) =>
        currentResult.state === "success"
          ? {
              state: "success",
              scenarios: currentResult.scenarios.map((scenario) =>
                scenario.id === scenarioId ? nextResult.scenario : scenario
              )
            }
          : currentResult
      );
      setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));

      return {
        state: "success",
        message: "Scenario를 저장했습니다.",
        scenario: nextResult.scenario
      };
    },
    [projectId]
  );

  const deleteScenarioById = useCallback(
    async (scenarioId: string): Promise<ScenarioMutationActionResult> => {
      const accessToken = getStoredAccessToken();

      if (!accessToken) {
        return {
          state: "unauthorized",
          message: "로그인 세션이 없습니다. 로그인 후 다시 시도하세요."
        };
      }

      const nextResult = await deleteScenario({
        projectId,
        scenarioId,
        accessToken
      });

      if (nextResult.state !== "success") {
        if (nextResult.state === "unauthorized") {
          clearStoredAccessTokenIfMatches(accessToken);
        }

        return {
          state: nextResult.state,
          message: scenarioDeleteStateMessage[nextResult.state]
        };
      }

      setResult((currentResult) =>
        currentResult.state === "success"
          ? {
              state: "success",
              scenarios: currentResult.scenarios.filter((scenario) => scenario.id !== scenarioId)
            }
          : currentResult
      );
      setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));

      return {
        state: "success",
        message: "Scenario를 삭제했습니다."
      };
    },
    [projectId]
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
    queueMicrotask(() => {
      void loadScenarios();
    });
  }, [loadScenarios]);

  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <header className="flex flex-col gap-6 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-cyan-700 dark:text-cyan-400">
                AIM 시나리오
              </p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
                시나리오 목록
              </h1>
              <p className="mt-4 text-sm leading-6 text-slate-600 dark:text-slate-300">
                로그인·검색 같은 핵심 사용자 흐름을 시나리오로 등록하고, 수동 실행으로
                실제 브라우저에서 동작을 검증합니다.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <LinkButton href={`/projects/${projectId}/settings`} label="프로젝트 설정" />
              <RefreshButton isLoading={isLoading} onClick={() => void loadScenarios()} />
            </div>
          </div>
        </header>

        {result.state === "checking" && (
          <Notice
            tone="info"
            title="로그인 세션 확인 중"
            description="저장된 로그인 세션이 있으면 자동으로 시나리오 목록을 조회합니다."
          />
        )}

        {result.state === "signed-out" && <LoginRequiredNotice />}

        {result.state === "unauthorized" && <LoginRequiredNotice expired />}

        {result.state === "not-found" && (
          <Notice
            tone="danger"
            title="프로젝트를 찾을 수 없습니다"
            description="프로젝트 ID 또는 현재 사용자 권한을 확인하세요."
          />
        )}

        {result.state === "unavailable" && (
          <Notice
            tone="danger"
            title="요청 실패"
            description="서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
          />
        )}

        {result.state === "success" && (
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
            title="시나리오 실행 생성 완료"
            description={`새 시나리오 실행이 ${runStatusLabel(createdRunResult.scenarioRun.status)} 상태로 생성되었습니다.`}
            action={
              <Link
                className="inline-flex text-sm font-bold underline"
                href={`/projects/${projectId}/scenarios/${createdRunResult.scenarioRun.scenario_id}/runs/${createdRunResult.scenarioRun.id}`}
              >
                결과 페이지 열기
              </Link>
            }
          />
        )}

        {createdRunResult?.state === "conflict" && (
          <Notice
            tone="danger"
            title="시나리오 실행 생성 실패"
            description="비활성 시나리오는 실행할 수 없습니다."
          />
        )}

        {createdRunResult?.state === "unauthorized" && (
          <Notice
            tone="danger"
            title="시나리오 실행 생성 인증 실패"
            description="토큰이 없거나 만료되었거나, 이 프로젝트에 접근할 권한이 없습니다."
          />
        )}

        {createdRunResult?.state === "not-found" && (
          <Notice
            tone="danger"
            title="시나리오 실행 생성 대상 없음"
            description="프로젝트 ID 또는 시나리오 ID를 확인하세요."
          />
        )}

        {createdRunResult?.state === "unavailable" && (
          <Notice
            tone="danger"
            title="시나리오 실행 생성 요청 실패"
            description="실행 요청에 실패했습니다. 잠시 후 다시 시도하세요."
          />
        )}

        {result.state === "success" && (
          <section className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold">저장된 시나리오</h2>
                <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                  마지막 조회: {lastUpdatedAt ?? "아직 없음"}
                </p>
              </div>
              <span className="rounded-full bg-cyan-50 dark:bg-cyan-950 px-3 py-1 text-xs font-bold text-cyan-700 dark:text-cyan-400 ring-1 ring-cyan-200 dark:ring-cyan-900">
                {scenarios.length}개
              </span>
            </div>

            {scenarios.length === 0 ? (
              <p className="rounded-2xl border border-dashed border-slate-200 dark:border-slate-800 bg-white/60 p-5 text-sm text-slate-500 dark:text-slate-400">
                아직 생성된 scenario가 없습니다. 위 폼으로 첫 critical user flow를 등록하세요.
              </p>
            ) : (
              <ul className="grid gap-4">
                {scenarios.map((scenario) => (
                  <ScenarioCard
                    creatingScenarioId={creatingScenarioId}
                    key={scenario.id}
                    onDelete={deleteScenarioById}
                    onRun={() => void requestScenarioRun(scenario.id)}
                    onUpdate={updateScenarioFromPayload}
                    projectId={projectId}
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
      className="rounded-3xl border border-cyan-200 dark:border-cyan-900 bg-cyan-50/60 p-6"
      onSubmit={onSubmit}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-400">
            시나리오 빌더
          </p>
          <h2 className="mt-3 text-2xl font-bold">새 시나리오 생성</h2>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
            핵심 사용자 흐름을 단계 단위로 작성합니다. 결제·삭제처럼 되돌리기 어려운 동작은
            피하고, 로그인·검색·주요 페이지 접근처럼 안전하게 반복 가능한 흐름부터 등록하세요.
          </p>
        </div>
        <button
          className="rounded-2xl border border-cyan-300 dark:border-cyan-800 px-4 py-2 text-sm font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-500 hover:bg-cyan-50 dark:hover:bg-cyan-950"
          onClick={onAddStep}
          type="button"
        >
          단계 추가
        </button>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_220px]">
        <label className="block" htmlFor="scenario-name">
          <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">시나리오 이름</span>
          <input
            className="mt-2 w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 text-sm text-slate-900 dark:text-white outline-none ring-cyan-300/0 transition placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
            id="scenario-name"
            maxLength={120}
            onChange={(event) => onChange({ ...form, name: event.target.value })}
            placeholder="로그인 흐름"
            required
            type="text"
            value={form.name}
          />
        </label>

        <label className="flex items-center gap-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 text-sm text-slate-600 dark:text-slate-300 lg:mt-7">
          <input
            checked={form.isActive}
            className="h-4 w-4 accent-cyan-600"
            onChange={(event) => onChange({ ...form, isActive: event.target.checked })}
            type="checkbox"
          />
          시나리오 활성화
        </label>
      </div>

      <label className="mt-4 block" htmlFor="scenario-description">
        <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">설명</span>
        <textarea
          className="mt-2 min-h-24 w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 text-sm text-slate-900 dark:text-white outline-none ring-cyan-300/0 transition placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
          id="scenario-description"
          maxLength={1000}
          onChange={(event) => onChange({ ...form, description: event.target.value })}
          placeholder="이 시나리오가 검증하는 핵심 사용자 흐름을 적어두세요."
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
          className="rounded-2xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-600 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={createState === "creating"}
          type="submit"
        >
          {createState === "creating" ? "시나리오 생성 중" : "시나리오 생성"}
        </button>
        <p className="text-xs leading-5 text-slate-500 dark:text-slate-400">
          생성 후 목록에 바로 추가됩니다. 활성 상태라면 수동 실행을 시작할 수 있습니다.
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
    <article className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-slate-900 dark:text-white">단계 #{index + 1}</p>
          <p className="mt-1 text-xs leading-5 text-slate-400 dark:text-slate-500">{actionHelp[step.action]}</p>
        </div>
        <button
          className="rounded-xl border border-slate-200 dark:border-slate-800 px-3 py-2 text-xs font-bold text-slate-600 dark:text-slate-300 transition hover:border-rose-400 hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-40"
          disabled={!canRemove}
          onClick={onRemove}
          type="button"
        >
          삭제
        </button>
      </div>

      <div className="grid gap-3 lg:grid-cols-[220px_1fr_1fr_180px]">
        <label className="block" htmlFor={`scenario-step-action-${step.id}`}>
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
            동작
          </span>
          <select
            className="mt-2 w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-3 text-sm text-slate-900 dark:text-white outline-none focus:border-cyan-500"
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
          label="대상"
          onChange={(value) => onUpdate({ target: value })}
          placeholder={getTargetPlaceholder(step.action)}
          value={step.target}
        />
        <StepInput
          label="값"
          onChange={(value) => onUpdate({ value })}
          placeholder={getValuePlaceholder(step.action)}
          value={step.value}
        />
        <StepInput
          label="제한 시간(ms)"
          onChange={(value) => onUpdate({ timeoutMs: value })}
          placeholder={step.action === "wait" ? "1000" : "선택"}
          type="number"
          value={step.timeoutMs}
        />
      </div>

      <label className="mt-4 flex items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
        <input
          checked={step.isCritical}
          className="h-4 w-4 accent-cyan-600"
          onChange={(event) => onUpdate({ isCritical: event.target.checked })}
          type="checkbox"
        />
        핵심 단계 (실패 시 이후 단계 중단)
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
      <span className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">
        {label}
      </span>
      <input
        className="mt-2 w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-3 text-sm text-slate-900 dark:text-white outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-cyan-500"
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
        title={createState === "success" ? "시나리오 생성 완료" : "시나리오 생성 실패"}
        tone={createState === "success" ? "info" : "danger"}
      />
    </div>
  );
}

function ScenarioCard({
  scenario,
  projectId,
  creatingScenarioId,
  onDelete,
  onUpdate,
  onRun
}: {
  scenario: TestScenario;
  projectId: string;
  creatingScenarioId: string | null;
  onDelete: (scenarioId: string) => Promise<ScenarioMutationActionResult>;
  onUpdate: (
    scenarioId: string,
    payload: TestScenarioPayload
  ) => Promise<ScenarioMutationActionResult>;
  onRun: () => void;
}) {
  const isCreating = creatingScenarioId === scenario.id;
  const [isEditing, setIsEditing] = useState(false);
  const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);
  const [form, setForm] = useState<ScenarioFormState>(() => formFromScenario(scenario));
  const [nextStepIndex, setNextStepIndex] = useState(scenario.steps.length + 1);
  const [mutationState, setMutationState] = useState<ScenarioCreateState>("idle");
  const [mutationMessage, setMutationMessage] = useState<string | null>(null);

  async function submitUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMutationMessage(null);

    const payloadResult = buildScenarioPayload(form);
    if (!payloadResult.ok) {
      setMutationState("invalid");
      setMutationMessage(payloadResult.message);
      return;
    }

    setMutationState("creating");
    const result = await onUpdate(scenario.id, payloadResult.payload);
    setMutationState(result.state === "success" ? "success" : result.state);
    setMutationMessage(result.message);

    if (result.state !== "success") {
      return;
    }

    if (result.scenario) {
      setForm(formFromScenario(result.scenario));
      setNextStepIndex(result.scenario.steps.length + 1);
    }
    setIsEditing(false);
  }

  async function submitDelete() {
    setMutationMessage(null);
    setMutationState("creating");
    const result = await onDelete(scenario.id);
    setMutationState(result.state === "success" ? "success" : result.state);
    setMutationMessage(result.message);
    setIsConfirmingDelete(false);
  }

  function startEditing() {
    setForm(formFromScenario(scenario));
    setNextStepIndex(scenario.steps.length + 1);
    setMutationState("idle");
    setMutationMessage(null);
    setIsConfirmingDelete(false);
    setIsEditing(true);
  }

  function cancelEditing() {
    setForm(formFromScenario(scenario));
    setNextStepIndex(scenario.steps.length + 1);
    setMutationState("idle");
    setMutationMessage(null);
    setIsEditing(false);
  }

  function updateEditStep(stepId: string, nextStep: Partial<ScenarioStepFormState>) {
    setForm((currentForm) => ({
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

  function addEditStep() {
    setForm((currentForm) => ({
      ...currentForm,
      steps: [...currentForm.steps, createScenarioStepForm(`edit-step-${nextStepIndex}`)]
    }));
    setNextStepIndex((currentIndex) => currentIndex + 1);
  }

  function removeEditStep(stepId: string) {
    setForm((currentForm) => {
      if (currentForm.steps.length <= 1) {
        return currentForm;
      }

      return {
        ...currentForm,
        steps: currentForm.steps.filter((step) => step.id !== stepId)
      };
    });
  }

  if (isEditing) {
    return (
      <li className="rounded-2xl border border-cyan-200 dark:border-cyan-900 bg-cyan-50/60 p-5">
        <form onSubmit={submitUpdate}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-700 dark:text-cyan-400">
                시나리오 편집
              </p>
              <h3 className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{scenario.name}</h3>
              <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
                저장하면 단계 목록이 현재 폼 기준으로 교체됩니다. 이미 생성된 시나리오 실행
                결과는 그대로 보존됩니다.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                className="rounded-2xl border border-cyan-300 dark:border-cyan-800 px-4 py-2 text-sm font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-500 hover:bg-cyan-50 dark:hover:bg-cyan-950"
                onClick={addEditStep}
                type="button"
              >
                단계 추가
              </button>
              <button
                className="rounded-2xl border border-slate-200 dark:border-slate-800 px-4 py-2 text-sm font-bold text-slate-600 dark:text-slate-300 transition hover:border-slate-400 hover:text-slate-900 dark:hover:text-white"
                onClick={cancelEditing}
                type="button"
              >
                취소
              </button>
            </div>
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-[1fr_220px]">
            <label className="block" htmlFor={`scenario-edit-name-${scenario.id}`}>
              <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">시나리오 이름</span>
              <input
                className="mt-2 w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 text-sm text-slate-900 dark:text-white outline-none ring-cyan-300/0 transition placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
                id={`scenario-edit-name-${scenario.id}`}
                maxLength={120}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                required
                type="text"
                value={form.name}
              />
            </label>

            <label className="flex items-center gap-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 text-sm text-slate-600 dark:text-slate-300 lg:mt-7">
              <input
                checked={form.isActive}
                className="h-4 w-4 accent-cyan-600"
                onChange={(event) => setForm({ ...form, isActive: event.target.checked })}
                type="checkbox"
              />
              시나리오 활성화
            </label>
          </div>

          <label className="mt-4 block" htmlFor={`scenario-edit-description-${scenario.id}`}>
            <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">설명</span>
            <textarea
              className="mt-2 min-h-24 w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 text-sm text-slate-900 dark:text-white outline-none ring-cyan-300/0 transition placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
              id={`scenario-edit-description-${scenario.id}`}
              maxLength={1000}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              value={form.description}
            />
          </label>

          <div className="mt-6 grid gap-4">
            {form.steps.map((step, index) => (
              <ScenarioStepEditor
                canRemove={form.steps.length > 1}
                index={index}
                key={step.id}
                onRemove={() => removeEditStep(step.id)}
                onUpdate={(nextStep) => updateEditStep(step.id, nextStep)}
                step={step}
              />
            ))}
          </div>

          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
            <button
              className="rounded-2xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-600 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={mutationState === "creating"}
              type="submit"
            >
              {mutationState === "creating" ? "저장 중" : "시나리오 저장"}
            </button>
            <p className="text-xs leading-5 text-slate-500 dark:text-slate-400">
              결제·삭제 같은 파괴적인 동작 없이 반복 가능한 사용자 흐름만 유지하세요.
            </p>
          </div>

          {mutationMessage && (
            <div className="mt-5">
              <Notice
                description={mutationMessage}
                title={mutationState === "success" ? "시나리오 저장 완료" : "시나리오 저장 실패"}
                tone={mutationState === "success" ? "info" : "danger"}
              />
            </div>
          )}
        </form>
      </li>
    );
  }

  return (
    <li className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">{scenario.name}</h3>
            <span
              className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${
                scenario.is_active
                  ? "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 ring-emerald-200 dark:ring-emerald-900"
                  : "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 ring-slate-200 dark:ring-slate-700"
              }`}
            >
              {scenario.is_active ? "활성" : "비활성"}
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            {scenario.description ?? "설명이 없습니다."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <LinkButton
            href={`/projects/${projectId}/scenarios/${scenario.id}/runs`}
            label="실행 이력 보기"
          />
          <button
            className="rounded-2xl border border-slate-200 dark:border-slate-800 px-4 py-2 text-sm font-bold text-slate-600 dark:text-slate-300 transition hover:border-cyan-400 hover:text-cyan-700 dark:hover:text-cyan-300"
            onClick={startEditing}
            type="button"
          >
            수정
          </button>
          <button
            className="rounded-2xl border border-rose-200 dark:border-rose-900 px-4 py-2 text-sm font-bold text-rose-800 dark:text-rose-300 transition hover:border-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950"
            onClick={() => {
              setMutationMessage(null);
              setIsConfirmingDelete(true);
            }}
            type="button"
          >
            삭제
          </button>
          <button
            className="rounded-2xl bg-cyan-700 px-4 py-2 text-sm font-bold text-white transition hover:bg-cyan-600 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!scenario.is_active || isCreating}
            onClick={onRun}
            type="button"
          >
            {isCreating ? "실행 생성 중" : "시나리오 실행"}
          </button>
        </div>
      </div>

      {isConfirmingDelete && (
        <div className="mt-5 rounded-2xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950 p-4 text-rose-800 dark:text-rose-300">
          <h4 className="font-semibold">시나리오 삭제 확인</h4>
          <p className="mt-2 text-sm leading-6 opacity-85">
            이 시나리오와 단계 정의를 삭제합니다. 이미 저장된 실행 결과는 별도 기록으로 남아있을
            수 있지만, 새 실행은 만들 수 없습니다.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              className="rounded-2xl bg-rose-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-rose-500 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={mutationState === "creating"}
              onClick={() => void submitDelete()}
              type="button"
            >
              {mutationState === "creating" ? "삭제 중" : "삭제 확정"}
            </button>
            <button
              className="rounded-2xl border border-slate-200 dark:border-slate-800 px-4 py-2 text-sm font-bold text-slate-700 dark:text-slate-200 transition hover:border-slate-400 hover:text-slate-900 dark:hover:text-white"
              onClick={() => setIsConfirmingDelete(false)}
              type="button"
            >
              취소
            </button>
          </div>
        </div>
      )}

      {mutationMessage && !isConfirmingDelete && (
        <div className="mt-5">
          <Notice
            description={mutationMessage}
            title={mutationState === "success" ? "시나리오 작업 완료" : "시나리오 작업 실패"}
            tone={mutationState === "success" ? "info" : "danger"}
          />
        </div>
      )}

      <div className="mt-5">
        <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
          단계
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
    <li className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-3 text-sm text-slate-600 dark:text-slate-300">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="font-medium text-slate-900 dark:text-white">
          #{step.step_order} {actionLabels[step.action]}
        </p>
        <span
          className={`rounded-full px-2 py-1 text-[11px] font-bold ring-1 ${
            step.is_critical
              ? "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900"
              : "bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 ring-slate-200 dark:ring-slate-700"
          }`}
        >
          {step.is_critical ? "핵심" : "일반"}
        </span>
      </div>
      <dl className="mt-3 grid gap-3 sm:grid-cols-3">
        <Metric label="대상" value={step.target ?? "없음"} />
        <Metric label="값" value={step.value ?? "없음"} />
        <Metric label="제한 시간" value={step.timeout_ms === null ? "기본값" : `${step.timeout_ms}ms`} />
      </dl>
    </li>
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

function formFromScenario(scenario: TestScenario): ScenarioFormState {
  return {
    name: scenario.name,
    description: scenario.description ?? "",
    isActive: scenario.is_active,
    steps: scenario.steps.map((step) => ({
      id: step.id,
      action: step.action,
      target: step.target ?? "",
      value: step.value ?? "",
      timeoutMs: step.timeout_ms === null ? "" : String(step.timeout_ms),
      isCritical: step.is_critical
    }))
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
      message: "시나리오 이름을 입력하세요."
    };
  }

  if (form.steps.length === 0) {
    return {
      ok: false,
      message: "시나리오에는 최소 1개 이상의 단계가 필요합니다."
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
        message: `단계 #${index + 1}: 제한 시간은 1~120000ms 사이의 정수여야 합니다.`
      };
    }

    if (requiresTarget(step.action) && !target) {
      return {
        ok: false,
        message: `단계 #${index + 1}: ${actionLabels[step.action]} 동작은 대상이 필요합니다.`
      };
    }

    if (step.action === "fill" && !value) {
      return {
        ok: false,
        message: `단계 #${index + 1}: 입력 동작은 값이 필요합니다.`
      };
    }

    if (requiresValue(step.action) && !value) {
      return {
        ok: false,
        message: `단계 #${index + 1}: ${actionLabels[step.action]} 동작은 값이 필요합니다.`
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
    return "CSS 선택자";
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
  invalid: "입력값을 확인하세요. 동작별 필수 대상, 값, 제한 시간을 채워야 합니다.",
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "프로젝트를 찾을 수 없습니다. 대시보드에서 프로젝트 상태를 다시 확인하세요.",
  unavailable: "시나리오 생성에 실패했습니다. 잠시 후 다시 시도하세요."
};

const scenarioUpdateStateMessage: Record<
  Exclude<UpdateScenarioResult["state"], "success">,
  string
> = {
  invalid: "입력값을 확인하세요. 동작별 필수 대상, 값, 제한 시간을 채워야 합니다.",
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "프로젝트 또는 시나리오를 찾을 수 없습니다. 목록을 다시 조회하세요.",
  unavailable: "시나리오 저장에 실패했습니다. 잠시 후 다시 시도하세요."
};

const scenarioDeleteStateMessage: Record<
  Exclude<DeleteScenarioResult["state"], "success">,
  string
> = {
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "프로젝트 또는 시나리오를 찾을 수 없습니다. 목록을 다시 조회하세요.",
  unavailable: "시나리오 삭제에 실패했습니다. 잠시 후 다시 시도하세요."
};
