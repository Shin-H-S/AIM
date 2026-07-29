// 서버 응답 타입은 손으로 쓰지 않는다 — FastAPI의 OpenAPI 스냅샷에서 생성된
// api-schema.d.ts를 재수출한다. 백엔드 스키마가 바뀌면 CI가 스냅샷·타입
// 재생성을 강제하고, 낡은 필드를 쓰는 프런트 코드는 컴파일 에러로 드러난다.
import type { components } from "./api-schema";
import { CSRF_HEADER_NAME, getCsrfToken } from "./auth";

/**
 * 세션이 쿠키로 오가는 세계의 기본 fetch.
 *
 * credentials:"include"가 없으면 브라우저는 크로스 오리진(API 서브도메인)
 * 요청에 세션 쿠키를 싣지 않는다. csrf 헤더는 상태 변경 요청에서 서버가
 * 요구하는 double-submit 증명이다 — GET에는 불필요하지만 항상 실어도
 * 무해하고, 메서드별 분기를 없애 실수 표면을 줄인다.
 *
 * 각 API 함수의 fetcher 기본값이 이것이다. 테스트는 이전처럼 fetcher를
 * 주입해 네트워크 없이 검증한다.
 */
export const sessionFetch: typeof fetch = (input, init = {}) => {
  const csrfToken = getCsrfToken();
  return fetch(input, {
    ...init,
    credentials: "include",
    headers: {
      ...(init.headers as Record<string, string> | undefined),
      ...(csrfToken ? { [CSRF_HEADER_NAME]: csrfToken } : {})
    }
  });
};


const DEFAULT_API_BASE_URL = "http://localhost:8000";

type ApiHealthPayload = {
  status?: string;
  service?: string;
};

type AccessTokenPayload = {
  access_token?: string;
  token_type?: string;
};

export type User = components["schemas"]["UserRead"];

export type SignupPayload = {
  email: string;
  password: string;
};

export type CheckRunStatus =
  | "QUEUED"
  | "RUNNING"
  | "ANALYZING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type ScenarioRunStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export type StepResultStatus = "PASSED" | "FAILED" | "SKIPPED";

export type TestStepAction =
  | "navigate"
  | "click"
  | "fill"
  | "wait"
  | "assert_element_exists"
  | "assert_text_exists"
  | "assert_url"
  | "take_screenshot";

export type TestStepPayload = {
  action: TestStepAction;
  target: string | null;
  value: string | null;
  timeout_ms: number | null;
  is_critical: boolean;
};

export type ProjectEnvironment = "development" | "staging" | "production";

export type ScoringPreset = "service" | "content" | "internal";

export type Project = components["schemas"]["ProjectRead"];

export type ProjectPayload = {
  name: string;
  service_url: string;
  description: string | null;
  environment: ProjectEnvironment;
  scoring_preset?: ScoringPreset;
  scan_interval_minutes: number;
  scheduled_scans_enabled?: boolean;
  response_time_threshold_ms: number;
  quality_score_threshold: number;
  alert_email_enabled?: boolean;
  alert_recipient_email?: string | null;
  alert_webhook_url?: string | null;
};

export type Incident = components["schemas"]["IncidentRead"];

export type Alert = components["schemas"]["AlertRead"];

export type ProjectVerification = components["schemas"]["ProjectVerificationRead"];

export type AvailabilityResult = components["schemas"]["AvailabilityResultRead"];

export type SslResult = components["schemas"]["SslResultRead"];

export type LighthouseTopAudit = components["schemas"]["LighthouseAuditRead"];

export type LighthouseResult = components["schemas"]["LighthouseResultRead"];

export type Artifact = components["schemas"]["ArtifactRead"];

export type ScoreBreakdownReason = {
  code: string;
  points?: number;
  value?: number;
  threshold?: number;
  failed?: number;
  with_failed_steps?: number;
  clean?: number;
  errors?: number;
  seo?: number | null;
  best_practices?: number | null;
  compared?: number;
  total_drop?: number;
  regressed?: { category: string; drop: number }[];
};

export type ScoreBreakdownCategory = {
  key: string;
  weight: number;
  score: number | null;
  reasons: ScoreBreakdownReason[];
};

export type ScoreBreakdownGate = {
  code: string;
  deployment_risk: string;
  grade_cap: string;
  detail: string | null;
};

export type ScoreBreakdown = {
  version: number;
  // 프리셋 도입(0030) 이전 기록에는 없다.
  preset?: ScoringPreset | string;
  categories: ScoreBreakdownCategory[];
  gate: ScoreBreakdownGate | null;
  overall: {
    score: number;
    evaluated_weight: number;
    grade_before_gate: string;
  };
};

// score_breakdown은 자유 JSON이라 스키마가 구조를 모른다. 그 필드 하나만
// 수기 구조(ScoreBreakdown)로 좁히고 나머지는 생성 타입을 그대로 쓴다.
export type ScoreResult = Omit<components["schemas"]["ScoreResultRead"], "score_breakdown"> & {
  score_breakdown: ScoreBreakdown | null;
};

export type RunComparison = components["schemas"]["RunComparisonRead"];

export type BaselineComparison = components["schemas"]["BaselineComparisonRead"];

export type AIReportSummary = components["schemas"]["AIReportSummaryRead"];

export type AIReportStatementType =
  | "confirmed_observation"
  | "evidence_based_inference"
  | "unknown_cause";

export type AIReportSeverity = "info" | "warning" | "risk";

export type AIReportScore = {
  overall_score: number;
  grade: "A" | "B" | "C" | "D" | "F";
  deployment_risk: "STABLE" | "WARNING" | "RISK";
  gate_reason: string | null;
  evidence_ids: string[];
};

export type AIReportIssue = {
  id: string;
  priority: number;
  title: string;
  statement_type: AIReportStatementType;
  severity: AIReportSeverity;
  category: string;
  summary: string;
  evidence_ids: string[];
  expected_user_impact: string;
  recommended_next_action: string;
  unknown_reason: string | null;
};

export type AIReportChange = {
  id: string;
  category: string;
  summary: string;
  evidence_ids: string[];
  metric_name: string | null;
  previous_value: string | number | boolean | null;
  current_value: string | number | boolean | null;
  delta: string | number | boolean | null;
};

// AI 리포트 상세는 report_json(자유 JSON)의 내부 구조다. OpenAPI 스키마는
// dict로만 알고 있으므로 이 타입은 수기로 유지한다 — 서버의
// docs/architecture/ai-diagnosis-report.md 가 구조의 원천이다.
export type AIReportPayload = {
  schema_version: string;
  input_schema_version: string;
  project_id: string;
  check_run_id: string;
  generated_at: string;
  summary: string;
  score: AIReportScore;
  top_issues: AIReportIssue[];
  improved_areas: AIReportChange[];
  regressed_areas: AIReportChange[];
  generation_warnings: string[];
};

export type AIReportDetail = AIReportSummary & {
  schema_version: string;
  input_schema_version: string;
  report_json: AIReportPayload;
};

// score_result 안의 score_breakdown(자유 JSON)을 좁힌 ScoreResult를 쓰기 위한 교차.
export type CheckRunDetail = Omit<
  components["schemas"]["CheckRunDetailRead"],
  "score_result"
> & {
  score_result: ScoreResult | null;
};

export type CheckRunScoreSummary = components["schemas"]["CheckRunScoreSummaryRead"];

export type CheckRunSummary = components["schemas"]["CheckRunListItemRead"];

export type StepResult = components["schemas"]["StepResultRead"];

export type ConsoleError = components["schemas"]["ConsoleErrorRead"];

export type NetworkFailure = components["schemas"]["NetworkFailureRead"];

export type TestStep = components["schemas"]["TestStepRead"];

export type TestScenario = components["schemas"]["TestScenarioRead"];

export type TestScenarioPayload = {
  name: string;
  description: string | null;
  is_active: boolean;
  steps: TestStepPayload[];
};

export type ScenarioRun = components["schemas"]["ScenarioRunRead"];

export type ScenarioRunDetail = components["schemas"]["ScenarioRunDetailRead"];

export type CheckRunDetailResult =
  | {
      state: "success";
      checkRun: CheckRunDetail;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type ProjectListResult =
  | {
      state: "success";
      projects: Project[];
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "unavailable";
    };

export type ProjectDetailResult =
  | {
      state: "success";
      project: Project;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type ProjectMutationResult =
  | {
      state: "success";
      project: Project;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "invalid";
    }
  | {
      state: "unavailable";
    };

export type ProjectVerificationReadResult =
  | {
      state: "success";
      verification: ProjectVerification;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type VerifyProjectDomainResult =
  | {
      state: "success";
      verification: ProjectVerification;
      status: string;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "verification-failed";
    }
  | {
      state: "unavailable";
    };

export type LoginResult =
  | {
      state: "success";
    }
  | {
      state: "invalid-credentials";
    }
  | {
      state: "email-not-verified";
    }
  | {
      state: "unavailable";
    };

export type SignupResult =
  | {
      state: "success";
      user: User;
    }
  | {
      state: "invalid";
    }
  | {
      state: "email-already-registered";
    }
  | {
      state: "unavailable";
    };

export type PasswordResetRequestResult =
  | {
      state: "accepted";
    }
  | {
      state: "unavailable";
    };

export type PasswordResetConfirmResult =
  | {
      state: "success";
    }
  | {
      state: "invalid-token";
    }
  | {
      state: "unavailable";
    };

export type EmailVerificationRequestResult =
  | {
      state: "accepted";
    }
  | {
      state: "unavailable";
    };

export type EmailVerificationConfirmResult =
  | {
      state: "success";
    }
  | {
      state: "invalid-token";
    }
  | {
      state: "unavailable";
    };

export type CurrentUserResult =
  | {
      state: "success";
      user: User;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "unavailable";
    };

export type LogoutResult =
  | {
      state: "success";
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "unavailable";
    };

export type CheckRunListResult =
  | {
      state: "success";
      checkRuns: CheckRunSummary[];
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type IncidentListResult =
  | {
      state: "success";
      incidents: Incident[];
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type AlertListResult =
  | {
      state: "success";
      alerts: Alert[];
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type RetryAlertResult =
  | {
      state: "success";
      alert: Alert;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "conflict";
    }
  | {
      state: "unavailable";
    };

export type CreateCheckRunResult =
  | {
      state: "success";
      checkRun: CheckRunSummary;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "conflict";
    }
  | {
      state: "unavailable";
    };

export type AIReportDetailResult =
  | {
      state: "success";
      report: AIReportDetail;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type ScenarioRunDetailResult =
  | {
      state: "success";
      scenarioRun: ScenarioRunDetail;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type ScenarioRunListResult =
  | {
      state: "success";
      scenarioRuns: ScenarioRun[];
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type ScenarioListResult =
  | {
      state: "success";
      scenarios: TestScenario[];
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type CreateScenarioResult =
  | {
      state: "success";
      scenario: TestScenario;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "invalid";
    }
  | {
      state: "unavailable";
    };

export type UpdateScenarioResult =
  | {
      state: "success";
      scenario: TestScenario;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "invalid";
    }
  | {
      state: "unavailable";
    };

export type DeleteScenarioResult =
  | {
      state: "success";
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type CreateScenarioRunResult =
  | {
      state: "success";
      scenarioRun: ScenarioRun;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "conflict";
    }
  | {
      state: "unavailable";
    };

export type ArtifactDownloadResult =
  | {
      state: "success";
      blob: Blob;
      filename: string;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "conflict";
    }
  | {
      state: "unavailable";
    };

export type CancelCheckRunResult =
  | {
      state: "success";
      checkRun: CheckRunSummary;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type DeleteProjectResult =
  | {
      state: "success";
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type ProjectBaselineMutationResult =
  | {
      state: "success";
      project: Project;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "conflict";
    }
  | {
      state: "unavailable";
    };

export type BaselineComparisonResult =
  | {
      state: "success";
      comparison: BaselineComparison;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "conflict";
    }
  | {
      state: "unavailable";
    };

export type HealthCheckResult =
  | {
      state: "loading";
    }
  | {
      state: "available";
      status: string;
      service: string;
    }
  | {
      state: "unavailable";
    };

export function getApiBaseUrl(value = process.env.NEXT_PUBLIC_API_URL): string {
  const normalizedValue = value?.trim() || DEFAULT_API_BASE_URL;
  const url = new URL(normalizedValue);

  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_API_URL must use HTTP or HTTPS.");
  }

  return url.origin;
}

export function getApiHealthUrl(apiBaseUrl = getApiBaseUrl()): string {
  return new URL("/health", getApiBaseUrl(apiBaseUrl)).toString();
}

export function getSignupUrl(apiBaseUrl = getApiBaseUrl()): string {
  return new URL("/auth/signup", getApiBaseUrl(apiBaseUrl)).toString();
}

export function getLoginUrl(apiBaseUrl = getApiBaseUrl()): string {
  return new URL("/auth/login", getApiBaseUrl(apiBaseUrl)).toString();
}

export function getPasswordResetRequestUrl(apiBaseUrl = getApiBaseUrl()): string {
  return new URL("/auth/password-reset/request", getApiBaseUrl(apiBaseUrl)).toString();
}

export function getPasswordResetConfirmUrl(apiBaseUrl = getApiBaseUrl()): string {
  return new URL("/auth/password-reset/confirm", getApiBaseUrl(apiBaseUrl)).toString();
}

export function getEmailVerificationRequestUrl(apiBaseUrl = getApiBaseUrl()): string {
  return new URL("/auth/email-verification/request", getApiBaseUrl(apiBaseUrl)).toString();
}

export function getEmailVerificationConfirmUrl(apiBaseUrl = getApiBaseUrl()): string {
  return new URL("/auth/email-verification/confirm", getApiBaseUrl(apiBaseUrl)).toString();
}

export function getCurrentUserUrl(apiBaseUrl = getApiBaseUrl()): string {
  return new URL("/auth/me", getApiBaseUrl(apiBaseUrl)).toString();
}

export function getLogoutUrl(apiBaseUrl = getApiBaseUrl()): string {
  return new URL("/auth/logout", getApiBaseUrl(apiBaseUrl)).toString();
}

export type PaginationParams = {
  limit?: number;
  offset?: number;
};

function applyPagination(url: URL, pagination: PaginationParams): URL {
  if (pagination.limit !== undefined) {
    url.searchParams.set("limit", String(pagination.limit));
  }

  if (pagination.offset !== undefined) {
    url.searchParams.set("offset", String(pagination.offset));
  }

  return url;
}

export function getProjectsUrl(
  apiBaseUrl = getApiBaseUrl(),
  pagination: PaginationParams = {}
): string {
  return applyPagination(new URL("/projects", getApiBaseUrl(apiBaseUrl)), pagination).toString();
}

export function getProjectDetailUrl(projectId: string, apiBaseUrl = getApiBaseUrl()): string {
  return new URL(`/projects/${encodeURIComponent(projectId)}`, getApiBaseUrl(apiBaseUrl)).toString();
}

export function getProjectVerificationUrl(
  projectId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/verification`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getProjectVerifyUrl(projectId: string, apiBaseUrl = getApiBaseUrl()): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/verify`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getCheckRunsUrl(
  projectId: string,
  apiBaseUrl = getApiBaseUrl(),
  pagination: PaginationParams = {}
): string {
  return applyPagination(
    new URL(`/projects/${encodeURIComponent(projectId)}/check-runs`, getApiBaseUrl(apiBaseUrl)),
    pagination
  ).toString();
}

export function getProjectIncidentsUrl(
  projectId: string,
  apiBaseUrl = getApiBaseUrl(),
  pagination: PaginationParams = {}
): string {
  return applyPagination(
    new URL(`/projects/${encodeURIComponent(projectId)}/incidents`, getApiBaseUrl(apiBaseUrl)),
    pagination
  ).toString();
}

export function getProjectAlertsUrl(
  projectId: string,
  apiBaseUrl = getApiBaseUrl(),
  pagination: PaginationParams = {}
): string {
  return applyPagination(
    new URL(`/projects/${encodeURIComponent(projectId)}/alerts`, getApiBaseUrl(apiBaseUrl)),
    pagination
  ).toString();
}

export function getRetryAlertUrl(
  projectId: string,
  alertId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/alerts/${encodeURIComponent(alertId)}/retry`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getCheckRunDetailUrl(
  projectId: string,
  checkRunId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/check-runs/${encodeURIComponent(checkRunId)}`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getCheckRunAIReportUrl(
  projectId: string,
  checkRunId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/check-runs/${encodeURIComponent(
      checkRunId
    )}/ai-report`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getCancelCheckRunUrl(
  projectId: string,
  checkRunId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/check-runs/${encodeURIComponent(
      checkRunId
    )}/cancel`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getProjectBaselineUrl(projectId: string, apiBaseUrl = getApiBaseUrl()): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/baseline`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getBaselineComparisonUrl(
  projectId: string,
  checkRunId: string,
  apiBaseUrl = getApiBaseUrl(),
  baselineCheckRunId?: string
): string {
  const url = new URL(
    `/projects/${encodeURIComponent(projectId)}/check-runs/${encodeURIComponent(
      checkRunId
    )}/baseline-comparison`,
    getApiBaseUrl(apiBaseUrl)
  );

  if (baselineCheckRunId) {
    url.searchParams.set("baseline_check_run_id", baselineCheckRunId);
  }

  return url.toString();
}

export function getScenarioRunsUrl(
  projectId: string,
  scenarioId: string,
  apiBaseUrl = getApiBaseUrl(),
  pagination: PaginationParams = {}
): string {
  return applyPagination(
    new URL(
      `/projects/${encodeURIComponent(projectId)}/scenarios/${encodeURIComponent(
        scenarioId
      )}/runs`,
      getApiBaseUrl(apiBaseUrl)
    ),
    pagination
  ).toString();
}

export function getScenarioRunDetailUrl(
  projectId: string,
  scenarioId: string,
  scenarioRunId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/scenarios/${encodeURIComponent(
      scenarioId
    )}/runs/${encodeURIComponent(scenarioRunId)}`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getScenariosUrl(projectId: string, apiBaseUrl = getApiBaseUrl()): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/scenarios`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getScenarioUrl(
  projectId: string,
  scenarioId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/scenarios/${encodeURIComponent(scenarioId)}`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getCreateScenarioRunUrl(
  projectId: string,
  scenarioId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/scenarios/${encodeURIComponent(
      scenarioId
    )}/runs`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getArtifactDownloadUrl(
  artifactId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/artifacts/${encodeURIComponent(artifactId)}/download`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export async function fetchApiHealth(
  fetcher: typeof fetch = fetch,
  apiBaseUrl?: string
): Promise<HealthCheckResult> {
  try {
    const response = await fetcher(getApiHealthUrl(apiBaseUrl ?? getApiBaseUrl()), {
      cache: "no-store"
    });

    if (!response.ok) {
      return { state: "unavailable" };
    }

    const payload = (await response.json()) as ApiHealthPayload;

    return {
      state: "available",
      status: payload.status ?? "unknown",
      service: payload.service ?? "aim-api"
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function loginUser({
  email,
  password,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  email: string;
  password: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<LoginResult> {
  try {
    const response = await fetcher(getLoginUrl(apiBaseUrl ?? getApiBaseUrl()), {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email, password })
    });

    if (response.status === 401) {
      return { state: "invalid-credentials" };
    }

    if (response.status === 403) {
      return { state: "email-not-verified" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    // 세션은 응답의 Set-Cookie(httpOnly)로 성립한다. 본문 토큰은 스크립트용
    // Bearer 경로의 잔재이므로 여기서는 발급 여부만 확인한다.
    const payload = (await response.json()) as AccessTokenPayload;
    if (!payload.access_token?.trim()) {
      return { state: "unavailable" };
    }

    return { state: "success" };
  } catch {
    return { state: "unavailable" };
  }
}

export async function signupUser({
  payload,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  payload: SignupPayload;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<SignupResult> {
  try {
    const response = await fetcher(getSignupUrl(apiBaseUrl ?? getApiBaseUrl()), {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (response.status === 409) {
      return { state: "email-already-registered" };
    }

    if (response.status === 422) {
      return { state: "invalid" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      user: (await response.json()) as User
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function requestPasswordReset({
  email,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  email: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<PasswordResetRequestResult> {
  try {
    const response = await fetcher(getPasswordResetRequestUrl(apiBaseUrl ?? getApiBaseUrl()), {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email })
    });

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return { state: "accepted" };
  } catch {
    return { state: "unavailable" };
  }
}

export async function confirmPasswordReset({
  token,
  newPassword,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  token: string;
  newPassword: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<PasswordResetConfirmResult> {
  try {
    const response = await fetcher(getPasswordResetConfirmUrl(apiBaseUrl ?? getApiBaseUrl()), {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ token, new_password: newPassword })
    });

    if (response.status === 400 || response.status === 422) {
      return { state: "invalid-token" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return { state: "success" };
  } catch {
    return { state: "unavailable" };
  }
}

export async function requestEmailVerification({
  email,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  email: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<EmailVerificationRequestResult> {
  try {
    const response = await fetcher(getEmailVerificationRequestUrl(apiBaseUrl ?? getApiBaseUrl()), {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email })
    });

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return { state: "accepted" };
  } catch {
    return { state: "unavailable" };
  }
}

export async function confirmEmailVerification({
  token,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  token: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<EmailVerificationConfirmResult> {
  try {
    const response = await fetcher(getEmailVerificationConfirmUrl(apiBaseUrl ?? getApiBaseUrl()), {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ token })
    });

    if (response.status === 400 || response.status === 422) {
      return { state: "invalid-token" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return { state: "success" };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchCurrentUser({
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<CurrentUserResult> {
  try {
    const response = await fetcher(getCurrentUserUrl(apiBaseUrl ?? getApiBaseUrl()), {
      cache: "no-store",
      headers: {}
    });

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      user: (await response.json()) as User
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function logoutUser({
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<LogoutResult> {
  try {
    const response = await fetcher(getLogoutUrl(apiBaseUrl ?? getApiBaseUrl()), {
      method: "POST",
      cache: "no-store",
      headers: {}
    });

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return { state: "success" };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchProjects({
  fetcher = sessionFetch,
  apiBaseUrl,
  limit,
  offset
}: {
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
  limit?: number;
  offset?: number;
}): Promise<ProjectListResult> {
  try {
    const response = await fetcher(
      getProjectsUrl(apiBaseUrl ?? getApiBaseUrl(), { limit, offset }),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401) {
      return { state: "unauthorized" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      projects: (await response.json()) as Project[]
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchProject({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ProjectDetailResult> {
  try {
    const response = await fetcher(
      getProjectDetailUrl(projectId, apiBaseUrl ?? getApiBaseUrl()),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      project: (await response.json()) as Project
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function createProject({
  payload,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  payload: ProjectPayload;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ProjectMutationResult> {
  try {
    const response = await fetcher(getProjectsUrl(apiBaseUrl ?? getApiBaseUrl()), {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    return await mapProjectMutationResponse(response);
  } catch {
    return { state: "unavailable" };
  }
}

export async function updateProject({
  projectId,
  payload,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  payload: ProjectPayload;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ProjectMutationResult> {
  try {
    const response = await fetcher(
      getProjectDetailUrl(projectId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "PATCH",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      }
    );

    return await mapProjectMutationResponse(response);
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchProjectVerification({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ProjectVerificationReadResult> {
  try {
    const response = await fetcher(
      getProjectVerificationUrl(projectId, apiBaseUrl ?? getApiBaseUrl()),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      verification: (await response.json()) as ProjectVerification
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function verifyProjectDomain({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<VerifyProjectDomainResult> {
  try {
    const response = await fetcher(
      getProjectVerifyUrl(projectId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "POST",
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (response.status === 400) {
      return { state: "verification-failed" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    const payload = (await response.json()) as ProjectVerification & { status?: string };
    const { status, ...verification } = payload;

    return {
      state: "success",
      verification,
      status: status ?? "verified"
    };
  } catch {
    return { state: "unavailable" };
  }
}

async function mapProjectMutationResponse(response: Response): Promise<ProjectMutationResult> {
  if (response.status === 401 || response.status === 403) {
    return { state: "unauthorized" };
  }

  if (response.status === 404) {
    return { state: "not-found" };
  }

  if (response.status === 400 || response.status === 422) {
    return { state: "invalid" };
  }

  if (!response.ok) {
    return { state: "unavailable" };
  }

  return {
    state: "success",
    project: (await response.json()) as Project
  };
}

export async function fetchCheckRuns({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl,
  limit,
  offset
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
  limit?: number;
  offset?: number;
}): Promise<CheckRunListResult> {
  try {
    const response = await fetcher(
      getCheckRunsUrl(projectId, apiBaseUrl ?? getApiBaseUrl(), { limit, offset }),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      checkRuns: (await response.json()) as CheckRunSummary[]
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchProjectIncidents({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl,
  limit,
  offset
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
  limit?: number;
  offset?: number;
}): Promise<IncidentListResult> {
  try {
    const response = await fetcher(
      getProjectIncidentsUrl(projectId, apiBaseUrl ?? getApiBaseUrl(), { limit, offset }),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      incidents: (await response.json()) as Incident[]
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchProjectAlerts({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl,
  limit,
  offset
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
  limit?: number;
  offset?: number;
}): Promise<AlertListResult> {
  try {
    const response = await fetcher(
      getProjectAlertsUrl(projectId, apiBaseUrl ?? getApiBaseUrl(), { limit, offset }),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      alerts: (await response.json()) as Alert[]
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function retryAlert({
  projectId,
  alertId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  alertId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<RetryAlertResult> {
  try {
    const response = await fetcher(
      getRetryAlertUrl(projectId, alertId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "POST",
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (response.status === 409) {
      return { state: "conflict" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      alert: (await response.json()) as Alert
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function createCheckRun({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<CreateCheckRunResult> {
  try {
    const response = await fetcher(
      getCheckRunsUrl(projectId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json"
        },
        body: "{}"
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (response.status === 409) {
      return { state: "conflict" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      checkRun: (await response.json()) as CheckRunSummary
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function downloadArtifact({
  artifactId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  artifactId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ArtifactDownloadResult> {
  try {
    const response = await fetcher(
      getArtifactDownloadUrl(artifactId, apiBaseUrl ?? getApiBaseUrl()),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (response.status === 409) {
      return { state: "conflict" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      blob: await response.blob(),
      filename:
        getFilenameFromContentDisposition(response.headers.get("content-disposition")) ??
        `artifact-${artifactId}`
    };
  } catch {
    return { state: "unavailable" };
  }
}

function getFilenameFromContentDisposition(value: string | null): string | null {
  if (!value) {
    return null;
  }

  const encodedFilenameMatch = /filename\*=UTF-8''([^;]+)/i.exec(value);
  const encodedFilename = encodedFilenameMatch?.[1];
  if (encodedFilename) {
    const normalizedFilename = encodedFilename.trim().replace(/^"|"$/g, "");
    try {
      return decodeURIComponent(normalizedFilename);
    } catch {
      return normalizedFilename;
    }
  }

  const quotedFilenameMatch = /filename="([^"]+)"/i.exec(value);
  if (quotedFilenameMatch?.[1]) {
    return quotedFilenameMatch[1];
  }

  const plainFilenameMatch = /filename=([^;]+)/i.exec(value);
  return plainFilenameMatch?.[1]?.trim() ?? null;
}

export async function fetchCheckRunDetail({
  projectId,
  checkRunId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<CheckRunDetailResult> {
  try {
    const response = await fetcher(
      getCheckRunDetailUrl(projectId, checkRunId, apiBaseUrl ?? getApiBaseUrl()),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      checkRun: (await response.json()) as CheckRunDetail
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchCheckRunAIReport({
  projectId,
  checkRunId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<AIReportDetailResult> {
  try {
    const response = await fetcher(
      getCheckRunAIReportUrl(projectId, checkRunId, apiBaseUrl ?? getApiBaseUrl()),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      report: (await response.json()) as AIReportDetail
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function cancelCheckRun({
  projectId,
  checkRunId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<CancelCheckRunResult> {
  try {
    const response = await fetcher(
      getCancelCheckRunUrl(projectId, checkRunId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "POST",
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      checkRun: (await response.json()) as CheckRunSummary
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function deleteProject({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<DeleteProjectResult> {
  try {
    const response = await fetcher(
      getProjectDetailUrl(projectId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "DELETE",
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return { state: "success" };
  } catch {
    return { state: "unavailable" };
  }
}

export async function setProjectBaseline({
  projectId,
  checkRunId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ProjectBaselineMutationResult> {
  try {
    const response = await fetcher(
      getProjectBaselineUrl(projectId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "PUT",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ check_run_id: checkRunId })
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (response.status === 409) {
      return { state: "conflict" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      project: (await response.json()) as Project
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function clearProjectBaseline({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ProjectBaselineMutationResult> {
  try {
    const response = await fetcher(
      getProjectBaselineUrl(projectId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "DELETE",
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      project: (await response.json()) as Project
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchBaselineComparison({
  projectId,
  checkRunId,
  baselineCheckRunId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  baselineCheckRunId?: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<BaselineComparisonResult> {
  try {
    const response = await fetcher(
      getBaselineComparisonUrl(
        projectId,
        checkRunId,
        apiBaseUrl ?? getApiBaseUrl(),
        baselineCheckRunId
      ),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (response.status === 409) {
      return { state: "conflict" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      comparison: (await response.json()) as BaselineComparison
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchScenarioRunDetail({
  projectId,
  scenarioId,
  scenarioRunId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  scenarioId: string;
  scenarioRunId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ScenarioRunDetailResult> {
  try {
    const response = await fetcher(
      getScenarioRunDetailUrl(
        projectId,
        scenarioId,
        scenarioRunId,
        apiBaseUrl ?? getApiBaseUrl()
      ),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      scenarioRun: (await response.json()) as ScenarioRunDetail
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchScenarioRuns({
  projectId,
  scenarioId,
  fetcher = sessionFetch,
  apiBaseUrl,
  limit,
  offset
}: {
  projectId: string;
  scenarioId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
  limit?: number;
  offset?: number;
}): Promise<ScenarioRunListResult> {
  try {
    const response = await fetcher(
      getScenarioRunsUrl(projectId, scenarioId, apiBaseUrl ?? getApiBaseUrl(), {
        limit,
        offset
      }),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      scenarioRuns: (await response.json()) as ScenarioRun[]
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchScenarios({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ScenarioListResult> {
  try {
    const response = await fetcher(getScenariosUrl(projectId, apiBaseUrl ?? getApiBaseUrl()), {
      cache: "no-store",
      headers: {}
    });

    if (response.status === 401) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      scenarios: (await response.json()) as TestScenario[]
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function createScenario({
  projectId,
  payload,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  payload: TestScenarioPayload;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<CreateScenarioResult> {
  try {
    const response = await fetcher(getScenariosUrl(projectId, apiBaseUrl ?? getApiBaseUrl()), {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (response.status === 400 || response.status === 422) {
      return { state: "invalid" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      scenario: (await response.json()) as TestScenario
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function updateScenario({
  projectId,
  scenarioId,
  payload,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  scenarioId: string;
  payload: TestScenarioPayload;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<UpdateScenarioResult> {
  try {
    const response = await fetcher(
      getScenarioUrl(projectId, scenarioId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "PATCH",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (response.status === 400 || response.status === 422) {
      return { state: "invalid" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      scenario: (await response.json()) as TestScenario
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function deleteScenario({
  projectId,
  scenarioId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  scenarioId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<DeleteScenarioResult> {
  try {
    const response = await fetcher(
      getScenarioUrl(projectId, scenarioId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "DELETE",
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return { state: "success" };
  } catch {
    return { state: "unavailable" };
  }
}

export async function createScenarioRun({
  projectId,
  scenarioId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  scenarioId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<CreateScenarioRunResult> {
  try {
    const response = await fetcher(
      getCreateScenarioRunUrl(projectId, scenarioId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "POST",
        cache: "no-store",
        headers: {
          "Content-Type": "application/json"
        },
        body: "{}"
      }
    );

    if (response.status === 401) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (response.status === 409) {
      return { state: "conflict" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      scenarioRun: (await response.json()) as ScenarioRun
    };
  } catch {
    return { state: "unavailable" };
  }
}

export type ProjectApiToken = components["schemas"]["ProjectApiTokenRead"];

export type IssuedProjectApiToken = ProjectApiToken & {
  token: string;
};

export type CreateProjectApiTokenResult =
  | {
      state: "success";
      token: IssuedProjectApiToken;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type ProjectApiTokenListResult =
  | {
      state: "success";
      tokens: ProjectApiToken[];
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type RevokeProjectApiTokenResult =
  | {
      state: "success";
      token: ProjectApiToken;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export function getProjectApiTokensUrl(projectId: string, apiBaseUrl = getApiBaseUrl()): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/tokens`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getProjectApiTokenUrl(
  projectId: string,
  tokenId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/tokens/${encodeURIComponent(tokenId)}`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export async function createProjectApiToken({
  projectId,
  name,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  name: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<CreateProjectApiTokenResult> {
  try {
    const response = await fetcher(getProjectApiTokensUrl(projectId, apiBaseUrl), {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ name })
    });

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      token: (await response.json()) as IssuedProjectApiToken
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchProjectApiTokens({
  projectId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ProjectApiTokenListResult> {
  try {
    const response = await fetcher(getProjectApiTokensUrl(projectId, apiBaseUrl), {
      method: "GET",
      cache: "no-store",
      headers: {}
    });

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      tokens: (await response.json()) as ProjectApiToken[]
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function revokeProjectApiToken({
  projectId,
  tokenId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  tokenId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<RevokeProjectApiTokenResult> {
  try {
    const response = await fetcher(getProjectApiTokenUrl(projectId, tokenId, apiBaseUrl), {
      method: "DELETE",
      cache: "no-store",
      headers: {}
    });

    if (response.status === 401 || response.status === 403) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      token: (await response.json()) as ProjectApiToken
    };
  } catch {
    return { state: "unavailable" };
  }
}


export type AgentToolCall = components["schemas"]["AgentToolCallRead"];

export type AgentLlmCall = components["schemas"]["AgentLlmCallRead"];

export type AgentInvestigation = components["schemas"]["AgentInvestigationRead"];

export type AgentInvestigationVerdict = "accurate" | "inaccurate";

export type AgentInvestigationFeedbackResult =
  | {
      state: "success";
      investigation: AgentInvestigation;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type AgentInvestigationResult =
  | {
      state: "success";
      investigation: AgentInvestigation;
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export type AgentInvestigationRequestResult =
  | {
      state: "accepted";
    }
  | {
      state: "conflict";
    }
  | {
      state: "unauthorized";
    }
  | {
      state: "not-found";
    }
  | {
      state: "unavailable";
    };

export function getCheckRunInvestigationUrl(
  projectId: string,
  checkRunId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return new URL(
    `/projects/${encodeURIComponent(projectId)}/check-runs/${encodeURIComponent(
      checkRunId
    )}/investigation`,
    getApiBaseUrl(apiBaseUrl)
  ).toString();
}

export function getCheckRunInvestigationFeedbackUrl(
  projectId: string,
  checkRunId: string,
  apiBaseUrl = getApiBaseUrl()
): string {
  return `${getCheckRunInvestigationUrl(projectId, checkRunId, apiBaseUrl)}/feedback`;
}

/**
 * 조사가 맞았는지 남긴다. 이 값이 조사 정확도를 합성 평가셋이 아니라
 * 실운영 데이터로 재는 유일한 원자료다.
 */
export async function submitAgentInvestigationFeedback({
  projectId,
  checkRunId,
  verdict,
  rootCause,
  note,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  verdict: AgentInvestigationVerdict;
  rootCause?: string | null;
  note?: string | null;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<AgentInvestigationFeedbackResult> {
  return sendAgentInvestigationFeedback({
    projectId,
    checkRunId,
    method: "PUT",
    body: {
      verdict,
      root_cause: rootCause ?? null,
      note: note ?? null
    },
    fetcher,
    apiBaseUrl
  });
}

/** 잘못 누른 피드백을 되돌린다 — 오입력이 라벨로 굳으면 안 된다. */
export async function clearAgentInvestigationFeedback({
  projectId,
  checkRunId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<AgentInvestigationFeedbackResult> {
  return sendAgentInvestigationFeedback({
    projectId,
    checkRunId,
    method: "DELETE",
    fetcher,
    apiBaseUrl
  });
}

async function sendAgentInvestigationFeedback({
  projectId,
  checkRunId,
  method,
  body,
  fetcher,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  method: "PUT" | "DELETE";
  body?: Record<string, unknown>;
  fetcher: typeof fetch;
  apiBaseUrl?: string;
}): Promise<AgentInvestigationFeedbackResult> {
  try {
    const response = await fetcher(
      getCheckRunInvestigationFeedbackUrl(projectId, checkRunId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method,
        cache: "no-store",
        headers: {
          ...(body ? { "Content-Type": "application/json" } : {})
        },
        ...(body ? { body: JSON.stringify(body) } : {})
      }
    );

    if (response.status === 401) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      investigation: (await response.json()) as AgentInvestigation
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function fetchAgentInvestigation({
  projectId,
  checkRunId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<AgentInvestigationResult> {
  try {
    const response = await fetcher(
      getCheckRunInvestigationUrl(projectId, checkRunId, apiBaseUrl ?? getApiBaseUrl()),
      {
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return {
      state: "success",
      investigation: (await response.json()) as AgentInvestigation
    };
  } catch {
    return { state: "unavailable" };
  }
}

export async function requestAgentInvestigation({
  projectId,
  checkRunId,
  fetcher = sessionFetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<AgentInvestigationRequestResult> {
  try {
    const response = await fetcher(
      getCheckRunInvestigationUrl(projectId, checkRunId, apiBaseUrl ?? getApiBaseUrl()),
      {
        method: "POST",
        cache: "no-store",
        headers: {}
      }
    );

    if (response.status === 401) {
      return { state: "unauthorized" };
    }

    if (response.status === 404) {
      return { state: "not-found" };
    }

    if (response.status === 409) {
      return { state: "conflict" };
    }

    if (!response.ok) {
      return { state: "unavailable" };
    }

    return { state: "accepted" };
  } catch {
    return { state: "unavailable" };
  }
}
