const DEFAULT_API_BASE_URL = "http://localhost:8000";

type ApiHealthPayload = {
  status?: string;
  service?: string;
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
