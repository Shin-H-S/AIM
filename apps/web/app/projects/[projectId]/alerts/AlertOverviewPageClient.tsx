"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchProject,
  fetchProjectAlerts,
  fetchProjectIncidents,
  getApiBaseUrl,
  retryAlert,
  updateProject,
  type Alert,
  type AlertListResult,
  type Incident,
  type IncidentListResult,
  type Project,
  type ProjectDetailResult,
  type RetryAlertResult
} from "@/lib/api";
import { clearStoredAccessTokenIfMatches, getStoredAccessToken } from "@/lib/auth";

const LIST_LIMIT = 20;

type LoadState = "idle" | "loading";
type AlertStatusFilter = "ALL" | "PENDING" | "SENT" | "FAILED";
type AlertSettingsSubmitState =
  | "idle"
  | "submitting"
  | "success"
  | "invalid"
  | "unauthorized"
  | "not-found"
  | "unavailable";

type AlertSettingsFormState = {
  alertEmailEnabled: boolean;
  alertRecipientEmail: string;
};

type RetryAlertFeedback = {
  alertId: string;
  state: Exclude<RetryAlertResult["state"], "success"> | "success";
  message: string;
};

type AlertStatusCounts = Record<AlertStatusFilter, number>;

export function AlertOverviewPageClient({ projectId }: { projectId: string }) {
  const [accessToken, setAccessToken] = useState("");
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [projectResult, setProjectResult] = useState<ProjectDetailResult | null>(null);
  const [incidentResult, setIncidentResult] = useState<IncidentListResult | null>(null);
  const [alertResult, setAlertResult] = useState<AlertListResult | null>(null);
  const [settingsForm, setSettingsForm] = useState<AlertSettingsFormState>({
    alertEmailEnabled: true,
    alertRecipientEmail: ""
  });
  const [settingsSubmitState, setSettingsSubmitState] =
    useState<AlertSettingsSubmitState>("idle");
  const [settingsSubmitMessage, setSettingsSubmitMessage] = useState<string | null>(null);
  const [retryingAlertId, setRetryingAlertId] = useState<string | null>(null);
  const [retryFeedback, setRetryFeedback] = useState<RetryAlertFeedback | null>(null);
  const [alertStatusFilter, setAlertStatusFilter] = useState<AlertStatusFilter>("ALL");
  const [hasMoreAlerts, setHasMoreAlerts] = useState(false);
  const [isLoadingMoreAlerts, setIsLoadingMoreAlerts] = useState(false);
  const [alertListMessage, setAlertListMessage] = useState<string | null>(null);
  const [hasCheckedStoredToken, setHasCheckedStoredToken] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const trimmedToken = accessToken.trim();

  const loadOverview = useCallback(
    async (token: string) => {
      const normalizedToken = token.trim();

      if (!normalizedToken) {
        setProjectResult(null);
        setIncidentResult(null);
        setAlertResult(null);
        setRetryFeedback(null);
        setRetryingAlertId(null);
        setHasMoreAlerts(false);
        setIsLoadingMoreAlerts(false);
        setAlertListMessage(null);
        setLastUpdatedAt(null);
        return;
      }

      setLoadState("loading");
      setAlertListMessage(null);
      const [nextProjectResult, nextIncidentResult, nextAlertResult] = await Promise.all([
        fetchProject({
          projectId,
          accessToken: normalizedToken
        }),
        fetchProjectIncidents({
          projectId,
          accessToken: normalizedToken,
          limit: LIST_LIMIT
        }),
        fetchProjectAlerts({
          projectId,
          accessToken: normalizedToken,
          limit: LIST_LIMIT
        })
      ]);

      if (
        nextProjectResult.state === "unauthorized" ||
        nextIncidentResult.state === "unauthorized" ||
        nextAlertResult.state === "unauthorized"
      ) {
        clearStoredAccessTokenIfMatches(normalizedToken);
      }

      setProjectResult(nextProjectResult);
      setIncidentResult(nextIncidentResult);
      setAlertResult(nextAlertResult);
      setHasMoreAlerts(
        nextAlertResult.state === "success" && nextAlertResult.alerts.length === LIST_LIMIT
      );
      if (nextProjectResult.state === "success") {
        setSettingsForm(formFromProjectAlertSettings(nextProjectResult.project));
        setSettingsSubmitState("idle");
        setSettingsSubmitMessage(null);
      }
      setLastUpdatedAt(new Date().toLocaleTimeString("ko-KR"));
      setLoadState("idle");
    },
    [projectId]
  );

  const refresh = useCallback(async () => {
    await loadOverview(trimmedToken);
  }, [loadOverview, trimmedToken]);

  useEffect(() => {
    const storedAccessToken = getStoredAccessToken();

    queueMicrotask(() => {
      setHasCheckedStoredToken(true);

      if (!storedAccessToken) {
        return;
      }

      setAccessToken(storedAccessToken);
      void loadOverview(storedAccessToken);
    });
  }, [loadOverview]);

  const apiBaseUrlLabel = useMemo(() => {
    try {
      return getApiBaseUrl();
    } catch {
      return "잘못된 NEXT_PUBLIC_API_URL";
    }
  }, []);

  const project = projectResult?.state === "success" ? projectResult.project : null;
  const incidents = incidentResult?.state === "success" ? incidentResult.incidents : [];
  const alerts = alertResult?.state === "success" ? alertResult.alerts : [];
  const filteredAlerts = filterAlertsByStatus(alerts, alertStatusFilter);
  const alertStatusCounts = summarizeAlertStatuses(alerts);

  async function handleLoadMoreAlerts() {
    if (!trimmedToken || alertResult?.state !== "success") {
      return;
    }

    setIsLoadingMoreAlerts(true);
    setAlertListMessage(null);

    const nextResult = await fetchProjectAlerts({
      projectId,
      accessToken: trimmedToken,
      limit: LIST_LIMIT,
      offset: alertResult.alerts.length
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(trimmedToken);
    }

    if (nextResult.state !== "success") {
      setAlertListMessage(alertListMessageByState[nextResult.state]);
      setIsLoadingMoreAlerts(false);
      return;
    }

    setAlertResult((current) =>
      current?.state === "success"
        ? {
            state: "success",
            alerts: [...current.alerts, ...nextResult.alerts]
          }
        : nextResult
    );
    setHasMoreAlerts(nextResult.alerts.length === LIST_LIMIT);
    if (nextResult.alerts.length === 0) {
      setAlertListMessage("더 불러올 email alert가 없습니다.");
    }
    setIsLoadingMoreAlerts(false);
  }

  async function handleAlertSettingsSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSettingsSubmitMessage(null);

    if (!project || !trimmedToken) {
      setSettingsSubmitState("unauthorized");
      setSettingsSubmitMessage("로그인 세션 또는 Project 정보를 먼저 확인하세요.");
      return;
    }

    const recipientEmail = normalizeOptionalText(settingsForm.alertRecipientEmail);
    if (recipientEmail !== null && !isValidEmail(recipientEmail)) {
      setSettingsSubmitState("invalid");
      setSettingsSubmitMessage("Alert recipient email 형식을 확인하세요.");
      return;
    }

    setSettingsSubmitState("submitting");
    const result = await updateProject({
      projectId: project.id,
      accessToken: trimmedToken,
      payload: {
        name: project.name,
        service_url: project.service_url,
        description: project.description,
        environment: project.environment,
        scan_interval_minutes: project.scan_interval_minutes,
        response_time_threshold_ms: project.response_time_threshold_ms,
        quality_score_threshold: project.quality_score_threshold,
        alert_email_enabled: settingsForm.alertEmailEnabled,
        alert_recipient_email: recipientEmail
      }
    });

    if (result.state !== "success") {
      if (result.state === "unauthorized") {
        clearStoredAccessTokenIfMatches(trimmedToken);
      }

      setSettingsSubmitState(result.state);
      setSettingsSubmitMessage(alertSettingsSubmitMessage[result.state]);
      return;
    }

    setProjectResult({
      state: "success",
      project: result.project
    });
    setSettingsForm(formFromProjectAlertSettings(result.project));
    setSettingsSubmitState("success");
    setSettingsSubmitMessage("Email alert 설정을 저장했습니다. 이후 생성되는 alert부터 반영됩니다.");
  }

  async function handleRetryAlert(alert: Alert) {
    if (!trimmedToken) {
      setRetryFeedback({
        alertId: alert.id,
        state: "unauthorized",
        message: retryAlertFeedbackMessage.unauthorized
      });
      return;
    }

    setRetryingAlertId(alert.id);
    setRetryFeedback(null);

    const result = await retryAlert({
      projectId,
      alertId: alert.id,
      accessToken: trimmedToken
    });

    if (result.state === "success") {
      setAlertResult((current) =>
        current?.state === "success"
          ? {
              state: "success",
              alerts: current.alerts.map((currentAlert) =>
                currentAlert.id === result.alert.id ? result.alert : currentAlert
              )
            }
          : current
      );
      setRetryFeedback({
        alertId: alert.id,
        state: "success",
        message: "Alert 재시도 요청을 등록했습니다. 상태가 PENDING으로 변경되었습니다."
      });
      setRetryingAlertId(null);
      return;
    }

    if (result.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(trimmedToken);
    }

    setRetryFeedback({
      alertId: alert.id,
      state: result.state,
      message: retryAlertFeedbackMessage[result.state]
    });
    setRetryingAlertId(null);
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50">
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <header className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-cyan-300">
                AIM Alerts
              </p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
                Incident & Alert overview
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-300">
                이 화면은 <code className="text-cyan-200">{apiBaseUrlLabel}</code>에서
                프로젝트의 incident와 email alert 이력을 읽어옵니다. email alert 사용 여부와
                수신자 email도 이 화면에서 저장할 수 있습니다.
              </p>
            </div>
            <Link
              className="rounded-2xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100"
              href="/"
            >
              Dashboard
            </Link>
          </div>

          <Identifier label="Project ID" value={projectId} />

          <form
            className="mt-5 grid gap-3 md:grid-cols-[1fr_auto]"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              void refresh();
            }}
          >
            <label className="flex flex-col gap-2 text-sm">
              <span className="font-medium text-slate-200">Bearer token</span>
              <input
                className="rounded-2xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none ring-cyan-400/0 transition focus:border-cyan-300 focus:ring-4 focus:ring-cyan-400/10"
                onChange={(event) => setAccessToken(event.target.value)}
                placeholder="로그인 API에서 받은 access_token을 입력하세요"
                type="password"
                value={accessToken}
              />
            </label>
            <button
              className="self-end rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!trimmedToken || loadState === "loading"}
              type="submit"
            >
              {loadState === "loading" ? "조회 중" : "Alerts 조회"}
            </button>
          </form>
        </header>

        {!hasCheckedStoredToken && (
          <Notice
            description="저장된 로그인 세션이 있으면 자동으로 alert overview를 조회합니다."
            title="로그인 세션 확인 중"
            tone="info"
          />
        )}

        {hasCheckedStoredToken && !trimmedToken && (
          <Notice
            description="로그인 페이지에서 먼저 로그인하거나 access token을 직접 입력하세요."
            title="인증 토큰이 필요합니다"
            tone="info"
          />
        )}

        <ResultNotice alertResult={alertResult} incidentResult={incidentResult} projectResult={projectResult} />

        {project && (
          <ProjectAlertSettingsCard
            alertCount={alerts.length}
            form={settingsForm}
            incidentCount={incidents.length}
            lastUpdatedAt={lastUpdatedAt}
            onChange={setSettingsForm}
            onSubmit={handleAlertSettingsSubmit}
            project={project}
            submitMessage={settingsSubmitMessage}
            submitState={settingsSubmitState}
          />
        )}

        {incidentResult?.state === "success" && (
          <IncidentSection incidents={incidents} projectId={projectId} />
        )}

        {alertResult?.state === "success" && (
          <AlertSection
            alerts={filteredAlerts}
            filter={alertStatusFilter}
            hasMoreAlerts={hasMoreAlerts}
            isLoadingMoreAlerts={isLoadingMoreAlerts}
            listMessage={alertListMessage}
            onRetry={handleRetryAlert}
            onFilterChange={setAlertStatusFilter}
            onLoadMore={() => void handleLoadMoreAlerts()}
            projectId={projectId}
            retryFeedback={retryFeedback}
            retryingAlertId={retryingAlertId}
            statusCounts={alertStatusCounts}
            totalAlertCount={alerts.length}
          />
        )}
      </section>
    </main>
  );
}

function ProjectAlertSettingsCard({
  alertCount,
  form,
  incidentCount,
  lastUpdatedAt,
  onChange,
  onSubmit,
  project,
  submitMessage,
  submitState
}: {
  alertCount: number;
  form: AlertSettingsFormState;
  incidentCount: number;
  lastUpdatedAt: string | null;
  onChange: (form: AlertSettingsFormState) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  project: Project;
  submitMessage: string | null;
  submitState: AlertSettingsSubmitState;
}) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-300">
            기본 Alert 기준
          </p>
          <h2 className="mt-3 text-2xl font-bold text-slate-100">{project.name}</h2>
          <p className="mt-2 break-all text-sm text-cyan-100">{project.service_url}</p>
          <p className="mt-3 text-sm text-slate-400">
            마지막 조회: {lastUpdatedAt ?? "아직 없음"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge label={project.environment} />
          <Badge label={project.is_verified ? "verified" : "unverified"} />
        </div>
      </div>

      <dl className="mt-6 grid gap-4 md:grid-cols-4">
        <Metric label="Response threshold" value={`${project.response_time_threshold_ms}ms`} />
        <Metric label="Quality threshold" value={`${project.quality_score_threshold}`} />
        <Metric label="Incidents" value={`${incidentCount}개`} />
        <Metric label="Alerts" value={`${alertCount}개`} />
        <Metric
          label="Email alert"
          value={project.alert_email_enabled ? "enabled" : "disabled"}
        />
        <Metric
          label="Recipient"
          value={project.alert_recipient_email ?? "Project owner email fallback"}
        />
      </dl>

      <form
        className="mt-6 rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.04] p-5"
        onSubmit={onSubmit}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-100">Email alert 설정</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              비활성화하면 새 incident open/recovery 시 pending email alert를 만들지 않습니다.
              수신자를 비워두면 Project owner email을 사용합니다.
            </p>
          </div>
          <label className="flex items-center gap-3 rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-300">
            <input
              checked={form.alertEmailEnabled}
              className="h-4 w-4 accent-cyan-300"
              onChange={(event) =>
                onChange({
                  ...form,
                  alertEmailEnabled: event.target.checked
                })
              }
              type="checkbox"
            />
            Email alert 사용
          </label>
        </div>

        <label className="mt-5 block" htmlFor="alert-recipient-email">
          <span className="text-sm font-semibold text-slate-300">Recipient email</span>
          <input
            className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950 px-4 py-3 text-sm text-slate-100 outline-none ring-cyan-300/0 transition placeholder:text-slate-600 focus:border-cyan-300/60 focus:ring-4 focus:ring-cyan-300/10"
            id="alert-recipient-email"
            maxLength={320}
            onChange={(event) =>
              onChange({
                ...form,
                alertRecipientEmail: event.target.value
              })
            }
            placeholder="alerts@example.com"
            type="email"
            value={form.alertRecipientEmail}
          />
        </label>

        <button
          className="mt-5 rounded-2xl bg-cyan-300 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={submitState === "submitting"}
          type="submit"
        >
          {submitState === "submitting" ? "저장 중" : "Alert 설정 저장"}
        </button>

        {submitMessage && (
          <p
            className={`mt-4 rounded-2xl border p-4 text-sm leading-6 ${
              submitState === "success"
                ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"
                : "border-rose-400/20 bg-rose-400/10 text-rose-100"
            }`}
          >
            {submitMessage}
          </p>
        )}
      </form>
    </section>
  );
}

function IncidentSection({ incidents, projectId }: { incidents: Incident[]; projectId: string }) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <SectionHeader count={incidents.length} title="Incidents" />
      {incidents.length === 0 ? (
        <EmptyState description="아직 이 프로젝트에서 기록된 incident가 없습니다." />
      ) : (
        <ul className="grid gap-4">
          {incidents.map((incident) => (
            <IncidentCard incident={incident} key={incident.id} projectId={projectId} />
          ))}
        </ul>
      )}
    </section>
  );
}

function IncidentCard({ incident, projectId }: { incident: Incident; projectId: string }) {
  return (
    <li className="rounded-2xl border border-white/10 bg-slate-950/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={incident.status} />
            <SeverityBadge severity={incident.severity} />
            <Badge label={formatTriggerType(incident.trigger_type)} />
          </div>
          <h3 className="mt-4 text-lg font-bold text-slate-100">{incident.title}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-300">{incident.summary}</p>
        </div>
        <Link
          className="rounded-2xl bg-slate-100 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-200"
          href={`/projects/${projectId}/check-runs/${incident.opened_check_run_id}`}
        >
          시작 run 보기
        </Link>
      </div>

      <dl className="mt-5 grid gap-3 md:grid-cols-3">
        <Metric label="Started" value={formatDateTime(incident.started_at)} />
        <Metric label="Resolved" value={formatNullableDateTime(incident.resolved_at)} />
        <Metric label="Incident ID" value={incident.id} />
      </dl>

      <pre className="mt-4 overflow-x-auto rounded-2xl border border-white/10 bg-slate-900 p-4 text-xs leading-5 text-slate-300">
        {JSON.stringify(incident.evidence_json, null, 2)}
      </pre>
    </li>
  );
}

function AlertSection({
  alerts,
  filter,
  hasMoreAlerts,
  isLoadingMoreAlerts,
  listMessage,
  onRetry,
  onFilterChange,
  onLoadMore,
  projectId,
  retryFeedback,
  retryingAlertId,
  statusCounts,
  totalAlertCount
}: {
  alerts: Alert[];
  filter: AlertStatusFilter;
  hasMoreAlerts: boolean;
  isLoadingMoreAlerts: boolean;
  listMessage: string | null;
  onRetry: (alert: Alert) => void;
  onFilterChange: (filter: AlertStatusFilter) => void;
  onLoadMore: () => void;
  projectId: string;
  retryFeedback: RetryAlertFeedback | null;
  retryingAlertId: string | null;
  statusCounts: AlertStatusCounts;
  totalAlertCount: number;
}) {
  return (
    <section className="rounded-3xl border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-100">Email alerts</h2>
          <p className="mt-2 text-sm text-slate-400">
            로드된 alert {totalAlertCount}개 중 {alerts.length}개를 표시합니다.
          </p>
        </div>
        <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-300 ring-1 ring-cyan-400/20">
          {alerts.length}개
        </span>
      </div>

      <AlertFilterBar
        currentFilter={filter}
        onChange={onFilterChange}
        statusCounts={statusCounts}
      />

      {totalAlertCount === 0 ? (
        <EmptyState description="아직 이 프로젝트에서 생성된 alert가 없습니다." />
      ) : alerts.length === 0 ? (
        <EmptyState description="현재 선택한 상태에 해당하는 loaded alert가 없습니다." />
      ) : (
        <ul className="mt-5 grid gap-4">
          {alerts.map((alert) => (
            <AlertCard
              alert={alert}
              key={alert.id}
              onRetry={onRetry}
              projectId={projectId}
              retryFeedback={retryFeedback?.alertId === alert.id ? retryFeedback : null}
              retrying={retryingAlertId === alert.id}
            />
          ))}
        </ul>
      )}

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <button
          className="rounded-2xl border border-cyan-300/30 px-4 py-2 text-sm font-bold text-cyan-100 transition hover:border-cyan-200 hover:bg-cyan-300/10 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!hasMoreAlerts || isLoadingMoreAlerts}
          onClick={onLoadMore}
          type="button"
        >
          {isLoadingMoreAlerts ? "더 불러오는 중" : "Alert 더 보기"}
        </button>
        <p className="text-sm text-slate-400">
          {hasMoreAlerts
            ? `${LIST_LIMIT}개 단위로 더 불러옵니다.`
            : "현재 로드된 목록이 마지막 page입니다."}
        </p>
      </div>

      {listMessage && (
        <p className="mt-4 rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-4 text-sm text-cyan-100">
          {listMessage}
        </p>
      )}
    </section>
  );
}

function AlertFilterBar({
  currentFilter,
  onChange,
  statusCounts
}: {
  currentFilter: AlertStatusFilter;
  onChange: (filter: AlertStatusFilter) => void;
  statusCounts: AlertStatusCounts;
}) {
  const filters: Array<{ label: string; value: AlertStatusFilter; count: number }> = [
    {
      label: "전체",
      value: "ALL",
      count: statusCounts.ALL
    },
    {
      label: "대기",
      value: "PENDING",
      count: statusCounts.PENDING
    },
    {
      label: "발송됨",
      value: "SENT",
      count: statusCounts.SENT
    },
    {
      label: "실패",
      value: "FAILED",
      count: statusCounts.FAILED
    }
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {filters.map((filter) => {
        const isSelected = currentFilter === filter.value;
        return (
          <button
            className={`rounded-2xl px-4 py-2 text-sm font-bold transition ${
              isSelected
                ? "bg-cyan-300 text-slate-950"
                : "border border-white/10 text-slate-300 hover:border-cyan-300/50 hover:text-cyan-100"
            }`}
            key={filter.value}
            onClick={() => onChange(filter.value)}
            type="button"
          >
            {filter.label} {filter.count}
          </button>
        );
      })}
    </div>
  );
}

function AlertCard({
  alert,
  onRetry,
  projectId,
  retryFeedback,
  retrying
}: {
  alert: Alert;
  onRetry: (alert: Alert) => void;
  projectId: string;
  retryFeedback: RetryAlertFeedback | null;
  retrying: boolean;
}) {
  const canRetry = alert.status === "FAILED";

  return (
    <li className="rounded-2xl border border-white/10 bg-slate-950/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap gap-2">
            <AlertStatusBadge status={alert.status} />
            <Badge label={alert.channel} />
            <Badge label={formatAlertType(alert.alert_type)} />
          </div>
          <h3 className="mt-4 text-lg font-bold text-slate-100">{alert.subject}</h3>
          <p className="mt-2 text-sm text-slate-400">
            수신자: {alert.recipient_email ?? "미설정"} · 시도 횟수: {alert.delivery_attempts}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canRetry && (
            <button
              className="rounded-2xl bg-cyan-300 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={retrying}
              onClick={() => onRetry(alert)}
              type="button"
            >
              {retrying ? "재시도 요청 중" : "발송 재시도"}
            </button>
          )}
          {alert.check_run_id && (
            <Link
              className="rounded-2xl bg-slate-100 px-4 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-200"
              href={`/projects/${projectId}/check-runs/${alert.check_run_id}`}
            >
              관련 run 보기
            </Link>
          )}
        </div>
      </div>

      <dl className="mt-5 grid gap-3 md:grid-cols-3">
        <Metric label="Created" value={formatDateTime(alert.created_at)} />
        <Metric label="Sent" value={formatNullableDateTime(alert.sent_at)} />
        <Metric label="Trigger" value={formatTriggerType(alert.trigger_type)} />
      </dl>

      {alert.last_error && (
        <p className="mt-4 rounded-2xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-100">
          {alert.last_error}
        </p>
      )}

      {retryFeedback && (
        <p
          className={`mt-4 rounded-2xl border p-4 text-sm leading-6 ${
            retryFeedback.state === "success"
              ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-100"
              : "border-rose-400/20 bg-rose-400/10 text-rose-100"
          }`}
        >
          {retryFeedback.message}
        </p>
      )}
    </li>
  );
}

function ResultNotice({
  alertResult,
  incidentResult,
  projectResult
}: {
  alertResult: AlertListResult | null;
  incidentResult: IncidentListResult | null;
  projectResult: ProjectDetailResult | null;
}) {
  const firstProblem = [projectResult, incidentResult, alertResult].find(
    (result) => result !== null && result.state !== "success"
  );

  if (!firstProblem) {
    return null;
  }

  if (firstProblem.state === "unauthorized") {
    return (
      <Notice
        description="토큰이 없거나 만료되었거나, 이 프로젝트에 접근할 권한이 없습니다."
        title="인증 실패"
        tone="danger"
      />
    );
  }

  if (firstProblem.state === "not-found") {
    return (
      <Notice
        description="Project ID 또는 현재 사용자 권한을 확인하세요."
        title="프로젝트를 찾을 수 없습니다"
        tone="danger"
      />
    );
  }

  return (
    <Notice
      description="API 서버 실행 상태와 NEXT_PUBLIC_API_URL 설정을 확인하세요."
      title="Alert overview 요청 실패"
      tone="danger"
    />
  );
}

function SectionHeader({ count, title }: { count: number; title: string }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-xl font-semibold text-slate-100">{title}</h2>
      <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-300 ring-1 ring-cyan-400/20">
        {count}개
      </span>
    </div>
  );
}

function Identifier({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-5 rounded-2xl border border-white/10 bg-slate-900/60 p-4 text-sm text-slate-300">
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
  description,
  title,
  tone
}: {
  description: string;
  title: string;
  tone: "info" | "danger";
}) {
  const className =
    tone === "info"
      ? "border-cyan-400/20 bg-cyan-400/10 text-cyan-100"
      : "border-rose-400/20 bg-rose-400/10 text-rose-100";

  return (
    <article className={`rounded-3xl border p-6 ${className}`}>
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-2 text-sm leading-6 opacity-80">{description}</p>
    </article>
  );
}

function EmptyState({ description }: { description: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/10 bg-white/[0.02] p-5 text-sm text-slate-400">
      {description}
    </div>
  );
}

function Badge({ label }: { label: string }) {
  return (
    <span className="rounded-full bg-slate-700/80 px-3 py-1 text-xs font-bold text-slate-200 ring-1 ring-white/10">
      {label}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const className =
    status === "OPEN"
      ? "bg-rose-400/10 text-rose-300 ring-rose-400/20"
      : "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${className}`}>
      {status}
    </span>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const className =
    severity === "RISK"
      ? "bg-rose-400/10 text-rose-300 ring-rose-400/20"
      : "bg-amber-400/10 text-amber-300 ring-amber-400/20";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${className}`}>
      {severity}
    </span>
  );
}

function AlertStatusBadge({ status }: { status: string }) {
  const className =
    status === "SENT"
      ? "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20"
      : status === "FAILED"
        ? "bg-rose-400/10 text-rose-300 ring-rose-400/20"
        : "bg-cyan-400/10 text-cyan-300 ring-cyan-400/20";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${className}`}>
      {status}
    </span>
  );
}

function formatTriggerType(value: string): string {
  return value.toLowerCase().replaceAll("_", " ");
}

function formatAlertType(value: string): string {
  return value.toLowerCase().replaceAll("_", " ");
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function formatNullableDateTime(value: string | null): string {
  return value ? formatDateTime(value) : "아직 없음";
}

function formFromProjectAlertSettings(project: Project): AlertSettingsFormState {
  return {
    alertEmailEnabled: project.alert_email_enabled,
    alertRecipientEmail: project.alert_recipient_email ?? ""
  };
}

function normalizeOptionalText(value: string): string | null {
  const normalized = value.trim().toLowerCase();
  return normalized ? normalized : null;
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function filterAlertsByStatus(alerts: Alert[], filter: AlertStatusFilter): Alert[] {
  if (filter === "ALL") {
    return alerts;
  }

  return alerts.filter((alert) => alert.status === filter);
}

function summarizeAlertStatuses(alerts: Alert[]): AlertStatusCounts {
  return alerts.reduce<AlertStatusCounts>(
    (summary, alert) => {
      summary.ALL += 1;

      if (alert.status === "PENDING") {
        summary.PENDING += 1;
      }

      if (alert.status === "SENT") {
        summary.SENT += 1;
      }

      if (alert.status === "FAILED") {
        summary.FAILED += 1;
      }

      return summary;
    },
    {
      ALL: 0,
      PENDING: 0,
      SENT: 0,
      FAILED: 0
    }
  );
}

const alertSettingsSubmitMessage: Record<
  Exclude<AlertSettingsSubmitState, "idle" | "submitting" | "success">,
  string
> = {
  invalid: "입력값을 확인하세요. Recipient email은 비워두거나 올바른 이메일 형식이어야 합니다.",
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "Project를 찾을 수 없습니다. Dashboard에서 다시 선택하세요.",
  unavailable: "Alert 설정 저장 요청에 실패했습니다. API 서버 상태를 확인하세요."
};

const retryAlertFeedbackMessage: Record<
  Exclude<RetryAlertResult["state"], "success">,
  string
> = {
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "Project 또는 Alert를 찾을 수 없습니다. 목록을 다시 조회하세요.",
  conflict: "FAILED 상태의 email alert만 재시도할 수 있습니다.",
  unavailable: "Alert 재시도 요청에 실패했습니다. API 서버 또는 worker queue 상태를 확인하세요."
};

const alertListMessageByState: Record<
  Exclude<AlertListResult["state"], "success">,
  string
> = {
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "Project를 찾을 수 없습니다. Dashboard에서 다시 선택하세요.",
  unavailable: "Alert 목록을 더 불러오지 못했습니다. API 서버 상태를 확인하세요."
};
