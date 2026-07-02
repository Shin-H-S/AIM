"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  createCheckRun,
  fetchApiHealth,
  fetchCheckRuns,
  fetchCurrentUser,
  fetchProjects,
  getApiBaseUrl,
  logoutUser,
  type CheckRunListResult,
  type CheckRunStatus,
  type CheckRunSummary,
  type HealthCheckResult,
  type Project,
  type User
} from "@/lib/api";
import { clearStoredAccessToken, getStoredAccessToken, storeAccessToken } from "@/lib/auth";

const PROJECT_DASHBOARD_LIMIT = 20;
const ACTIVE_CHECK_RUN_STATUSES: CheckRunStatus[] = ["QUEUED", "RUNNING", "ANALYZING"];

const healthStatusCopy: Record<HealthCheckResult["state"], string> = {
  loading: "확인 중",
  available: "연결됨",
  unavailable: "연결 실패"
};

const checkRunStatusCopy: Record<CheckRunStatus, string> = {
  QUEUED: "대기 중",
  RUNNING: "실행 중",
  ANALYZING: "분석 중",
  COMPLETED: "완료",
  FAILED: "실패",
  CANCELLED: "취소됨"
};

type DashboardProject = {
  project: Project;
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
      state: "idle";
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
  const [accessToken, setAccessToken] = useState("");
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [dashboard, setDashboard] = useState<DashboardState>({ state: "idle" });
  const [checkRunStartStates, setCheckRunStartStates] = useState<
    Record<string, CheckRunStartState>
  >({});
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const trimmedToken = accessToken.trim();

  const loadDashboardWithToken = useCallback(async (token: string) => {
    const normalizedToken = token.trim();

    if (!normalizedToken) {
      clearStoredAccessToken();
      setCurrentUser(null);
      setDashboard({ state: "idle" });
      setLastUpdatedAt(null);
      return;
    }

    setDashboard({ state: "loading" });

    const currentUserResult = await fetchCurrentUser({
      accessToken: normalizedToken
    });

    if (currentUserResult.state !== "success") {
      if (currentUserResult.state === "unauthorized") {
        clearStoredAccessToken();
      }

      setCurrentUser(null);
      setDashboard({ state: currentUserResult.state });
      setLastUpdatedAt(null);
      return;
    }

    setCurrentUser(currentUserResult.user);
    storeAccessToken(normalizedToken);

    const projectsResult = await fetchProjects({
      accessToken: normalizedToken,
      limit: PROJECT_DASHBOARD_LIMIT
    });

    if (projectsResult.state !== "success") {
      if (projectsResult.state === "unauthorized") {
        clearStoredAccessToken();
        setCurrentUser(null);
      }

      setDashboard({ state: projectsResult.state });
      setLastUpdatedAt(null);
      return;
    }

    const projects = await Promise.all(
      projectsResult.projects.map(async (project) => {
        const checkRunsResult = await fetchCheckRuns({
          projectId: project.id,
          accessToken: normalizedToken,
          limit: 1
        });

        return {
          project,
          latestCheckRun:
            checkRunsResult.state === "success" ? (checkRunsResult.checkRuns[0] ?? null) : null,
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
    const storedAccessToken = getStoredAccessToken();

    if (!storedAccessToken) {
      return;
    }

    queueMicrotask(() => {
      setAccessToken(storedAccessToken);
      void loadDashboardWithToken(storedAccessToken);
    });
  }, [loadDashboardWithToken]);

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

    return {
      projectCount: dashboard.projects.length,
      latestRunCount: latestRuns.length,
      activeCount,
      failedCount
    };
  }, [dashboard]);

  function handleDashboardSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadDashboardWithToken(trimmedToken);
  }

  async function handleStartCheckRun(project: Project) {
    if (!trimmedToken) {
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
      accessToken: trimmedToken
    });

    if (result.state !== "success") {
      if (result.state === "unauthorized") {
        clearStoredAccessToken();
        setAccessToken("");
        setCurrentUser(null);
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

  function handleLogout() {
    if (trimmedToken) {
      void logoutUser({
        accessToken: trimmedToken
      });
    }

    clearStoredAccessToken();
    setAccessToken("");
    setCurrentUser(null);
    setCheckRunStartStates({});
    setDashboard({ state: "idle" });
    setLastUpdatedAt(null);
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <section className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-8 px-6 py-12">
        <div className="max-w-4xl">
          <p className="mb-4 text-sm font-semibold uppercase tracking-[0.32em] text-cyan-300">
            AIM MVP Dashboard
          </p>
          <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
            프로젝트별 최신 CheckRun을 한눈에 확인합니다
          </h1>
          <p className="mt-6 text-lg leading-8 text-slate-300">
            AIM은 프로젝트, 서비스 URL, 최신 검사 상태를 모아 배포 후 서비스가 실제로
            안정적인지 빠르게 확인할 수 있게 돕습니다.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <StatusCard health={health} />
          <MetricCard
            label="Projects"
            value={dashboardSummary?.projectCount ?? "-"}
            description="현재 토큰으로 조회한 프로젝트 수"
          />
          <MetricCard
            label="Latest failures"
            value={dashboardSummary?.failedCount ?? "-"}
            description="최신 CheckRun이 실패한 프로젝트"
            tone={dashboardSummary && dashboardSummary.failedCount > 0 ? "danger" : "default"}
          />
        </div>

        <DashboardPanel
          accessToken={accessToken}
          checkRunStartStates={checkRunStartStates}
          currentUser={currentUser}
          dashboard={dashboard}
          lastUpdatedAt={lastUpdatedAt}
          onAccessTokenChange={(value) => {
            setAccessToken(value);
            setCurrentUser(null);
            setCheckRunStartStates({});
            setDashboard({ state: "idle" });
            setLastUpdatedAt(null);
          }}
          onLogout={handleLogout}
          onStartCheckRun={handleStartCheckRun}
          onSubmit={handleDashboardSubmit}
          trimmedToken={trimmedToken}
        />
      </section>
    </main>
  );
}

function DashboardPanel({
  accessToken,
  checkRunStartStates,
  currentUser,
  dashboard,
  lastUpdatedAt,
  onAccessTokenChange,
  onLogout,
  onStartCheckRun,
  onSubmit,
  trimmedToken
}: {
  accessToken: string;
  checkRunStartStates: Record<string, CheckRunStartState>;
  currentUser: User | null;
  dashboard: DashboardState;
  lastUpdatedAt: string | null;
  onAccessTokenChange: (value: string) => void;
  onLogout: () => void;
  onStartCheckRun: (project: Project) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  trimmedToken: string;
}) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl shadow-cyan-950/20">
      <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-100">Project dashboard</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
            로그인 페이지에서 저장한 access token을 자동으로 사용합니다. 필요하면 access
            token을 직접 입력해 Dashboard를 갱신할 수도 있습니다.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            {currentUser ? (
              <>
                <span className="rounded-full bg-emerald-400/10 px-3 py-1 text-xs font-bold text-emerald-200 ring-1 ring-emerald-400/20">
                  로그인됨: {currentUser.email}
                </span>
                <button
                  className="rounded-full border border-white/10 px-3 py-1 text-xs font-bold text-slate-300 transition hover:border-cyan-300/50 hover:text-cyan-100"
                  onClick={onLogout}
                  type="button"
                >
                  로그아웃
                </button>
                <Link
                  className="rounded-full bg-cyan-300 px-3 py-1 text-xs font-bold text-slate-950 transition hover:bg-cyan-200"
                  href="/projects/new"
                >
                  새 Project
                </Link>
              </>
            ) : (
              <>
                <Link
                  className="rounded-full bg-cyan-300 px-3 py-1 text-xs font-bold text-slate-950 transition hover:bg-cyan-200"
                  href="/signup"
                >
                  회원가입
                </Link>
                <Link
                  className="rounded-full border border-white/10 px-3 py-1 text-xs font-bold text-slate-300 transition hover:border-cyan-300/50 hover:text-cyan-100"
                  href="/login"
                >
                  로그인하기
                </Link>
              </>
            )}
          </div>
          {lastUpdatedAt && <p className="mt-2 text-xs text-slate-500">마지막 갱신: {lastUpdatedAt}</p>}
        </div>

        <form className="flex w-full flex-col gap-3 lg:max-w-xl" onSubmit={onSubmit}>
          <label className="text-sm font-semibold text-slate-300" htmlFor="dashboard-token">
            Access token
          </label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              className="min-w-0 flex-1 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition placeholder:text-slate-600 focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
              id="dashboard-token"
              onChange={(event) => onAccessTokenChange(event.target.value)}
              placeholder="Bearer 없이 access_token만 입력"
              type="password"
              value={accessToken}
            />
            <button
              className="rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!trimmedToken || dashboard.state === "loading"}
              type="submit"
            >
              {dashboard.state === "loading" ? "불러오는 중" : "Dashboard 갱신"}
            </button>
          </div>
        </form>
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
  if (dashboard.state === "idle") {
    return (
      <EmptyState
        description="로그인 페이지에서 로그인하거나 access token을 직접 입력하고 Dashboard를 갱신하세요."
        title="Dashboard 대기 중"
      />
    );
  }

  if (dashboard.state === "loading") {
    return <EmptyState description="프로젝트와 최신 CheckRun을 불러오는 중입니다." title="불러오는 중" />;
  }

  if (dashboard.state === "unauthorized") {
    return (
      <Notice
        description="토큰이 없거나 만료되었습니다. 로그인 페이지에서 다시 로그인하세요."
        title="인증 실패"
        tone="danger"
      />
    );
  }

  if (dashboard.state === "unavailable") {
    return (
      <Notice
        description="API 서버 상태와 NEXT_PUBLIC_API_URL 설정을 확인한 뒤 다시 시도하세요."
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
    <article className="rounded-3xl border border-white/10 bg-slate-950/40 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="mb-3 flex flex-wrap gap-2">
            <Badge label={project.environment} />
            <Badge label={project.is_verified ? "verified" : "unverified"} tone={project.is_verified ? "success" : "warning"} />
          </div>
          <h3 className="text-xl font-bold text-slate-100">{project.name}</h3>
          <a
            className="mt-2 block break-all text-sm text-cyan-200 hover:text-cyan-100"
            href={project.service_url}
            rel="noreferrer"
            target="_blank"
          >
            {project.service_url}
          </a>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            className="rounded-2xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
            href={`/projects/${project.id}/settings`}
          >
            Settings
          </Link>
          <Link
            className="rounded-2xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
            href={`/projects/${project.id}/scenarios`}
          >
            Scenarios
          </Link>
          <button
            className="rounded-2xl bg-cyan-300 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
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

      {project.description && <p className="mt-4 text-sm leading-6 text-slate-400">{project.description}</p>}

      <CheckRunStartNotice project={project} startState={startState} />

      <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-3">
        <Metric label="Scan interval" value={`${project.scan_interval_minutes}분`} />
        <Metric label="Response threshold" value={`${project.response_time_threshold_ms}ms`} />
        <Metric label="Quality threshold" value={`${project.quality_score_threshold}`} />
      </dl>

      <div className="mt-5 border-t border-white/10 pt-5">
        <LatestCheckRunCard
          latestCheckRun={latestCheckRun}
          latestCheckRunState={latestCheckRunState}
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
  projectId
}: {
  latestCheckRun: CheckRunSummary | null;
  latestCheckRunState: CheckRunListResult["state"];
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
        description="아직 실행된 CheckRun이 없습니다. CheckRun 생성 UI가 연결되면 여기에서 첫 검사를 시작할 수 있습니다."
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
          ? "border-rose-400/30 bg-rose-400/10"
          : isActive
            ? "border-cyan-300/30 bg-cyan-300/10"
            : "border-white/10 bg-white/[0.03]"
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
            Latest CheckRun
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <StatusBadge status={latestCheckRun.status} />
            <span className="rounded-full bg-slate-900 px-3 py-1 text-xs font-bold text-slate-300 ring-1 ring-white/10">
              {latestCheckRun.trigger_source}
            </span>
          </div>
        </div>
        <Link
          className="rounded-2xl bg-slate-100 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-200"
          href={`/projects/${projectId}/check-runs/${latestCheckRun.id}`}
        >
          결과 보기
        </Link>
      </div>

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <Metric label="Queued" value={formatDateTime(latestCheckRun.queued_at)} />
        <Metric label="Finished" value={formatNullableDateTime(latestCheckRun.finished_at)} />
      </dl>

      {latestCheckRun.failure_reason && (
        <p className="mt-4 rounded-2xl bg-rose-950/40 p-3 text-sm leading-6 text-rose-100">
          {latestCheckRun.failure_reason}
        </p>
      )}
    </div>
  );
}

function StatusCard({ health }: { health: HealthCheckResult }) {
  const isAvailable = health.state === "available";
  const apiBaseUrlLabel = getApiBaseUrlLabel();
  const badgeClassName = isAvailable
    ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20"
    : health.state === "loading"
      ? "bg-cyan-400/10 text-cyan-300 ring-cyan-400/20"
      : "bg-rose-400/10 text-rose-300 ring-rose-400/20";

  return (
    <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-6 shadow-2xl shadow-cyan-950/20">
      <div className="mb-5 flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">API 상태</h2>
        <span className={`rounded-full px-3 py-1 text-xs font-semibold ring-1 ${badgeClassName}`}>
          {healthStatusCopy[health.state]}
        </span>
      </div>
      <p className="text-sm leading-6 text-slate-300">
        프론트엔드는 <code className="text-cyan-200">{apiBaseUrlLabel}</code>의{" "}
        <code className="text-cyan-200">/health</code> 응답을 확인합니다.
      </p>
      <p className="mt-4 text-sm text-slate-400">
        {health.state === "available" && `서비스: ${health.service}`}
        {health.state === "loading" && "FastAPI 서버 상태를 불러오는 중입니다."}
        {health.state === "unavailable" &&
          "API 서버가 실행 중인지, NEXT_PUBLIC_API_URL 값이 맞는지 확인하세요."}
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
        tone === "danger" ? "border-rose-400/20 bg-rose-400/10" : "border-white/10 bg-white/[0.03]"
      }`}
    >
      <p className="text-sm font-semibold uppercase tracking-[0.24em] text-slate-500">{label}</p>
      <p className="mt-3 text-4xl font-bold text-slate-100">{value}</p>
      <p className="mt-3 text-sm leading-6 text-slate-400">{description}</p>
    </article>
  );
}

function StatusBadge({ status }: { status: CheckRunStatus }) {
  const className =
    status === "COMPLETED"
      ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20"
      : status === "FAILED"
        ? "bg-rose-400/10 text-rose-300 ring-rose-400/20"
        : status === "CANCELLED"
          ? "bg-slate-500/10 text-slate-300 ring-slate-400/20"
          : "bg-cyan-400/10 text-cyan-300 ring-cyan-400/20";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${className}`}>
      {checkRunStatusCopy[status]}
    </span>
  );
}

function Badge({
  label,
  tone = "default"
}: {
  label: string;
  tone?: "default" | "success" | "warning";
}) {
  const className =
    tone === "success"
      ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20"
      : tone === "warning"
        ? "bg-amber-400/10 text-amber-300 ring-amber-400/20"
        : "bg-slate-700/80 text-slate-200 ring-white/10";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${className}`}>
      {label}
    </span>
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
  description,
  title,
  tone = "info"
}: {
  description: string;
  title: string;
  tone?: "info" | "danger";
}) {
  return (
    <div
      className={`rounded-2xl border p-4 ${
        tone === "danger"
          ? "border-rose-400/20 bg-rose-400/10 text-rose-100"
          : "border-cyan-300/20 bg-cyan-300/10 text-cyan-100"
      }`}
    >
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-2 text-sm leading-6 opacity-85">{description}</p>
    </div>
  );
}

function EmptyState({
  compact = false,
  description,
  title
}: {
  compact?: boolean;
  description: string;
  title: string;
}) {
  return (
    <div className={`rounded-2xl border border-white/10 bg-slate-950/50 ${compact ? "p-4" : "p-6"}`}>
      <h3 className="font-semibold text-slate-100">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-400">{description}</p>
    </div>
  );
}

function getApiBaseUrlLabel() {
  try {
    return getApiBaseUrl();
  } catch {
    return "잘못된 NEXT_PUBLIC_API_URL";
  }
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function formatNullableDateTime(value: string | null) {
  return value ? formatDateTime(value) : "아직 없음";
}

const checkRunStartStateMessage: Record<
  Exclude<CheckRunStartState, "idle" | "starting">,
  string
> = {
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "Project를 찾을 수 없습니다. Dashboard를 다시 갱신하세요.",
  conflict: "Project가 아직 domain verification을 통과하지 못했습니다.",
  unavailable: "Scan queue 또는 API 서버 상태를 확인한 뒤 다시 시도하세요."
};
