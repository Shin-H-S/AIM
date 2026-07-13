"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createCheckRun,
  fetchApiHealth,
  fetchCheckRuns,
  fetchProjects,
  type CheckRunListResult,
  type CheckRunStatus,
  type CheckRunSummary,
  type HealthCheckResult,
  type Project
} from "@/lib/api";
import { MiniDonut, Sparkline } from "@/components/charts";
import { clearStoredAccessToken, getStoredAccessToken } from "@/lib/auth";
import { formatRelativeTime } from "@/lib/format";
import { deploymentRiskLabel, environmentLabel, triggerSourceLabel } from "@/lib/statusLabels";
import {
  checkRunStatusCopy,
  EmptyState,
  LinkButton,
  LoginRequiredNotice,
  Notice,
  RefreshButton
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
    const accessToken = getStoredAccessToken();

    if (!accessToken) {
      setDashboard({ state: "signed-out" });
      setLastUpdatedAt(null);
      return;
    }

    setDashboard({ state: "loading" });

    const projectsResult = await fetchProjects({
      accessToken,
      limit: PROJECT_DASHBOARD_LIMIT
    });

    if (projectsResult.state !== "success") {
      if (projectsResult.state === "unauthorized") {
        clearStoredAccessToken();
      }

      setDashboard({ state: projectsResult.state });
      setLastUpdatedAt(null);
      return;
    }

    const projects = await Promise.all(
      projectsResult.projects.map(async (project) => {
        // 목록 응답에 점수 요약과 linked ScenarioRun이 포함되므로 상세 조회 없이 구성한다.
        const checkRunsResult = await fetchCheckRuns({
          projectId: project.id,
          accessToken,
          limit: PROJECT_TREND_RUN_LIMIT
        });
        const checkRuns = checkRunsResult.state === "success" ? checkRunsResult.checkRuns : [];

        return {
          project,
          checkRuns,
          latestCheckRun: checkRuns[0] ?? null,
          latestCheckRunState: checkRunsResult.state
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

  const dashboardSummary = useMemo(() => {
    if (dashboard.state !== "success") {
      return null;
    }

    const latestRuns = dashboard.projects
      .map((project) => project.latestCheckRun)
      .filter((checkRun): checkRun is CheckRunSummary => checkRun !== null);
    const activeCount = latestRuns.filter((checkRun) =>
      ACTIVE_CHECK_RUN_STATUSES.includes(checkRun.status)
    ).length;
    const failedCount = latestRuns.filter((checkRun) => checkRun.status === "FAILED").length;
    const linkedScenarioRuns = dashboard.projects.flatMap(
      (project) => project.latestCheckRun?.linked_scenario_runs ?? []
    );
    const scenarioFailureCount = linkedScenarioRuns.filter(
      (scenarioRun) => scenarioRun.status === "FAILED"
    ).length;

    return {
      projectCount: dashboard.projects.length,
      activeCount,
      failedCount,
      scenarioFailureCount
    };
  }, [dashboard]);

  async function handleStartCheckRun(project: Project) {
    const accessToken = getStoredAccessToken();

    if (!accessToken) {
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
      accessToken
    });

    if (result.state !== "success") {
      if (result.state === "unauthorized") {
        clearStoredAccessToken();
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
            <h1 className="text-2xl font-bold tracking-tight text-slate-900">대시보드</h1>
            <HealthInline health={health} />
            {lastUpdatedAt && (
              <span className="text-xs text-slate-400">갱신 {lastUpdatedAt}</span>
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

        {dashboardSummary && <StatStrip summary={dashboardSummary} />}

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
    ? "text-emerald-600"
    : health.state === "loading"
      ? "text-cyan-700"
      : "text-rose-600";

  return (
    <span className={`flex items-center gap-1.5 text-xs font-semibold ${textClassName}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${dotClassName}`} />
      서비스 {healthStatusCopy[health.state]}
    </span>
  );
}

type DashboardSummary = {
  projectCount: number;
  activeCount: number;
  failedCount: number;
  scenarioFailureCount: number;
};

function StatStrip({ summary }: { summary: DashboardSummary }) {
  return (
    <div className="grid grid-cols-2 rounded-2xl border border-slate-200 bg-white sm:grid-cols-4 sm:divide-x sm:divide-slate-200">
      <StatCell label="프로젝트" value={summary.projectCount} />
      <StatCell
        label="진행 중"
        tone={summary.activeCount > 0 ? "active" : "default"}
        value={summary.activeCount}
      />
      <StatCell
        label="최신 검사 실패"
        tone={summary.failedCount > 0 ? "danger" : "default"}
        value={summary.failedCount}
      />
      <StatCell
        label="시나리오 실패"
        tone={summary.scenarioFailureCount > 0 ? "danger" : "default"}
        value={summary.scenarioFailureCount}
      />
    </div>
  );
}

function StatCell({
  label,
  tone = "default",
  value
}: {
  label: string;
  tone?: "default" | "danger" | "active";
  value: number;
}) {
  const valueClassName =
    tone === "danger" && value > 0
      ? "text-rose-600"
      : tone === "active"
        ? "text-cyan-700"
        : "text-slate-900";

  return (
    <div className="px-4 py-3 text-center">
      <p className="text-xs font-semibold text-slate-400">{label}</p>
      <p className={`mt-0.5 text-xl font-bold ${valueClassName}`}>{value}</p>
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
    <article className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="text-base font-bold text-slate-900">{project.name}</h3>
            <span className="rounded-full border border-slate-200 px-2 py-0.5 text-[11px] font-semibold text-slate-500">
              {environmentLabel(project.environment)}
            </span>
            {project.is_verified ? (
              <span className="text-[11px] font-semibold text-emerald-600">인증됨</span>
            ) : (
              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700 ring-1 ring-amber-200">
                미인증
              </span>
            )}
          </div>
          <a
            className="mt-0.5 block truncate text-xs text-slate-400 transition hover:text-cyan-700"
            href={project.service_url}
            rel="noreferrer"
            target="_blank"
          >
            {project.service_url}
          </a>
        </div>
        <button
          className="shrink-0 rounded-xl bg-cyan-700 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-cyan-600 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
          disabled={!project.is_verified || startState === "starting"}
          onClick={() => onStartCheckRun(project)}
          type="button"
        >
          {startState === "starting" ? "요청 중" : project.is_verified ? "검사 시작" : "검증 필요"}
        </button>
      </div>

      {startState !== "idle" && startState !== "starting" && (
        <p className="mt-2 rounded-xl bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 ring-1 ring-rose-200">
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
        <p className="mt-2 truncate rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-200">
          {latestCheckRun.failure_reason}
        </p>
      )}

      {failedScenarioCount > 0 && (
        <p className="mt-2 rounded-xl bg-rose-50 px-3 py-2 text-xs font-semibold text-rose-700 ring-1 ring-rose-200">
          시나리오 실패 {failedScenarioCount}건 — 결과 페이지에서 step·스크린샷 근거를 확인하세요.
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-slate-100 pt-3">
        <FooterLink href={`/projects/${project.id}/check-runs`} label="검사 이력" />
        <FooterLink href={`/projects/${project.id}/scenarios`} label="시나리오" />
        <FooterLink href={`/projects/${project.id}/alerts`} label="알림" />
        <FooterLink href={`/projects/${project.id}/settings`} label="설정" />
      </div>
    </article>
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
    return "text-emerald-700";
  }

  if (status === "FAILED") {
    return "text-rose-700";
  }

  if (status === "CANCELLED") {
    return "text-slate-500";
  }

  return "text-cyan-700";
}

const riskChipClassName: Record<"STABLE" | "WARNING" | "RISK", string> = {
  STABLE: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  WARNING: "bg-amber-50 text-amber-700 ring-amber-200",
  RISK: "bg-rose-50 text-rose-700 ring-rose-200"
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
      <p className="mt-3 text-xs font-semibold text-rose-600">
        최신 검사를 불러오지 못했습니다 — 권한 또는 API 상태를 확인하세요.
      </p>
    );
  }

  if (!latestCheckRun) {
    return (
      <p className="mt-3 text-xs text-slate-400">
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
      <span className="min-w-0 truncate text-xs text-slate-500">
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
      className="text-xs font-semibold text-slate-500 transition hover:text-cyan-700"
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
