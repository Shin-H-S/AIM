"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createCheckRun,
  fetchApiHealth,
  fetchCheckRuns,
  fetchProjectIncidents,
  fetchProjects,
  fetchScenarios,
  type CheckRunListResult,
  type CheckRunStatus,
  type CheckRunSummary,
  type HealthCheckResult,
  type Project
} from "@/lib/api";
import { MiniDonut, Sparkline } from "@/components/charts";
import { hasSession, notifySessionChanged } from "@/lib/auth";
import { formatRelativeTime } from "@/lib/format";
import { deploymentRiskLabel, environmentLabel, triggerSourceLabel } from "@/lib/statusLabels";
import {
  checkRunStatusCopy,
  EmptyState,
  LinkButton,
  LoginRequiredNotice,
  Notice,
  RefreshButton,
  TONE_CHIP_CLASSES
} from "@/components/ui";

const PROJECT_DASHBOARD_LIMIT = 20;
// 프로젝트 카드의 점수 스파크라인에 쓸 최근 CheckRun 수.
const PROJECT_TREND_RUN_LIMIT = 10;
const ACTIVE_CHECK_RUN_STATUSES: CheckRunStatus[] = ["QUEUED", "RUNNING", "ANALYZING"];

const healthStatusCopy: Record<HealthCheckResult["state"], string> = {
  loading: "확인 중",
  available: "연결됨",
  unavailable: "연결 실패"
};

type DashboardProject = {
  project: Project;
  checkRuns: CheckRunSummary[];
  latestCheckRun: CheckRunSummary | null;
  latestCheckRunState: CheckRunListResult["state"];
  openIncidentCount: number;
  // null = 조회 실패(알 수 없음) — 체크리스트에서 이 단계를 빼고 판단한다.
  scenarioCount: number | null;
};

type CheckRunStartState =
  | "idle"
  | "starting"
  | "unauthorized"
  | "not-found"
  | "conflict"
  | "unavailable";

type DashboardState =
  | {
      state: "signed-out";
    }
  | {
      state: "loading";
    }
  | {
      state: "success";
      projects: DashboardProject[];
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "unavailable";
    };

export default function DashboardPage() {
  const router = useRouter();
  const [health, setHealth] = useState<HealthCheckResult>({
    state: "loading"
  });
  const [dashboard, setDashboard] = useState<DashboardState>({ state: "loading" });
  const [checkRunStartStates, setCheckRunStartStates] = useState<
    Record<string, CheckRunStartState>
  >({});
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    if (!hasSession()) {
      setDashboard({ state: "signed-out" });
      setLastUpdatedAt(null);
      return;
    }

    setDashboard({ state: "loading" });

    const projectsResult = await fetchProjects({
      limit: PROJECT_DASHBOARD_LIMIT
    });

    if (projectsResult.state !== "success") {
      if (projectsResult.state === "unauthorized") {
        notifySessionChanged();
      }

      setDashboard({ state: projectsResult.state });
      setLastUpdatedAt(null);
      return;
    }

    const projects = await Promise.all(
      projectsResult.projects.map(async (project) => {
        // 목록 응답에 점수 요약과 linked ScenarioRun이 포함되므로 상세 조회 없이 구성한다.
        // 인시던트·시나리오는 관제 스트립과 온보딩 체크리스트의 원료다.
        const [checkRunsResult, incidentsResult, scenariosResult] = await Promise.all([
          fetchCheckRuns({ projectId: project.id, limit: PROJECT_TREND_RUN_LIMIT }),
          fetchProjectIncidents({ projectId: project.id, limit: 20 }),
          fetchScenarios({ projectId: project.id })
        ]);
        const checkRuns = checkRunsResult.state === "success" ? checkRunsResult.checkRuns : [];

        return {
          project,
          checkRuns,
          latestCheckRun: checkRuns[0] ?? null,
          latestCheckRunState: checkRunsResult.state,
          openIncidentCount:
            incidentsResult.state === "success"
              ? incidentsResult.incidents.filter((incident) => incident.status === "OPEN").length
              : 0,
          scenarioCount:
            scenariosResult.state === "success" ? scenariosResult.scenarios.length : null
        };
      })
    );
    setDashboard({ state: "success", projects });
    setCheckRunStartStates({});
    setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
  }, []);

  useEffect(() => {
    let isMounted = true;

    fetchApiHealth().then((result) => {
      if (isMounted) {
        setHealth(result);
      }
    });

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void loadDashboard();
    });
  }, [loadDashboard]);

  const actionItems = useMemo(() => {
    if (dashboard.state !== "success") {
      return null;
    }
    return buildActionItems(dashboard.projects);
  }, [dashboard]);

  async function handleStartCheckRun(project: Project) {
    if (!hasSession()) {
      setCheckRunStartStates((currentStates) => ({
        ...currentStates,
        [project.id]: "unauthorized"
      }));
      return;
    }

    setCheckRunStartStates((currentStates) => ({
      ...currentStates,
      [project.id]: "starting"
    }));

    const result = await createCheckRun({
      projectId: project.id,
    });

    if (result.state !== "success") {
      if (result.state === "unauthorized") {
        notifySessionChanged();
      }

      setCheckRunStartStates((currentStates) => ({
        ...currentStates,
        [project.id]: result.state
      }));
      return;
    }

    setCheckRunStartStates((currentStates) => ({
      ...currentStates,
      [project.id]: "idle"
    }));
    router.push(`/projects/${project.id}/check-runs/${result.checkRun.id}`);
  }

  return (
    <main>
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-6 py-8">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">대시보드</h1>
            <HealthInline health={health} />
            {lastUpdatedAt && (
              <span className="text-xs text-slate-400 dark:text-slate-500">갱신 {lastUpdatedAt}</span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {dashboard.state !== "signed-out" && (
              <LinkButton href="/projects/new" label="새 프로젝트" variant="primary" />
            )}
            <RefreshButton
              isLoading={dashboard.state === "loading"}
              label="갱신"
              onClick={() => void loadDashboard()}
            />
          </div>
        </header>

        {actionItems && (
          <ActionStrip items={actionItems} projectCount={dashboard.state === "success" ? dashboard.projects.length : 0} />
        )}

        <DashboardContent
          checkRunStartStates={checkRunStartStates}
          dashboard={dashboard}
          onStartCheckRun={handleStartCheckRun}
        />
      </section>
    </main>
  );
}

function HealthInline({ health }: { health: HealthCheckResult }) {
  const isAvailable = health.state === "available";
  const dotClassName = isAvailable
    ? "bg-emerald-500"
    : health.state === "loading"
      ? "animate-pulse bg-cyan-500"
      : "bg-rose-500";
  const textClassName = isAvailable
    ? "text-emerald-600 dark:text-emerald-400"
    : health.state === "loading"
      ? "text-cyan-700 dark:text-cyan-400"
      : "text-rose-600 dark:text-rose-400";

  return (
    <span className={`flex items-center gap-1.5 text-xs font-semibold ${textClassName}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotClassName}`} />
      서비스 {healthStatusCopy[health.state]}
    </span>
  );
}

type ActionItem = {
  key: string;
  tone: "bad" | "warn" | "info";
  label: string;
  href: string;
};

/**
 * 관제 스트립의 원료 — "지금 조치할 것"만 골라낸다(R3).
 * 심각한 것부터: 열린 인시던트 → 최신 검사 실패 → 인증 대기 → 진행 중(정보).
 */
function buildActionItems(projects: DashboardProject[]): ActionItem[] {
  const items: ActionItem[] = [];

  for (const { openIncidentCount, project } of projects) {
    if (openIncidentCount > 0) {
      items.push({
        key: `incident-${project.id}`,
        tone: "bad",
        label: `${project.name} · 인시던트 ${openIncidentCount}건`,
        href: `/projects/${project.id}/alerts`
      });
    }
  }

  for (const { latestCheckRun, openIncidentCount, project } of projects) {
    // 인시던트 칩이 이미 있는 프로젝트의 실패는 중복 신호다.
    if (openIncidentCount === 0 && latestCheckRun?.status === "FAILED") {
      items.push({
        key: `failed-${project.id}`,
        tone: "bad",
        label: `${project.name} · 최신 검사 실패`,
        href: `/projects/${project.id}/check-runs/${latestCheckRun.id}`
      });
    }
  }

  for (const { project } of projects) {
    if (!project.is_verified) {
      items.push({
        key: `verify-${project.id}`,
        tone: "warn",
        label: `${project.name} · 도메인 인증 대기`,
        href: `/projects/${project.id}/settings`
      });
    }
  }

  const activeCount = projects.filter(
    ({ latestCheckRun }) =>
      latestCheckRun !== null && ACTIVE_CHECK_RUN_STATUSES.includes(latestCheckRun.status)
  ).length;
  if (activeCount > 0) {
    items.push({
      key: "active",
      tone: "info",
      label: `검사 진행 중 ${activeCount}건`,
      href: "#"
    });
  }

  return items;
}

const ACTION_CHIP_HOVER: Record<ActionItem["tone"], string> = {
  bad: "hover:ring-rose-400",
  warn: "hover:ring-amber-400",
  info: "hover:ring-cyan-400"
};

function ActionStrip({ items, projectCount }: { items: ActionItem[]; projectCount: number }) {
  if (items.length === 0) {
    return (
      <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm font-semibold text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300">
        ✓ 프로젝트 {projectCount}개 모두 정상 — 지금 조치할 항목이 없습니다.
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
      <span className="text-xs font-bold uppercase tracking-[0.14em] text-slate-400 dark:text-slate-500">
        지금 조치 필요
      </span>
      {items.map((item) =>
        item.href === "#" ? (
          <span
            className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${TONE_CHIP_CLASSES[item.tone]}`}
            key={item.key}
          >
            {item.label}
          </span>
        ) : (
          <Link
            className={`rounded-full px-3 py-1 text-xs font-bold ring-1 transition ${TONE_CHIP_CLASSES[item.tone]} ${ACTION_CHIP_HOVER[item.tone]}`}
            href={item.href}
            key={item.key}
          >
            {item.label} →
          </Link>
        )
      )}
    </div>
  );
}

function DashboardContent({
  checkRunStartStates,
  dashboard,
  onStartCheckRun
}: {
  checkRunStartStates: Record<string, CheckRunStartState>;
  dashboard: DashboardState;
  onStartCheckRun: (project: Project) => void;
}) {
  if (dashboard.state === "signed-out") {
    return <LoginRequiredNotice />;
  }

  if (dashboard.state === "loading") {
    return <EmptyState description="프로젝트와 최신 검사를 불러오는 중입니다." title="불러오는 중" />;
  }

  if (dashboard.state === "unauthorized") {
    return <LoginRequiredNotice expired />;
  }

  if (dashboard.state === "unavailable") {
    return (
      <Notice
        description="서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
        title="대시보드 요청 실패"
        tone="danger"
      />
    );
  }

  if (dashboard.projects.length === 0) {
    return (
      <EmptyState
        description="현재 계정에 등록된 프로젝트가 없습니다. 새 프로젝트 버튼으로 첫 서비스를 등록하세요."
        title="등록된 프로젝트 없음"
      />
    );
  }

  return (
    <div className="grid gap-3 xl:grid-cols-2">
      {dashboard.projects.map((dashboardProject) => (
        <ProjectDashboardCard
          dashboardProject={dashboardProject}
          key={dashboardProject.project.id}
          onStartCheckRun={onStartCheckRun}
          startState={checkRunStartStates[dashboardProject.project.id] ?? "idle"}
        />
      ))}
    </div>
  );
}

function ProjectDashboardCard({
  dashboardProject,
  onStartCheckRun,
  startState
}: {
  dashboardProject: DashboardProject;
  onStartCheckRun: (project: Project) => void;
  startState: CheckRunStartState;
}) {
  const { checkRuns, latestCheckRun, latestCheckRunState, project } = dashboardProject;
  const failedScenarioCount =
    latestCheckRun?.linked_scenario_runs?.filter(
      (scenarioRun) => scenarioRun.status === "FAILED"
    ).length ?? 0;
  const trendScores = checkRuns
    .map((checkRun) => checkRun.score?.overall_score)
    .filter((score): score is number => typeof score === "number")
    .reverse();

  return (
    <article className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="text-base font-bold text-slate-900 dark:text-white">{project.name}</h3>
            <span className="rounded-full border border-slate-200 dark:border-slate-800 px-2 py-0.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
              {environmentLabel(project.environment)}
            </span>
            {project.is_verified ? (
              <span className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">인증됨</span>
            ) : (
              <span className="rounded-full bg-amber-50 dark:bg-amber-950 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300 ring-1 ring-amber-200 dark:ring-amber-900">
                미인증
              </span>
            )}
          </div>
          <a
            className="mt-0.5 block truncate text-xs text-slate-400 dark:text-slate-500 transition hover:text-cyan-700 dark:hover:text-cyan-300"
            href={project.service_url}
            rel="noreferrer"
            target="_blank"
          >
            {project.service_url}
          </a>
        </div>
        <PrimaryAction
          dashboardProject={dashboardProject}
          onStartCheckRun={onStartCheckRun}
          startState={startState}
        />
      </div>

      <OnboardingChecklist dashboardProject={dashboardProject} />

      {startState !== "idle" && startState !== "starting" && (
        <p className="mt-2 rounded-xl bg-rose-50 dark:bg-rose-950 px-3 py-2 text-xs font-semibold text-rose-700 dark:text-rose-300 ring-1 ring-rose-200 dark:ring-rose-900">
          {checkRunStartStateMessage[startState]}
        </p>
      )}

      <LatestRunLine
        latestCheckRun={latestCheckRun}
        latestCheckRunState={latestCheckRunState}
        projectId={project.id}
        trendScores={trendScores}
      />

      {latestCheckRun?.failure_reason && (
        <p className="mt-2 truncate rounded-xl bg-rose-50 dark:bg-rose-950 px-3 py-2 text-xs text-rose-700 dark:text-rose-300 ring-1 ring-rose-200 dark:ring-rose-900">
          {latestCheckRun.failure_reason}
        </p>
      )}

      {failedScenarioCount > 0 && (
        <p className="mt-2 rounded-xl bg-rose-50 dark:bg-rose-950 px-3 py-2 text-xs font-semibold text-rose-700 dark:text-rose-300 ring-1 ring-rose-200 dark:ring-rose-900">
          시나리오 실패 {failedScenarioCount}건 — 결과 페이지에서 step·스크린샷 근거를 확인하세요.
        </p>
      )}

      <div className="mt-3 grid grid-cols-2 gap-2 border-t border-slate-100 dark:border-slate-800 pt-3 sm:grid-cols-4">
        <FooterLink href={`/projects/${project.id}/check-runs`} label="검사 이력" />
        <FooterLink href={`/projects/${project.id}/scenarios`} label="시나리오" />
        <FooterLink href={`/projects/${project.id}/alerts`} label="알림" />
        <FooterLink href={`/projects/${project.id}/settings`} label="설정" />
      </div>
    </article>
  );
}

const PRIMARY_ACTION_CLASSES =
  "shrink-0 rounded-xl bg-cyan-700 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-cyan-600";

/**
 * 상태마다 주 행동은 정확히 하나다(R3). 이전의 비활성 "검증 필요" 버튼은
 * 막다른 길이었다 — 못 하는 이유를 보여줄 게 아니라 다음 행동으로 보내야 한다.
 */
function PrimaryAction({
  dashboardProject,
  onStartCheckRun,
  startState
}: {
  dashboardProject: DashboardProject;
  onStartCheckRun: (project: Project) => void;
  startState: CheckRunStartState;
}) {
  const { openIncidentCount, project } = dashboardProject;

  if (!project.is_verified) {
    return (
      <Link className={PRIMARY_ACTION_CLASSES} href={`/projects/${project.id}/settings`}>
        인증하기
      </Link>
    );
  }

  if (openIncidentCount > 0) {
    return (
      <div className="flex shrink-0 items-center gap-1.5">
        <Link
          className="rounded-xl bg-rose-600 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-rose-500"
          href={`/projects/${project.id}/alerts`}
        >
          인시던트 보기
        </Link>
        <button
          className="rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 transition hover:border-cyan-400 hover:text-cyan-700 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
          disabled={startState === "starting"}
          onClick={() => onStartCheckRun(project)}
          type="button"
        >
          {startState === "starting" ? "요청 중" : "재검사"}
        </button>
      </div>
    );
  }

  return (
    <button
      className={`${PRIMARY_ACTION_CLASSES} disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500`}
      disabled={startState === "starting"}
      onClick={() => onStartCheckRun(project)}
      type="button"
    >
      {startState === "starting" ? "요청 중" : "검사 시작"}
    </button>
  );
}

type ChecklistStep = {
  key: string;
  label: string;
  done: boolean;
  href: string | null;
};

/**
 * 프로젝트가 "완성"될 때까지 카드에 상주하는 온보딩 여정(R3) —
 * 인증 → 첫 검사 → 시나리오 → 알림 채널. 전부 끝나면 사라진다.
 * 빈 상태를 안내로 쓰는 것이지, 완료된 사용자를 방해하지 않는다.
 */
function OnboardingChecklist({ dashboardProject }: { dashboardProject: DashboardProject }) {
  const { checkRuns, project, scenarioCount } = dashboardProject;

  const steps: ChecklistStep[] = [
    {
      key: "verify",
      label: "도메인 인증",
      done: project.is_verified,
      href: `/projects/${project.id}/settings`
    },
    {
      key: "first-run",
      label: "첫 검사 실행",
      done: checkRuns.length > 0,
      // 행동은 이 카드의 검사 시작 버튼이다 — 다른 페이지로 보내지 않는다.
      href: null
    },
    // 조회 실패(null)면 이 단계를 판단에서 뺀다 — 모르는 것을 미완료로 단정하지 않는다.
    ...(scenarioCount !== null
      ? [
          {
            key: "scenario",
            label: "핵심 흐름 시나리오",
            done: scenarioCount > 0,
            href: `/projects/${project.id}/scenarios`
          }
        ]
      : []),
    {
      key: "alerts",
      label: "알림 채널",
      done: Boolean(project.alert_webhook_url) || project.alert_email_enabled,
      href: `/projects/${project.id}/alerts`
    }
  ];

  if (steps.every((step) => step.done)) {
    return null;
  }

  return (
    <ol className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-800/50">
      {steps.map((step) => (
        <li className="flex items-center gap-1 text-xs" key={step.key}>
          <span aria-hidden className={step.done ? "text-emerald-600 dark:text-emerald-400" : "text-slate-300 dark:text-slate-600"}>
            {step.done ? "✓" : "○"}
          </span>
          {step.done || step.href === null ? (
            <span
              className={
                step.done
                  ? "font-semibold text-slate-400 line-through dark:text-slate-500"
                  : "font-semibold text-slate-600 dark:text-slate-300"
              }
            >
              {step.label}
            </span>
          ) : (
            <Link
              className="font-semibold text-cyan-700 underline-offset-2 hover:underline dark:text-cyan-400"
              href={step.href}
            >
              {step.label} →
            </Link>
          )}
        </li>
      ))}
    </ol>
  );
}

function getRunStatusDotClassName(status: CheckRunStatus): string {
  if (status === "COMPLETED") {
    return "bg-emerald-500";
  }

  if (status === "FAILED") {
    return "bg-rose-500";
  }

  if (status === "CANCELLED") {
    return "bg-slate-400";
  }

  return "animate-pulse bg-cyan-500";
}

function getRunStatusTextClassName(status: CheckRunStatus): string {
  if (status === "COMPLETED") {
    return "text-emerald-700 dark:text-emerald-400";
  }

  if (status === "FAILED") {
    return "text-rose-700 dark:text-rose-300";
  }

  if (status === "CANCELLED") {
    return "text-slate-500 dark:text-slate-400";
  }

  return "text-cyan-700 dark:text-cyan-400";
}

const riskChipClassName: Record<"STABLE" | "WARNING" | "RISK", string> = {
  STABLE: "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 ring-emerald-200 dark:ring-emerald-900",
  WARNING: "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 ring-amber-200 dark:ring-amber-900",
  RISK: "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900"
};

function LatestRunLine({
  latestCheckRun,
  latestCheckRunState,
  projectId,
  trendScores
}: {
  latestCheckRun: CheckRunSummary | null;
  latestCheckRunState: CheckRunListResult["state"];
  projectId: string;
  trendScores: number[];
}) {
  if (latestCheckRunState !== "success") {
    return (
      <p className="mt-3 text-xs font-semibold text-rose-600 dark:text-rose-400">
        최신 검사를 불러오지 못했습니다 — 권한 또는 API 상태를 확인하세요.
      </p>
    );
  }

  if (!latestCheckRun) {
    return (
      <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
        아직 실행된 검사가 없습니다. 검사 시작 버튼으로 첫 검사를 실행하세요.
      </p>
    );
  }

  const score = latestCheckRun.score ?? null;

  return (
    <Link
      className="-mx-1 mt-2 flex items-center gap-3 rounded-xl px-1 py-1.5 transition hover:bg-slate-50"
      href={`/projects/${projectId}/check-runs/${latestCheckRun.id}`}
    >
      {score && (
        <MiniDonut
          grade={score.grade}
          risk={score.deployment_risk}
          score={score.overall_score}
        />
      )}
      <span
        className={`flex shrink-0 items-center gap-1.5 text-xs font-bold ${getRunStatusTextClassName(latestCheckRun.status)}`}
      >
        <span
          className={`h-1.5 w-1.5 rounded-full ${getRunStatusDotClassName(latestCheckRun.status)}`}
        />
        {checkRunStatusCopy[latestCheckRun.status]}
      </span>
      <span className="min-w-0 truncate text-xs text-slate-500 dark:text-slate-400">
        {triggerSourceLabel(latestCheckRun.trigger_source)} ·{" "}
        {formatRelativeTime(latestCheckRun.queued_at)}
      </span>
      {score && (
        <span
          className={`hidden whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 sm:inline-flex ${riskChipClassName[score.deployment_risk]}`}
        >
          {score.overall_score}점 · {score.grade} · {deploymentRiskLabel(score.deployment_risk)}
        </span>
      )}
      <span className="flex-1" />
      {trendScores.length >= 2 ? (
        <Sparkline scores={trendScores} />
      ) : (
        <span className="hidden text-[11px] text-slate-300 sm:block">추이 데이터 부족</span>
      )}
      <svg className="h-3.5 w-3.5 shrink-0 text-slate-300" fill="none" viewBox="0 0 16 16">
        <path
          d="M6 4l4 4-4 4"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="1.5"
        />
      </svg>
    </Link>
  );
}

function FooterLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      className="whitespace-nowrap rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-1.5 text-center text-xs font-semibold text-slate-600 dark:text-slate-300 transition hover:border-cyan-300 hover:bg-cyan-50 dark:hover:bg-cyan-950 hover:text-cyan-800"
      href={href}
    >
      {label}
    </Link>
  );
}

const checkRunStartStateMessage: Record<
  Exclude<CheckRunStartState, "idle" | "starting">,
  string
> = {
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "프로젝트를 찾을 수 없습니다. 대시보드를 다시 갱신하세요.",
  conflict: "이미 진행 중인 검사가 있거나 도메인 인증이 필요합니다.",
  unavailable: "검사 요청에 실패했습니다. 잠시 후 다시 시도하세요."
};
