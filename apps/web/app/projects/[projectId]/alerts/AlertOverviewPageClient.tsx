"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  clearAgentInvestigationFeedback,
  fetchAgentInvestigation,
  fetchProject,
  fetchProjectAlerts,
  fetchProjectIncidents,
  retryAlert,
  submitAgentInvestigationFeedback,
  updateProject,
  type AgentInvestigation,
  type Alert,
  type AlertListResult,
  type Incident,
  type IncidentListResult,
  type Project,
  type ProjectDetailResult,
  type RetryAlertResult
} from "@/lib/api";
import { hasSession, notifySessionChanged } from "@/lib/auth";
import { formatDateTime, formatNullableDateTime } from "@/lib/format";
import {
  alertChannelLabel,
  alertStatusLabel,
  alertTypeLabel,
  enabledLabel,
  environmentLabel,
  incidentStatusLabel,
  incidentTriggerLabel,
  rootCauseLabel,
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
// 타임라인에 조사를 붙일 인시던트 수 — 그 아래는 발생 검사 링크로 충분하다.
const INVESTIGATION_LOOKUP_LIMIT = 10;

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
  // 인시던트 id → 조사 결과. null = 조사 없음(쿨다운·규칙 미적용 등), 미기재 = 미조회.
  const [investigationsByIncident, setInvestigationsByIncident] = useState<
    Record<string, AgentInvestigation | null>
  >({});
  const [feedbackBusyIncidentId, setFeedbackBusyIncidentId] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    if (!hasSession()) {
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
      }),
      fetchProjectIncidents({
        projectId,
        limit: LIST_LIMIT
      }),
      fetchProjectAlerts({
        projectId,
        limit: LIST_LIMIT
      })
    ]);

    if (
      nextProjectResult.state === "unauthorized" ||
      nextIncidentResult.state === "unauthorized" ||
      nextAlertResult.state === "unauthorized"
    ) {
      notifySessionChanged();
    }

    setProjectResult(nextProjectResult);
    setIncidentResult(nextIncidentResult);
    // 타임라인의 조사 단계: 상위 인시던트들의 조사를 병렬로 붙인다.
    if (nextIncidentResult.state === "success") {
      const lookups = await Promise.all(
        nextIncidentResult.incidents.slice(0, INVESTIGATION_LOOKUP_LIMIT).map(async (incident) => {
          const result = await fetchAgentInvestigation({
            projectId,
            checkRunId: incident.opened_check_run_id
          });
          return [incident.id, result.state === "success" ? result.investigation : null] as const;
        })
      );
      setInvestigationsByIncident(Object.fromEntries(lookups));
    } else {
      setInvestigationsByIncident({});
    }
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

  async function handleIncidentFeedback(
    incident: Incident,
    verdict: "accurate" | null
  ) {
    setFeedbackBusyIncidentId(incident.id);
    const result =
      verdict === null
        ? await clearAgentInvestigationFeedback({
            projectId,
            checkRunId: incident.opened_check_run_id
          })
        : await submitAgentInvestigationFeedback({
            projectId,
            checkRunId: incident.opened_check_run_id,
            verdict
          });
    if (result.state === "unauthorized") {
      notifySessionChanged();
    }
    if (result.state === "success") {
      setInvestigationsByIncident((current) => ({
        ...current,
        [incident.id]: result.investigation
      }));
    }
    setFeedbackBusyIncidentId(null);
  }

  async function handleLoadMoreAlerts() {
    if (!hasSession() || alertResult?.state !== "success") {
      return;
    }

    setIsLoadingMoreAlerts(true);
    setAlertListMessage(null);

    const nextResult = await fetchProjectAlerts({
      projectId,
      limit: LIST_LIMIT,
      offset: alertResult.alerts.length
    });

    if (nextResult.state === "unauthorized") {
      notifySessionChanged();
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

    if (!project || !hasSession()) {
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
      payload: {
        name: project.name,
        service_url: project.service_url,
        // Read 스키마가 Create의 default를 물려받아 optional로 생성된다 —
        // 응답에는 항상 실려 오므로 여기서 null로 정규화한다.
        description: project.description ?? null,
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
        notifySessionChanged();
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
    if (!hasSession()) {
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
      notifySessionChanged();
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
        <header className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.28em] text-cyan-700 dark:text-cyan-400">
                AIM 알림
              </p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-5xl">
                장애·알림 현황
              </h1>
              <p className="mt-4 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
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
          <IncidentSection
            feedbackBusyIncidentId={feedbackBusyIncidentId}
            incidents={incidents}
            investigationsByIncident={investigationsByIncident}
            onFeedback={(incident, verdict) => void handleIncidentFeedback(incident, verdict)}
            projectId={projectId}
          />
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
    <section className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-cyan-700 dark:text-cyan-400">
            기본 알림 기준
          </p>
          <h2 className="mt-3 text-2xl font-bold text-slate-900 dark:text-white">{project.name}</h2>
          <p className="mt-2 break-all text-sm text-cyan-700 dark:text-cyan-400">{project.service_url}</p>
          <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
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
        className="mt-6 rounded-2xl border border-cyan-200 dark:border-cyan-900 bg-cyan-50/60 dark:bg-cyan-950/40 p-5"
        onSubmit={onSubmit}
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h3 className="text-lg font-bold text-slate-900 dark:text-white">알림 채널 설정</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">
              장애 발생/복구 시 활성화된 채널로 알림을 발송합니다. 이메일은 체크한 경우에만,
              Webhook은 URL을 등록한 경우에만 사용합니다. 수신자를 비워두면 프로젝트 소유자
              이메일을 사용합니다.
            </p>
          </div>
          <label className="flex items-center gap-3 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 text-sm text-slate-600 dark:text-slate-300">
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
          <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">수신자 이메일</span>
          <input
            className="mt-2 w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 text-sm text-slate-900 dark:text-white outline-none ring-cyan-300/0 transition placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
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
          <span className="text-sm font-semibold text-slate-600 dark:text-slate-300">
            Webhook URL (Slack/Discord)
          </span>
          <input
            className="mt-2 w-full rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-3 text-sm text-slate-900 dark:text-white outline-none ring-cyan-300/0 transition placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-cyan-500 focus:ring-4 focus:ring-cyan-500/20"
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
          <span className="mt-2 block text-xs leading-5 text-slate-500 dark:text-slate-400">
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
                ? "border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300"
                : "border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950 text-rose-800 dark:text-rose-300"
            }`}
          >
            {submitMessage}
          </p>
        )}
      </form>
    </section>
  );
}

type IncidentSectionProps = {
  feedbackBusyIncidentId: string | null;
  incidents: Incident[];
  investigationsByIncident: Record<string, AgentInvestigation | null>;
  onFeedback: (incident: Incident, verdict: "accurate" | null) => void;
  projectId: string;
};

function IncidentSection({
  feedbackBusyIncidentId,
  incidents,
  investigationsByIncident,
  onFeedback,
  projectId
}: IncidentSectionProps) {
  return (
    <section className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
      <SectionHeader count={incidents.length} title="장애" />
      {incidents.length === 0 ? (
        <EmptyState description="아직 이 프로젝트에서 기록된 장애가 없습니다." />
      ) : (
        <ul className="grid gap-4">
          {incidents.map((incident) => (
            <IncidentCard
              incident={incident}
              investigation={investigationsByIncident[incident.id]}
              isFeedbackBusy={feedbackBusyIncidentId === incident.id}
              key={incident.id}
              onFeedback={onFeedback}
              projectId={projectId}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * 인시던트 생애 타임라인(R4) — 열림 → 조사 결론 → 해소가 한 카드에서 완결된다.
 * 조사 피드백을 여기로 승격한 이유: 평가 루프의 입력을 인시던트를 보는 바로
 * 그 순간에 받는 것이 입력률을 만든다.
 */
function IncidentCard({
  incident,
  investigation,
  isFeedbackBusy,
  onFeedback,
  projectId
}: {
  incident: Incident;
  investigation: AgentInvestigation | null | undefined;
  isFeedbackBusy: boolean;
  onFeedback: (incident: Incident, verdict: "accurate" | null) => void;
  projectId: string;
}) {
  return (
    <li className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <IncidentStatusBadge status={incident.status} />
        <SeverityBadge severity={incident.severity} />
        <Badge label={incidentTriggerLabel(incident.trigger_type)} />
        {incident.is_stale && <StaleBadge />}
        <h3 className="w-full text-base font-bold text-slate-900 dark:text-white sm:w-auto sm:flex-1">
          {incident.title}
        </h3>
      </div>

      <ol className="mt-3 grid gap-0">
        <TimelineStep
          dotClassName="bg-rose-500"
          isLast={false}
          label={`발생 · ${formatDateTime(incident.started_at)}`}
        >
          <p className="break-keep text-sm leading-6 text-slate-600 dark:text-slate-300">
            {incident.summary}{" "}
            <Link
              className="font-semibold text-cyan-700 underline-offset-2 hover:underline dark:text-cyan-400"
              href={`/projects/${projectId}/check-runs/${incident.opened_check_run_id}`}
            >
              발생 검사 →
            </Link>
          </p>
        </TimelineStep>

        <TimelineStep
          dotClassName={investigation ? "bg-cyan-500" : "bg-slate-300 dark:bg-slate-600"}
          isLast={false}
          label="에이전트 조사"
        >
          {investigation ? (
            <InvestigationTimelineBody
              incident={incident}
              investigation={investigation}
              isFeedbackBusy={isFeedbackBusy}
              onFeedback={onFeedback}
              projectId={projectId}
            />
          ) : (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {investigation === undefined
                ? "조사 결과를 확인하려면 발생 검사를 여세요."
                : "자동 조사가 붙지 않은 인시던트입니다(쿨다운 등) — 발생 검사에서 수동 조사를 시작할 수 있습니다."}
            </p>
          )}
        </TimelineStep>

        <TimelineStep
          dotClassName={incident.resolved_at ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"}
          isLast
          label={
            incident.resolved_at
              ? `해소 · ${formatNullableDateTime(incident.resolved_at)}`
              : "미해소"
          }
        >
          {incident.resolved_at ? (
            incident.resolved_check_run_id ? (
              <Link
                className="text-sm font-semibold text-cyan-700 underline-offset-2 hover:underline dark:text-cyan-400"
                href={`/projects/${projectId}/check-runs/${incident.resolved_check_run_id}`}
              >
                회복을 확인한 검사 →
              </Link>
            ) : (
              <p className="text-sm text-slate-500 dark:text-slate-400">회복 확인됨</p>
            )
          ) : (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              해소는 다음 검사에서 판정됩니다.
            </p>
          )}
        </TimelineStep>
      </ol>

      {incident.is_stale && (
        <p className="mt-4 break-keep rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
          이 프로젝트는 {formatNullableDateTime(incident.project_last_checked_at ?? null)} 이후 검사되지
          않았습니다. 장애 해소는 다음 검사에서 판정되므로, 서비스가 이미 회복됐더라도 이
          장애는 열린 채로 남아 있습니다 — <b>현재 상태가 아니라 그때의 기록</b>입니다.
          정기 검사를 켜면 다시 확인됩니다.
        </p>
      )}
    </li>
  );
}

function TimelineStep({
  children,
  dotClassName,
  isLast,
  label
}: {
  children: React.ReactNode;
  dotClassName: string;
  isLast: boolean;
  label: string;
}) {
  return (
    <li className="relative pl-6">
      <span aria-hidden className={`absolute left-0 top-1.5 h-2.5 w-2.5 rounded-full ${dotClassName}`} />
      {!isLast && (
        <span aria-hidden className="absolute bottom-0 left-[4px] top-5 w-px bg-slate-200 dark:bg-slate-700" />
      )}
      <p className="text-xs font-bold uppercase tracking-[0.08em] text-slate-400 dark:text-slate-500">
        {label}
      </p>
      <div className={isLast ? "mt-1" : "mt-1 pb-4"}>{children}</div>
    </li>
  );
}

function InvestigationTimelineBody({
  incident,
  investigation,
  isFeedbackBusy,
  onFeedback,
  projectId
}: {
  incident: Incident;
  investigation: AgentInvestigation;
  isFeedbackBusy: boolean;
  onFeedback: (incident: Incident, verdict: "accurate" | null) => void;
  projectId: string;
}) {
  return (
    <div>
      <p className="break-keep text-sm leading-6 text-slate-700 dark:text-slate-200">
        <span className="font-bold">{rootCauseLabel(investigation.root_cause)}</span>
        <span className="text-slate-400 dark:text-slate-500">
          {" "}
          · 신뢰 {investigation.confidence === "high" ? "높음" : "낮음"}
        </span>
        {" — "}
        {investigation.recommendation}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
        {investigation.feedback_verdict ? (
          <>
            <span className="font-semibold text-slate-500 dark:text-slate-400">
              피드백:{" "}
              {investigation.feedback_verdict === "accurate"
                ? "✅ 정확함"
                : `❌ 부정확${
                    investigation.feedback_root_cause
                      ? ` (실제: ${rootCauseLabel(investigation.feedback_root_cause)})`
                      : ""
                  }`}
            </span>
            <button
              className="font-semibold text-slate-400 underline underline-offset-2 hover:text-slate-600 disabled:opacity-50 dark:text-slate-500 dark:hover:text-slate-300"
              disabled={isFeedbackBusy}
              onClick={() => onFeedback(incident, null)}
              type="button"
            >
              되돌리기
            </button>
          </>
        ) : (
          <>
            <span className="text-slate-400 dark:text-slate-500">이 진단이 맞았나요?</span>
            <button
              className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 font-bold text-emerald-800 transition hover:border-emerald-400 disabled:opacity-50 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300"
              disabled={isFeedbackBusy}
              onClick={() => onFeedback(incident, "accurate")}
              type="button"
            >
              👍 정확함
            </button>
            <Link
              className="rounded-full border border-rose-200 bg-rose-50 px-2.5 py-0.5 font-bold text-rose-800 transition hover:border-rose-400 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300"
              href={`/projects/${projectId}/check-runs/${incident.opened_check_run_id}#investigation`}
            >
              👎 부정확 — 실제 원인 선택 →
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

function StaleBadge() {
  return (
    <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-bold text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300">
      오래된 기록
    </span>
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
    <section className="rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white">알림 목록</h2>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            로드된 알림 {totalAlertCount}개 중 {alerts.length}개를 표시합니다.
          </p>
        </div>
        <span className="rounded-full bg-cyan-50 dark:bg-cyan-950 px-3 py-1 text-xs font-bold text-cyan-700 dark:text-cyan-400 ring-1 ring-cyan-200 dark:ring-cyan-900">
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
          className="rounded-2xl border border-cyan-300 dark:border-cyan-800 px-4 py-2 text-sm font-bold text-cyan-700 dark:text-cyan-400 transition hover:border-cyan-500 hover:bg-cyan-50 dark:hover:bg-cyan-950 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!hasMoreAlerts || isLoadingMoreAlerts}
          onClick={onLoadMore}
          type="button"
        >
          {isLoadingMoreAlerts ? "더 불러오는 중" : "알림 더 보기"}
        </button>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {hasMoreAlerts
            ? `${LIST_LIMIT}개 단위로 더 불러옵니다.`
            : "현재 로드된 목록이 마지막 페이지입니다."}
        </p>
      </div>

      {listMessage && (
        <p className="mt-4 rounded-2xl border border-cyan-200 dark:border-cyan-900 bg-cyan-50 dark:bg-cyan-950 p-4 text-sm text-cyan-700 dark:text-cyan-400">
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
                : "border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:border-cyan-400 hover:text-cyan-700 dark:hover:text-cyan-300"
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
    <li className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap gap-2">
            <AlertStatusBadge status={alert.status} />
            <Badge label={alertChannelLabel(alert.channel)} />
            <Badge label={alertTypeLabel(alert.alert_type)} />
          </div>
          <h3 className="mt-4 text-lg font-bold text-slate-900 dark:text-white">{alert.subject}</h3>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
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
        <p className="mt-4 rounded-2xl border border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950 p-4 text-sm text-rose-800 dark:text-rose-300">
          {alert.last_error}
        </p>
      )}

      {retryFeedback && (
        <p
          className={`mt-4 rounded-2xl border p-4 text-sm leading-6 ${
            retryFeedback.state === "success"
              ? "border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950 text-emerald-800 dark:text-emerald-300"
              : "border-rose-200 dark:border-rose-900 bg-rose-50 dark:bg-rose-950 text-rose-800 dark:text-rose-300"
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
      <h2 className="text-xl font-semibold text-slate-900 dark:text-white">{title}</h2>
      <span className="rounded-full bg-cyan-50 dark:bg-cyan-950 px-3 py-1 text-xs font-bold text-cyan-700 dark:text-cyan-400 ring-1 ring-cyan-200 dark:ring-cyan-900">
        {count}개
      </span>
    </div>
  );
}

function IncidentStatusBadge({ status }: { status: string }) {
  const className =
    status === "OPEN"
      ? "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900"
      : "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 ring-emerald-200 dark:ring-emerald-900";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${className}`}>
      {incidentStatusLabel(status)}
    </span>
  );
}

function SeverityBadge({ severity }: { severity: string }) {
  const className =
    severity === "RISK"
      ? "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900"
      : "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 ring-amber-200 dark:ring-amber-900";

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ${className}`}>
      {severityLabel(severity)}
    </span>
  );
}

function AlertStatusBadge({ status }: { status: string }) {
  const className =
    status === "SENT"
      ? "bg-emerald-50 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-400 ring-emerald-200 dark:ring-emerald-900"
      : status === "FAILED"
        ? "bg-rose-50 dark:bg-rose-950 text-rose-700 dark:text-rose-300 ring-rose-200 dark:ring-rose-900"
        : "bg-cyan-50 dark:bg-cyan-950 text-cyan-700 dark:text-cyan-400 ring-cyan-200 dark:ring-cyan-900";

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
