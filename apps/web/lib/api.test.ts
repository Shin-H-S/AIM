import { describe, expect, it, vi } from "vitest";
import {
  fetchApiHealth,
  fetchCheckRunDetail,
  getApiBaseUrl,
  getApiHealthUrl,
  getCheckRunDetailUrl
} from "./api";

describe("getApiBaseUrl", () => {
  it("uses the local API URL by default", () => {
    expect(getApiBaseUrl("")).toBe("http://localhost:8000");
  });

  it("normalizes a configured API URL", () => {
    expect(getApiBaseUrl(" https://api.example.com/v1 ")).toBe("https://api.example.com");
  });

  it("rejects non-HTTP URLs", () => {
    expect(() => getApiBaseUrl("file:///tmp/aim")).toThrow("HTTP or HTTPS");
  });
});

describe("getApiHealthUrl", () => {
  it("builds the health endpoint URL", () => {
    expect(getApiHealthUrl("http://localhost:8000")).toBe("http://localhost:8000/health");
  });
});

describe("getCheckRunDetailUrl", () => {
  it("builds the check run detail endpoint URL", () => {
    expect(getCheckRunDetailUrl("project-id", "check-run-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id"
    );
  });
});

describe("fetchApiHealth", () => {
  it("returns an available result when the API health check succeeds", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({
        status: "ok",
        service: "aim-api"
      })
    );

    await expect(fetchApiHealth(fetcher, "http://localhost:8000")).resolves.toEqual({
      state: "available",
      status: "ok",
      service: "aim-api"
    });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/health", {
      cache: "no-store"
    });
  });

  it("returns an unavailable result when the API health check fails", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(fetchApiHealth(fetcher, "http://localhost:8000")).resolves.toEqual({
      state: "unavailable"
    });
  });

  it("returns an unavailable result when the API URL is invalid", async () => {
    const fetcher = vi.fn(async () => Response.json({ status: "ok" }));

    await expect(fetchApiHealth(fetcher, "file:///tmp/aim")).resolves.toEqual({
      state: "unavailable"
    });

    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("fetchCheckRunDetail", () => {
  it("returns a check run detail result when the API request succeeds", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({
        id: "check-run-id",
        project_id: "project-id",
        requested_by_id: "user-id",
        status: "COMPLETED",
        trigger_source: "manual",
        failure_reason: null,
        queued_at: "2026-06-26T00:00:00Z",
        started_at: "2026-06-26T00:00:01Z",
        finished_at: "2026-06-26T00:00:02Z",
        created_at: "2026-06-26T00:00:00Z",
        updated_at: "2026-06-26T00:00:02Z",
        availability_result: null,
        ssl_result: null,
        lighthouse_result: null,
        artifacts: []
      })
    );

    await expect(
      fetchCheckRunDetail({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      checkRun: {
        id: "check-run-id",
        project_id: "project-id",
        requested_by_id: "user-id",
        status: "COMPLETED",
        trigger_source: "manual",
        failure_reason: null,
        queued_at: "2026-06-26T00:00:00Z",
        started_at: "2026-06-26T00:00:01Z",
        finished_at: "2026-06-26T00:00:02Z",
        created_at: "2026-06-26T00:00:00Z",
        updated_at: "2026-06-26T00:00:02Z",
        availability_result: null,
        ssl_result: null,
        lighthouse_result: null,
        artifacts: []
      }
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("maps authentication and missing-resource responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      fetchCheckRunDetail({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      fetchCheckRunDetail({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "token",
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });
  });
});
