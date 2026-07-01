const DEFAULT_API_BASE_URL = "http://localhost:8000";

type ApiHealthPayload = {
  status?: string;
  service?: string;
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

export type Project = {
  id: string;
  owner_id: string;
  name: string;
  service_url: string;
  description: string | null;
  environment: "development" | "staging" | "production";
  scan_interval_minutes: number;
  response_time_threshold_ms: number;
  quality_score_threshold: number;
  is_verified: boolean;
  created_at: string;
  updated_at: string;
};

export type AvailabilityResult = {
  service_url: string;
  final_url: string | null;
  is_available: boolean;
  status_code: number | null;
  response_time_ms: number | null;
  redirect_count: number;
  uses_https: boolean;
  timed_out: boolean;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type SslResult = {
  service_url: string;
  is_applicable: boolean;
  is_valid: boolean | null;
  expires_at: string | null;
  days_until_expiration: number | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type LighthouseResult = {
  service_url: string;
  is_successful: boolean;
  performance_score: number | null;
  accessibility_score: number | null;
  seo_score: number | null;
  best_practices_score: number | null;
  largest_contentful_paint_ms: number | null;
  cumulative_layout_shift: number | null;
  total_blocking_time_ms: number | null;
  raw_json_artifact_id: string | null;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type Artifact = {
  id: string;
  artifact_type: string;
  storage_backend: string;
  storage_path: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
  created_at: string;
};

export type ScoreResult = {
  availability_score: number | null;
  functional_stability_score: number | null;
  web_performance_score: number | null;
  accessibility_score: number | null;
  seo_basic_quality_score: number | null;
  regression_stability_score: number | null;
  overall_score: number;
  evaluated_weight: number;
  grade: "A" | "B" | "C" | "D" | "F";
  deployment_risk: "STABLE" | "WARNING" | "RISK";
  gate_reason: string | null;
  scoring_version: string;
  created_at: string;
  updated_at: string;
};

export type RunComparison = {
  baseline_check_run_id: string;
  comparison_type: string;
  overall_score_delta: number | null;
  availability_score_delta: number | null;
  web_performance_score_delta: number | null;
  accessibility_score_delta: number | null;
  seo_basic_quality_score_delta: number | null;
  response_time_delta_ms: number | null;
  performance_score_delta: number | null;
  deployment_risk_changed: boolean;
  summary: string;
  created_at: string;
  updated_at: string;
};

export type AIReportSummary = {
  id: string;
  check_run_id: string;
  summary: string;
  overall_score: number;
  grade: "A" | "B" | "C" | "D" | "F";
  deployment_risk: "STABLE" | "WARNING" | "RISK";
  gate_reason: string | null;
  generated_at: string;
  created_at: string;
  updated_at: string;
};

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

export type CheckRunDetail = {
  id: string;
  project_id: string;
  requested_by_id: string;
  status: CheckRunStatus;
  trigger_source: string;
  failure_reason: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
  availability_result: AvailabilityResult | null;
  ssl_result: SslResult | null;
  lighthouse_result: LighthouseResult | null;
  score_result: ScoreResult | null;
  comparison_result: RunComparison | null;
  ai_report: AIReportSummary | null;
  artifacts: Artifact[];
  linked_scenario_runs: ScenarioRun[];
};

export type CheckRunSummary = {
  id: string;
  project_id: string;
  requested_by_id: string;
  status: CheckRunStatus;
  trigger_source: string;
  failure_reason: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type StepResult = {
  id: string;
  scenario_run_id: string;
  test_step_id: string | null;
  step_order: number;
  action: TestStepAction;
  target: string | null;
  status: StepResultStatus;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error_message: string | null;
  failure_screenshot_artifact_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ConsoleError = {
  id: string;
  scenario_run_id: string;
  level: string;
  message: string;
  source_url: string | null;
  line_number: number | null;
  column_number: number | null;
  created_at: string;
};

export type NetworkFailure = {
  id: string;
  scenario_run_id: string;
  request_url: string;
  method: string;
  resource_type: string | null;
  failure_text: string | null;
  created_at: string;
};

export type TestStep = {
  id: string;
  scenario_id: string;
  step_order: number;
  action: TestStepAction;
  target: string | null;
  value: string | null;
  timeout_ms: number | null;
  is_critical: boolean;
  created_at: string;
  updated_at: string;
};

export type TestScenario = {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  steps: TestStep[];
};

export type ScenarioRun = {
  id: string;
  project_id: string;
  scenario_id: string;
  check_run_id: string | null;
  requested_by_id: string;
  status: ScenarioRunStatus;
  trigger_source: string;
  failure_reason: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
};

export type ScenarioRunDetail = {
  id: string;
  project_id: string;
  scenario_id: string;
  check_run_id: string | null;
  requested_by_id: string;
  status: ScenarioRunStatus;
  trigger_source: string;
  failure_reason: string | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  created_at: string;
  updated_at: string;
  step_results: StepResult[];
  console_errors: ConsoleError[];
  network_failures: NetworkFailure[];
};

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

export async function fetchProjects({
  accessToken,
  fetcher = fetch,
  apiBaseUrl,
  limit,
  offset
}: {
  accessToken: string;
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
        headers: {
          Authorization: `Bearer ${accessToken}`
        }
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

export async function fetchCheckRuns({
  projectId,
  accessToken,
  fetcher = fetch,
  apiBaseUrl,
  limit,
  offset
}: {
  projectId: string;
  accessToken: string;
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
        headers: {
          Authorization: `Bearer ${accessToken}`
        }
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

export async function downloadArtifact({
  artifactId,
  accessToken,
  fetcher = fetch,
  apiBaseUrl
}: {
  artifactId: string;
  accessToken: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ArtifactDownloadResult> {
  try {
    const response = await fetcher(
      getArtifactDownloadUrl(artifactId, apiBaseUrl ?? getApiBaseUrl()),
      {
        cache: "no-store",
        headers: {
          Authorization: `Bearer ${accessToken}`
        }
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
  accessToken,
  fetcher = fetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  accessToken: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<CheckRunDetailResult> {
  try {
    const response = await fetcher(
      getCheckRunDetailUrl(projectId, checkRunId, apiBaseUrl ?? getApiBaseUrl()),
      {
        cache: "no-store",
        headers: {
          Authorization: `Bearer ${accessToken}`
        }
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
  accessToken,
  fetcher = fetch,
  apiBaseUrl
}: {
  projectId: string;
  checkRunId: string;
  accessToken: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<AIReportDetailResult> {
  try {
    const response = await fetcher(
      getCheckRunAIReportUrl(projectId, checkRunId, apiBaseUrl ?? getApiBaseUrl()),
      {
        cache: "no-store",
        headers: {
          Authorization: `Bearer ${accessToken}`
        }
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

export async function fetchScenarioRunDetail({
  projectId,
  scenarioId,
  scenarioRunId,
  accessToken,
  fetcher = fetch,
  apiBaseUrl
}: {
  projectId: string;
  scenarioId: string;
  scenarioRunId: string;
  accessToken: string;
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
        headers: {
          Authorization: `Bearer ${accessToken}`
        }
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

export async function fetchScenarios({
  projectId,
  accessToken,
  fetcher = fetch,
  apiBaseUrl
}: {
  projectId: string;
  accessToken: string;
  fetcher?: typeof fetch;
  apiBaseUrl?: string;
}): Promise<ScenarioListResult> {
  try {
    const response = await fetcher(getScenariosUrl(projectId, apiBaseUrl ?? getApiBaseUrl()), {
      cache: "no-store",
      headers: {
        Authorization: `Bearer ${accessToken}`
      }
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

export async function createScenarioRun({
  projectId,
  scenarioId,
  accessToken,
  fetcher = fetch,
  apiBaseUrl
}: {
  projectId: string;
  scenarioId: string;
  accessToken: string;
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
          Authorization: `Bearer ${accessToken}`,
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
