"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createCheckRun,
  fetchApiHealth,
  fetchCheckRunDetail,
  fetchCheckRuns,
  fetchProjects,
  type CheckRunDetailResult,
  type CheckRunListResult,
  type CheckRunStatus,
  type CheckRunSummary,
  type HealthCheckResult,
  type Project,
  type ScenarioRun
} from "@/lib/api";
import { clearStoredAccessToken, getStoredAccessToken } from "@/lib/auth";
import { formatDateTime, formatNullableDateTime } from "@/lib/format";
import {
  Badge,
  CheckRunStatusBadge,
  EmptyState,
  LinkButton,
  LoginRequiredNotice,
  Metric,
  Notice,
  RefreshButton,
  ScenarioRunStatusBadge
} from "@/components/ui";

const PROJECT_DASHBOARD_LIMIT = 20;
const ACTIVE_CHECK_RUN_STATUSES: CheckRunStatus[] = ["QUEUED", "RUNNING", "ANALYZING"];

const healthStatusCopy: Record<HealthCheckResult["state"], string> = {
  loading: "확인 중",
  available: "연결됨",
  unavailable: "연결 실패"
};

type DashboardProject = {
  project: Project;
  latestCheckRun: CheckRunSummary | null;
  latestCheckRunState: CheckRunListResult["state"];
  latestLinkedScenarioRuns: ScenarioRun[];
  latestLinkedScenarioRunsState: CheckRunDetailResult["state"] | "not-requested";
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

export default function Home() {
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
        const checkRunsResult = await fetchCheckRuns({
          projectId: project.id,
          accessToken,
          limit: 1
        });
        const latestCheckRun =
          checkRunsResult.state === "success" ? (checkRunsResult.checkRuns[0] ?? null) : null;

        if (!latestCheckRun) {
          return {
            project,
            latestCheckRun,
            latestCheckRunState: checkRunsResult.state,
            latestLinkedScenarioRuns: [],
            latestLinkedScenarioRunsState: "not-requested" as const
          };
        }

        const checkRunDetailResult = await fetchCheckRunDetail({
          projectId: project.id,
          checkRunId: latestCheckRun.id,
          accessToken
        });

        return {
          project,
          latestCheckRun,
          latestCheckRunState: checkRunsResult.state,
          latestLinkedScenarioRuns:
            checkRunDetailResult.state === "success"
              ? checkRunDetailResult.checkRun.linked_scenario_runs
              : [],
          latestLinkedScenarioRunsState: checkRunDetailResult.state
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
      (project) => project.latestLinkedScenarioRuns
    );
    const scenarioFailureCount = linkedScenarioRuns.filter(
      (scenarioRun) => scenarioRun.status === "FAILED"
    ).length;

    return {
      projectCount: dashboard.projects.length,
      latestRunCount: latestRuns.length,
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
      <section className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-12">
        <div className="max-w-4xl">
          <p className="mb-4 text-sm font-semibold uppercase tracking-[0.32em] text-cyan-700">
            AI Manager
          </p>
          <h1 className="text-4xl font-bold tracking-tight text-cyan-600 sm:text-6xl">
            AI가 검사하고, 진단하고, 처방합니다
          </h1>
          <p className="mt-6 text-lg leading-8 text-slate-600">
            AIM은 프로젝트, 서비스 URL, 최신 검사 상태를 모아 배포 후 서비스가 실제로
            안정적인지 빠르게 확인할 수 있게 돕습니다.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-4">
          <StatusCard health={health} />
          <MetricCard
            label="Projects"
            value={dashboardSummary?.projectCount ?? "-"}
            description="현재 세션으로 조회한 프로젝트 수"
          />
          <MetricCard
            label="Latest failures"
            value={dashboardSummary?.failedCount ?? "-"}
            description="최신 CheckRun이 실패한 프로젝트"
            tone={dashboardSummary && dashboardSummary.failedCount > 0 ? "danger" : "default"}
          />
          <MetricCard
            label="Scenario failures"
            value={dashboardSummary?.scenarioFailureCount ?? "-"}
            description="최신 CheckRun에 연결된 실패 ScenarioRun"
            tone={
              dashboardSummary && dashboardSummary.scenarioFailureCount > 0
                ? "danger"
                : "default"
            }
          />
        </div>

        <DashboardPanel
          checkRunStartStates={checkRunStartStates}
          dashboard={dashboard}
          lastUpdatedAt={lastUpdatedAt}
          onRefresh={() => void loadDashboard()}
          onStartCheckRun={handleStartCheckRun}
        />
      </section>
    </main>
  );
}

function DashboardPanel({
  checkRunStartStates,
  dashboard,
  lastUpdatedAt,
  onRefresh,
  onStartCheckRun
}: {
  checkRunStartStates: Record<string, CheckRunStartState>;
  dashboard: DashboardState;
  lastUpdatedAt: string | null;
  onRefresh: () => void;
  onStartCheckRun: (project: Project) => void;
}) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-200/60">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">Project dashboard</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
            로그인 세션으로 프로젝트와 최신 CheckRun을 자동 조회합니다.
          </p>
          {lastUpdatedAt && <p className="mt-2 text-xs text-slate-400">마지막 갱신: {lastUpdatedAt}</p>}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {dashboard.state !== "signed-out" && (
            <LinkButton href="/projects/new" label="새 Project" variant="primary" />
          )}
          <RefreshButton
            isLoading={dashboard.state === "loading"}
            label="Dashboard 갱신"
            onClick={onRefresh}
          />
        </div>
      </div>

      <div className="mt-6">
        <DashboardContent
          checkRunStartStates={checkRunStartStates}
          dashboard={dashboard}
          onStartCheckRun={onStartCheckRun}
        />
      </div>
    </section>
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
    return <EmptyState description="프로젝트와 최신 CheckRun을 불러오는 중입니다." title="불러오는 중" />;
  }

  if (dashboard.state === "unauthorized") {
    return <LoginRequiredNotice expired />;
  }

  if (dashboard.state === "unavailable") {
    return (
      <Notice
        description="서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
        title="Dashboard 요청 실패"
        tone="danger"
      />
    );
  }

  if (dashboard.projects.length === 0) {
    return (
      <EmptyState
        description="현재 계정에 등록된 프로젝트가 없습니다. 새 Project 버튼으로 첫 서비스를 등록하세요."
        title="등록된 프로젝트 없음"
      />
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
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
  const { latestCheckRun, latestCheckRunState, project } = dashboardProject;

  return (
    <article className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="mb-3 flex flex-wrap gap-2">
            <Badge label={project.environment} />
            <Badge label={project.is_verified ? "verified" : "unverified"} tone={project.is_verified ? "success" : "warning"} />
          </div>
          <h3 className="text-xl font-bold text-slate-900">{project.name}</h3>
          <a
            className="mt-2 block break-all text-sm text-cyan-700 hover:text-cyan-700"
            href={project.service_url}
            rel="noreferrer"
            target="_blank"
          >
            {project.service_url}
          </a>
        </div>
        <div className="flex flex-wrap gap-2">
          <LinkButton href={`/projects/${project.id}/settings`} label="Settings" />
          <LinkButton href={`/projects/${project.id}/check-runs`} label="Runs" />
          <LinkButton href={`/projects/${project.id}/scenarios`} label="Scenarios" />
          <LinkButton href={`/projects/${project.id}/alerts`} label="Alerts" />
          <button
            className="rounded-2xl bg-cyan-600 px-4 py-2 text-sm font-bold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
            disabled={!project.is_verified || startState === "starting"}
            onClick={() => onStartCheckRun(project)}
            type="button"
          >
            {startState === "starting"
              ? "검사 요청 중"
              : project.is_verified
                ? "검사 시작"
                : "검증 필요"}
          </button>
        </div>
      </div>

      {project.description && <p className="mt-4 text-sm leading-6 text-slate-500">{project.description}</p>}

      <CheckRunStartNotice project={project} startState={startState} />

      <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-3">
        <Metric label="Scan interval" value={`${project.scan_interval_minutes}분`} />
        <Metric label="Response threshold" value={`${project.response_time_threshold_ms}ms`} />
        <Metric label="Quality threshold" value={`${project.quality_score_threshold}`} />
      </dl>

      <div className="mt-5 border-t border-slate-200 pt-5">
        <LatestCheckRunCard
          latestCheckRun={latestCheckRun}
          latestCheckRunState={latestCheckRunState}
          latestLinkedScenarioRuns={dashboardProject.latestLinkedScenarioRuns}
          latestLinkedScenarioRunsState={dashboardProject.latestLinkedScenarioRunsState}
          projectId={project.id}
        />
      </div>
    </article>
  );
}

function CheckRunStartNotice({
  project,
  startState
}: {
  project: Project;
  startState: CheckRunStartState;
}) {
  if (!project.is_verified) {
    return (
      <div className="mt-4">
        <Notice
          description="Domain verification이 완료되어야 수동 CheckRun을 시작할 수 있습니다."
          title="검증 필요"
        />
      </div>
    );
  }

  if (startState === "idle" || startState === "starting") {
    return null;
  }

  return (
    <div className="mt-4">
      <Notice
        description={checkRunStartStateMessage[startState]}
        title="CheckRun 생성 실패"
        tone="danger"
      />
    </div>
  );
}

function LatestCheckRunCard({
  latestCheckRun,
  latestCheckRunState,
  latestLinkedScenarioRuns,
  latestLinkedScenarioRunsState,
  projectId
}: {
  latestCheckRun: CheckRunSummary | null;
  latestCheckRunState: CheckRunListResult["state"];
  latestLinkedScenarioRuns: ScenarioRun[];
  latestLinkedScenarioRunsState: CheckRunDetailResult["state"] | "not-requested";
  projectId: string;
}) {
  if (latestCheckRunState !== "success") {
    return (
      <Notice
        description="이 프로젝트의 최신 CheckRun을 불러오지 못했습니다. 권한 또는 API 상태를 확인하세요."
        title="최신 CheckRun 조회 실패"
        tone="danger"
      />
    );
  }

  if (!latestCheckRun) {
    return (
      <EmptyState
        compact
        description="아직 실행된 CheckRun이 없습니다. 검사 시작 버튼으로 첫 검사를 시작할 수 있습니다."
        title="최신 CheckRun 없음"
      />
    );
  }

  const isFailed = latestCheckRun.status === "FAILED";
  const isActive = ACTIVE_CHECK_RUN_STATUSES.includes(latestCheckRun.status);

  return (
    <div
      className={`rounded-2xl border p-4 ${
        isFailed
          ? "border-rose-300 bg-rose-50"
          : isActive
            ? "border-cyan-300 bg-cyan-50"
            : "border-slate-200 bg-white"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            Latest CheckRun
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <CheckRunStatusBadge status={latestCheckRun.status} />
            <span className="rounded-full bg-white px-3 py-1 text-xs font-bold text-slate-600 ring-1 ring-slate-200">
              {latestCheckRun.trigger_source}
            </span>
          </div>
        </div>
        <LinkButton
          href={`/projects/${projectId}/check-runs/${latestCheckRun.id}`}
          label="결과 보기"
          variant="dark"
        />
      </div>

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <Metric label="Queued" value={formatDateTime(latestCheckRun.queued_at)} />
        <Metric label="Finished" value={formatNullableDateTime(latestCheckRun.finished_at)} />
      </dl>

      {latestCheckRun.failure_reason && (
        <p className="mt-4 rounded-2xl bg-rose-100 p-3 text-sm leading-6 text-rose-800">
          {latestCheckRun.failure_reason}
        </p>
      )}

      <LatestScenarioRunAccess
        projectId={projectId}
        scenarioRuns={latestLinkedScenarioRuns}
        state={latestLinkedScenarioRunsState}
      />
    </div>
  );
}

function LatestScenarioRunAccess({
  projectId,
  scenarioRuns,
  state
}: {
  projectId: string;
  scenarioRuns: ScenarioRun[];
  state: CheckRunDetailResult["state"] | "not-requested";
}) {
  if (state === "not-requested") {
    return null;
  }

  if (state !== "success") {
    return (
      <div className="mt-4">
        <Notice
          description="최신 CheckRun의 linked ScenarioRun 요약을 불러오지 못했습니다. CheckRun 결과 화면에서 다시 확인하세요."
          title="ScenarioRun 요약 조회 실패"
          tone="danger"
        />
      </div>
    );
  }

  if (scenarioRuns.length === 0) {
    return (
      <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <p className="text-sm font-semibold text-slate-900">Linked ScenarioRun 없음</p>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          최신 CheckRun에 연결된 browser scenario 실행 이력이 없습니다.
        </p>
      </div>
    );
  }

  const latestScenarioRun = getLatestScenarioRun(scenarioRuns);
  const summary = summarizeDashboardScenarioRuns(scenarioRuns);

  return (
    <div className="mt-4 rounded-2xl border border-cyan-200 bg-cyan-50/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-cyan-700">최근 linked ScenarioRun</p>
          <p className="mt-2 text-xs text-slate-500">
            실패 {summary.failed}개 · 진행 중 {summary.active}개 · 전체 {summary.total}개
          </p>
        </div>
        {latestScenarioRun && <ScenarioRunStatusBadge status={latestScenarioRun.status} />}
      </div>

      {latestScenarioRun && (
        <>
          {latestScenarioRun.failure_reason && (
            <p className="mt-3 rounded-2xl border border-rose-200 bg-rose-100 p-3 text-sm text-rose-800">
              {latestScenarioRun.failure_reason}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              className="rounded-xl bg-cyan-600 px-3 py-2 text-xs font-bold text-white transition hover:bg-cyan-500"
              href={`/projects/${projectId}/scenarios/${latestScenarioRun.scenario_id}/runs/${latestScenarioRun.id}`}
            >
              최근 결과 보기
            </Link>
            <Link
              className="rounded-xl border border-cyan-300 bg-cyan-50 px-3 py-2 text-xs font-bold text-cyan-700 transition hover:border-cyan-500 hover:bg-cyan-100"
              href={`/projects/${projectId}/scenarios/${latestScenarioRun.scenario_id}/runs`}
            >
              ScenarioRun 목록
            </Link>
          </div>
        </>
      )}
    </div>
  );
}

function StatusCard({ health }: { health: HealthCheckResult }) {
  const isAvailable = health.state === "available";
  const badgeClassName = isAvailable
    ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
    : health.state === "loading"
      ? "bg-cyan-50 text-cyan-700 ring-cyan-200"
      : "bg-rose-50 text-rose-700 ring-rose-200";

  return (
    <article className="rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-200/60">
      <div className="mb-5 flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">서비스 상태</h2>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${badgeClassName}`}>
          {healthStatusCopy[health.state]}
        </span>
      </div>
      <p className="text-sm leading-6 text-slate-600">
        {health.state === "available" && "모든 기능을 정상적으로 사용할 수 있습니다."}
        {health.state === "loading" && "서버 상태를 확인하는 중입니다."}
        {health.state === "unavailable" &&
          "서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요."}
      </p>
    </article>
  );
}

function MetricCard({
  description,
  label,
  tone = "default",
  value
}: {
  description: string;
  label: string;
  tone?: "default" | "danger";
  value: number | string;
}) {
  return (
    <article
      className={`rounded-3xl border p-6 ${
        tone === "danger" ? "border-rose-200 bg-rose-50" : "border-slate-200 bg-white"
      }`}
    >
      <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-400">{label}</p>
      <p className="mt-3 text-4xl font-bold text-slate-900">{value}</p>
      <p className="mt-3 text-sm leading-6 text-slate-500">{description}</p>
    </article>
  );
}

type DashboardScenarioRunSummary = {
  total: number;
  failed: number;
  active: number;
};

function summarizeDashboardScenarioRuns(
  scenarioRuns: ScenarioRun[]
): DashboardScenarioRunSummary {
  return scenarioRuns.reduce<DashboardScenarioRunSummary>(
    (summary, scenarioRun) => {
      if (scenarioRun.status === "FAILED") {
        summary.failed += 1;
      }

      if (scenarioRun.status === "QUEUED" || scenarioRun.status === "RUNNING") {
        summary.active += 1;
      }

      return summary;
    },
    {
      total: scenarioRuns.length,
      failed: 0,
      active: 0
    }
  );
}

function getLatestScenarioRun(scenarioRuns: ScenarioRun[]): ScenarioRun | null {
  return scenarioRuns.reduce<ScenarioRun | null>((latest, scenarioRun) => {
    if (!latest) {
      return scenarioRun;
    }

    return new Date(scenarioRun.queued_at).getTime() > new Date(latest.queued_at).getTime()
      ? scenarioRun
      : latest;
  }, null);
}

const checkRunStartStateMessage: Record<
  Exclude<CheckRunStartState, "idle" | "starting">,
  string
> = {
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "Project를 찾을 수 없습니다. Dashboard를 다시 갱신하세요.",
  conflict: "Project가 아직 domain verification을 통과하지 못했습니다.",
  unavailable: "검사 요청에 실패했습니다. 잠시 후 다시 시도하세요."
};
