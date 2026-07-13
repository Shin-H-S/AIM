"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  fetchProject,
  fetchProjectAlerts,
  fetchProjectIncidents,
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
import { formatDateTime, formatNullableDateTime } from "@/lib/format";
import {
  alertChannelLabel,
  alertStatusLabel,
  alertTypeLabel,
  enabledLabel,
  environmentLabel,
  incidentStatusLabel,
  incidentTriggerLabel,
  severityLabel,
  verifiedLabel
} from "@/lib/statusLabels";
import {
  Badge,
  EmptyState,
  LinkButton,
  LoginRequiredNotice,
  Metric,
  Notice,
  RefreshButton
} from "@/components/ui";

const LIST_LIMIT = 20;

type SessionState = "checking" | "signed-out" | "ready";
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
  alertWebhookUrl: string;
};

type RetryAlertFeedback = {
  alertId: string;
  state: Exclude<RetryAlertResult["state"], "success"> | "success";
  message: string;
};

type AlertStatusCounts = Record<AlertStatusFilter, number>;

export function AlertOverviewPageClient({ projectId }: { projectId: string }) {
  const [sessionState, setSessionState] = useState<SessionState>("checking");
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [projectResult, setProjectResult] = useState<ProjectDetailResult | null>(null);
  const [incidentResult, setIncidentResult] = useState<IncidentListResult | null>(null);
  const [alertResult, setAlertResult] = useState<AlertListResult | null>(null);
  const [settingsForm, setSettingsForm] = useState<AlertSettingsFormState>({
    alertEmailEnabled: false,
    alertRecipientEmail: "",
    alertWebhookUrl: ""
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
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    const accessToken = getStoredAccessToken();

    if (!accessToken) {
      setSessionState("signed-out");
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

    setSessionState("ready");
    setLoadState("loading");
    setAlertListMessage(null);
    const [nextProjectResult, nextIncidentResult, nextAlertResult] = await Promise.all([
      fetchProject({
        projectId,
        accessToken
      }),
      fetchProjectIncidents({
        projectId,
        accessToken,
        limit: LIST_LIMIT
      }),
      fetchProjectAlerts({
        projectId,
        accessToken,
        limit: LIST_LIMIT
      })
    ]);

    if (
      nextProjectResult.state === "unauthorized" ||
      nextIncidentResult.state === "unauthorized" ||
      nextAlertResult.state === "unauthorized"
    ) {
      clearStoredAccessTokenIfMatches(accessToken);
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
  }, [projectId]);

  useEffect(() => {
    queueMicrotask(() => {
      void loadOverview();
    });
  }, [loadOverview]);

  const project = projectResult?.state === "success" ? projectResult.project : null;
  const incidents = incidentResult?.state === "success" ? incidentResult.incidents : [];
  const alerts = alertResult?.state === "success" ? alertResult.alerts : [];
  const filteredAlerts = filterAlertsByStatus(alerts, alertStatusFilter);
  const alertStatusCounts = summarizeAlertStatuses(alerts);

  async function handleLoadMoreAlerts() {
    const accessToken = getStoredAccessToken();

    if (!accessToken || alertResult?.state !== "success") {
      return;
    }

    setIsLoadingMoreAlerts(true);
    setAlertListMessage(null);

    const nextResult = await fetchProjectAlerts({
      projectId,
      accessToken,
      limit: LIST_LIMIT,
      offset: alertResult.alerts.length
    });

    if (nextResult.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
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

    const accessToken = getStoredAccessToken();

    if (!project || !accessToken) {
      setSettingsSubmitState("unauthorized");
      setSettingsSubmitMessage("로그인 세션 또는 Project 정보를 먼저 확인하세요.");
      return;
    }

    const recipientEmail = normalizeOptionalText(settingsForm.alertRecipientEmail);
    if (recipientEmail !== null && !isValidEmail(recipientEmail)) {
      setSettingsSubmitState("invalid");
      setSettingsSubmitMessage("수신자 이메일 형식을 확인하세요.");
      return;
    }

    const webhookUrl = normalizeOptionalUrl(settingsForm.alertWebhookUrl);
    if (webhookUrl !== null && !isValidWebhookUrl(webhookUrl)) {
      setSettingsSubmitState("invalid");
      setSettingsSubmitMessage("Webhook URL은 http(s)://로 시작하는 주소여야 합니다.");
      return;
    }

    setSettingsSubmitState("submitting");
    const result = await updateProject({
      projectId: project.id,
      accessToken,
      payload: {
        name: project.name,
        service_url: project.service_url,
        description: project.description,
        environment: project.environment,
        scan_interval_minutes: project.scan_interval_minutes,
        response_time_threshold_ms: project.response_time_threshold_ms,
        quality_score_threshold: project.quality_score_threshold,
        alert_email_enabled: settingsForm.alertEmailEnabled,
        alert_recipient_email: recipientEmail,
        alert_webhook_url: webhookUrl
      }
    });

    if (result.state !== "success") {
      if (result.state === "unauthorized") {
        clearStoredAccessTokenIfMatches(accessToken);
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
    setSettingsSubmitMessage("알림 채널 설정을 저장했습니다. 이후 생성되는 알림부터 반영됩니다.");
  }

  async function handleRetryAlert(alert: Alert) {
    const accessToken = getStoredAccessToken();

    if (!accessToken) {
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
      accessToken
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
        message: "알림 재시도 요청을 등록했습니다. 상태가 대기로 변경되었습니다."
      });
      setRetryingAlertId(null);
      return;
    }

    if (result.state === "unauthorized") {
      clearStoredAccessTokenIfMatches(accessToken);
    }

    setRetryFeedback({
      alertId: alert.id,
      state: result.state,
      message: retryAlertFeedbackMessage[result.state]
    });
    setRetryingAlertId(null);
  }

  return (
    <main>
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-6 py-12">
        <header className="rounded-3xl border border-slate-200 bg-white p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-cyan-700">
                AIM 알림
              </p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
                장애·알림 현황
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-600">
                프로젝트의 장애와 알림 이력을 확인하고, 알림 채널을 설정합니다.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <LinkButton href={`/projects/${projectId}/settings`} label="프로젝트 설정" />
              <RefreshButton
                isLoading={loadState === "loading"}
                onClick={() => void loadOverview()}
              />
            </div>
          </div>
        </header>

        {sessionState === "checking" && (
          <Notice
            description="저장된 로그인 세션이 있으면 자동으로 알림 현황을 조회합니다."
            title="로그인 세션 확인 중"
            tone="info"
          />
        )}

        {sessionState === "signed-out" && <LoginRequiredNotice />}

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
    <section className="rounded-3xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-700">
            기본 알림 기준
          </p>
          <h2 className="mt-3 text-2xl font-bold text-slate-900">{project.name}</h2>
          <p className="mt-2 break-all text-sm text-cyan-700">{project.service_url}</p>
          <p className="mt-3 text-sm text-slate-500">
            마지막 조회: {lastUpdatedAt ?? "아직 없음"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge label={environmentLabel(project.environment)} />
          <Badge label={verifiedLabel(project.is_verified)} />
        </div>
      </div>

      <dl className="mt-6 grid gap-4 md:grid-cols-4">
        <Metric label="응답 임계값" value={`${project.response_time_threshold_ms}ms`} />
        <Metric label="품질 임계값" value={`${project.quality_score_threshold}`} />
        <Metric label="장애" value={`${incidentCount}개`} />
        <Metric label="알림" value={`${alertCount}개`} />
        <Metric
          label="이메일 알림"
          value={enabledLabel(project.alert_email_enabled)}
        />
        <Metric
          label="수신자"
          value={project.alert_recipient_email ?? "미설정 시 소유자 이메일"}
        />
        <Metric
          label="Webhook 알림"
          value={enabledLabel(Boolean(project.alert_webhook_url))}
        />
      </dl>

      <form
        className="mt-6 rounded-2xl border border-cyan-200 bg-cyan-50/60 p-5"
        onSubmit={onSubmit}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900">알림 채널 설정</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
              장애 발생/복구 시 활성화된 채널로 알림을 발송합니다. 이메일은 체크한 경우에만,
              Webhook은 URL을 등록한 경우에만 사용합니다. 수신자를 비워두면 프로젝트 소유자
              이메일을 사용합니다.
            </p>
          </div>
          <label className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
            <input
              checked={form.alertEmailEnabled}
              className="h-4 w-4 accent-cyan-600"
              onChange={(event) =>
                onChange({
                  ...form,
                  alertEmailEnabled: event.target.checked
                })
              }
              type="checkbox"
            />
            이메일 알림 사용
          </label>
        </div>

        <label className="mt-5 block" htmlFor="alert-recipient-email">
          <span className="text-sm font-semibold text-slate-600">수신자 이메일</span>
          <input
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-cyan-300/0 transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
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

        <label className="mt-5 block" htmlFor="alert-webhook-url">
          <span className="text-sm font-semibold text-slate-600">
            Webhook URL (Slack/Discord)
          </span>
          <input
            className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none ring-cyan-300/0 transition placeholder:text-slate-400 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
            id="alert-webhook-url"
            maxLength={1024}
            onChange={(event) =>
              onChange({
                ...form,
                alertWebhookUrl: event.target.value
              })
            }
            placeholder="https://hooks.slack.com/services/..."
            type="url"
            value={form.alertWebhookUrl}
          />
          <span className="mt-2 block text-xs leading-5 text-slate-500">
            Slack 또는 Discord의 incoming webhook URL을 붙여넣으세요. 비워두면 Webhook
            알림을 보내지 않습니다.
          </span>
        </label>

        <button
          className="mt-5 rounded-2xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white transition hover:bg-cyan-600 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={submitState === "submitting"}
          type="submit"
        >
          {submitState === "submitting" ? "저장 중" : "알림 설정 저장"}
        </button>

        {submitMessage && (
          <p
            className={`mt-4 rounded-2xl border p-4 text-sm leading-6 ${
              submitState === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-rose-200 bg-rose-50 text-rose-800"
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
    <section className="rounded-3xl border border-slate-200 bg-white p-6">
      <SectionHeader count={incidents.length} title="장애" />
      {incidents.length === 0 ? (
        <EmptyState description="아직 이 프로젝트에서 기록된 장애가 없습니다." />
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
    <li className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap gap-2">
            <IncidentStatusBadge status={incident.status} />
            <SeverityBadge severity={incident.severity} />
            <Badge label={incidentTriggerLabel(incident.trigger_type)} />
          </div>
          <h3 className="mt-4 text-lg font-bold text-slate-900">{incident.title}</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">{incident.summary}</p>
        </div>
        <LinkButton
          href={`/projects/${projectId}/check-runs/${incident.opened_check_run_id}`}
          label="발생 검사 보기"
          variant="dark"
        />
      </div>

      <dl className="mt-5 grid gap-3 md:grid-cols-2">
        <Metric label="시작 시각" value={formatDateTime(incident.started_at)} />
        <Metric label="해소 시각" value={formatNullableDateTime(incident.resolved_at)} />
      </dl>
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
    <section className="rounded-3xl border border-slate-200 bg-white p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900">알림 목록</h2>
          <p className="mt-2 text-sm text-slate-500">
            로드된 알림 {totalAlertCount}개 중 {alerts.length}개를 표시합니다.
          </p>
        </div>
        <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
          {alerts.length}개
        </span>
      </div>

      <AlertFilterBar
        currentFilter={filter}
        onChange={onFilterChange}
        statusCounts={statusCounts}
      />

      {totalAlertCount === 0 ? (
        <EmptyState description="아직 이 프로젝트에서 생성된 알림이 없습니다." />
      ) : alerts.length === 0 ? (
        <EmptyState description="현재 선택한 상태에 해당하는 알림이 없습니다." />
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
          className="rounded-2xl border border-cyan-300 px-4 py-2 text-sm font-bold text-cyan-700 transition hover:border-cyan-500 hover:bg-cyan-50 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!hasMoreAlerts || isLoadingMoreAlerts}
          onClick={onLoadMore}
          type="button"
        >
          {isLoadingMoreAlerts ? "더 불러오는 중" : "알림 더 보기"}
        </button>
        <p className="text-sm text-slate-500">
          {hasMoreAlerts
            ? `${LIST_LIMIT}개 단위로 더 불러옵니다.`
            : "현재 로드된 목록이 마지막 페이지입니다."}
        </p>
      </div>

      {listMessage && (
        <p className="mt-4 rounded-2xl border border-cyan-200 bg-cyan-50 p-4 text-sm text-cyan-700">
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
                ? "bg-cyan-700 text-white"
                : "border border-slate-200 text-slate-600 hover:border-cyan-400 hover:text-cyan-700"
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
    <li className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap gap-2">
            <AlertStatusBadge status={alert.status} />
            <Badge label={alertChannelLabel(alert.channel)} />
            <Badge label={alertTypeLabel(alert.alert_type)} />
          </div>
          <h3 className="mt-4 text-lg font-bold text-slate-900">{alert.subject}</h3>
          <p className="mt-2 text-sm text-slate-500">
            수신자: {alert.channel === "WEBHOOK" ? "Webhook" : (alert.recipient_email ?? "미설정")}{" "}
            · 시도 횟수: {alert.delivery_attempts}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canRetry && (
            <button
              className="rounded-2xl bg-cyan-700 px-4 py-2 text-sm font-bold text-white transition hover:bg-cyan-600 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={retrying}
              onClick={() => onRetry(alert)}
              type="button"
            >
              {retrying ? "재시도 요청 중" : "발송 재시도"}
            </button>
          )}
          {alert.check_run_id && (
            <LinkButton
              href={`/projects/${projectId}/check-runs/${alert.check_run_id}`}
              label="관련 검사 보기"
              variant="dark"
            />
          )}
        </div>
      </div>

      <dl className="mt-5 grid gap-3 md:grid-cols-3">
        <Metric label="생성 시각" value={formatDateTime(alert.created_at)} />
        <Metric label="발송 시각" value={formatNullableDateTime(alert.sent_at)} />
        <Metric label="트리거" value={incidentTriggerLabel(alert.trigger_type)} />
      </dl>

      {alert.last_error && (
        <p className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
          {alert.last_error}
        </p>
      )}

      {retryFeedback && (
        <p
          className={`mt-4 rounded-2xl border p-4 text-sm leading-6 ${
            retryFeedback.state === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-rose-200 bg-rose-50 text-rose-800"
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
    return <LoginRequiredNotice expired />;
  }

  if (firstProblem.state === "not-found") {
    return (
      <Notice
        description="프로젝트 ID 또는 현재 사용자 권한을 확인하세요."
        title="프로젝트를 찾을 수 없습니다"
        tone="danger"
      />
    );
  }

  return (
    <Notice
      description="서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
      title="알림 현황 요청 실패"
      tone="danger"
    />
  );
}

function SectionHeader({ count, title }: { count: number; title: string }) {
  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <h2 className="text-xl font-semibold text-slate-900">{title}</h2>
      <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-700 ring-1 ring-cyan-200">
        {count}개
      </span>
    </div>
  );
}

function IncidentStatusBadge({ status }: { status: string }) {
  const className =
    status === "OPEN"
      ? "bg-rose-50 text-rose-700 ring-rose-200"
      : "bg-emerald-50 text-emerald-700 ring-emerald-200";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${className}`}>
      {incidentStatusLabel(status)}
    </span>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const className =
    severity === "RISK"
      ? "bg-rose-50 text-rose-700 ring-rose-200"
      : "bg-amber-50 text-amber-700 ring-amber-200";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${className}`}>
      {severityLabel(severity)}
    </span>
  );
}

function AlertStatusBadge({ status }: { status: string }) {
  const className =
    status === "SENT"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
      : status === "FAILED"
        ? "bg-rose-50 text-rose-700 ring-rose-200"
        : "bg-cyan-50 text-cyan-700 ring-cyan-200";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${className}`}>
      {alertStatusLabel(status)}
    </span>
  );
}

function formFromProjectAlertSettings(project: Project): AlertSettingsFormState {
  return {
    alertEmailEnabled: project.alert_email_enabled,
    alertRecipientEmail: project.alert_recipient_email ?? "",
    alertWebhookUrl: project.alert_webhook_url ?? ""
  };
}

function normalizeOptionalUrl(value: string): string | null {
  const normalized = value.trim();
  return normalized ? normalized : null;
}

function isValidWebhookUrl(value: string): boolean {
  return /^https?:\/\/\S+$/.test(value);
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
  invalid: "입력값을 확인하세요. 수신자 이메일은 비워두거나 올바른 이메일 형식이어야 합니다.",
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "프로젝트를 찾을 수 없습니다. 대시보드에서 다시 선택하세요.",
  unavailable: "알림 설정 저장에 실패했습니다. 잠시 후 다시 시도하세요."
};

const retryAlertFeedbackMessage: Record<
  Exclude<RetryAlertResult["state"], "success">,
  string
> = {
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "프로젝트 또는 알림을 찾을 수 없습니다. 목록을 다시 조회하세요.",
  conflict: "실패 상태의 알림만 재시도할 수 있습니다.",
  unavailable: "알림 재시도 요청에 실패했습니다. 잠시 후 다시 시도하세요."
};

const alertListMessageByState: Record<
  Exclude<AlertListResult["state"], "success">,
  string
> = {
  unauthorized: "로그인 세션이 만료되었습니다. 다시 로그인한 뒤 시도하세요.",
  "not-found": "프로젝트를 찾을 수 없습니다. 대시보드에서 다시 선택하세요.",
  unavailable: "알림 목록을 더 불러오지 못했습니다. 잠시 후 다시 시도하세요."
};
