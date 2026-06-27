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
  artifacts: Artifact[];
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
