import { describe, expect, it, vi } from "vitest";
import {
  createScenarioRun,
  downloadArtifact,
  fetchApiHealth,
  fetchCheckRunDetail,
  fetchScenarioRunDetail,
  fetchScenarios,
  getApiBaseUrl,
  getApiHealthUrl,
  getArtifactDownloadUrl,
  getCheckRunDetailUrl,
  getCreateScenarioRunUrl,
  getScenariosUrl,
  getScenarioRunDetailUrl
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

describe("getScenarioRunDetailUrl", () => {
  it("builds the scenario run detail endpoint URL", () => {
    expect(
      getScenarioRunDetailUrl(
        "project-id",
        "scenario-id",
        "scenario-run-id",
        "http://localhost:8000"
      )
    ).toBe(
      "http://localhost:8000/projects/project-id/scenarios/scenario-id/runs/scenario-run-id"
    );
  });
});

describe("getScenariosUrl", () => {
  it("builds the scenario list endpoint URL", () => {
    expect(getScenariosUrl("project-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/scenarios"
    );
  });
});

describe("getCreateScenarioRunUrl", () => {
  it("builds the scenario run creation endpoint URL", () => {
    expect(getCreateScenarioRunUrl("project-id", "scenario-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/scenarios/scenario-id/runs"
    );
  });
});

describe("getArtifactDownloadUrl", () => {
  it("builds the artifact download endpoint URL", () => {
    expect(getArtifactDownloadUrl("artifact-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/artifacts/artifact-id/download"
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

describe("downloadArtifact", () => {
  it("downloads an artifact blob with the authenticated request", async () => {
    const fetcher = vi.fn(
      async () =>
        new Response("artifact-body", {
          status: 200,
          headers: {
            "content-disposition": 'attachment; filename="lighthouse.json"',
            "content-type": "application/json"
          }
        })
    );

    const result = await downloadArtifact({
      artifactId: "artifact-id",
      accessToken: "token",
      fetcher,
      apiBaseUrl: "http://localhost:8000"
    });

    expect(result.state).toBe("success");
    if (result.state !== "success") {
      throw new Error("expected artifact download to succeed");
    }
    await expect(result.blob.text()).resolves.toBe("artifact-body");
    expect(result.filename).toBe("lighthouse.json");
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/artifacts/artifact-id/download",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("falls back to an artifact based filename", async () => {
    const fetcher = vi.fn(async () => new Response("artifact-body", { status: 200 }));

    const result = await downloadArtifact({
      artifactId: "artifact-id",
      accessToken: "token",
      fetcher,
      apiBaseUrl: "http://localhost:8000"
    });

    expect(result.state).toBe("success");
    if (result.state !== "success") {
      throw new Error("expected artifact download to succeed");
    }
    expect(result.filename).toBe("artifact-artifact-id");
  });

  it("maps artifact download error responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));
    const conflictFetcher = vi.fn(async () => new Response(null, { status: 409 }));

    await expect(
      downloadArtifact({
        artifactId: "artifact-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      downloadArtifact({
        artifactId: "missing-id",
        accessToken: "token",
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });

    await expect(
      downloadArtifact({
        artifactId: "remote-id",
        accessToken: "token",
        fetcher: conflictFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "conflict" });
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
        score_result: null,
        comparison_result: null,
        artifacts: [],
        linked_scenario_runs: [
          {
            id: "scenario-run-id",
            project_id: "project-id",
            scenario_id: "scenario-id",
            check_run_id: "check-run-id",
            requested_by_id: "user-id",
            status: "QUEUED",
            trigger_source: "check_run",
            failure_reason: null,
            queued_at: "2026-06-26T00:00:00Z",
            started_at: null,
            finished_at: null,
            duration_ms: null,
            created_at: "2026-06-26T00:00:00Z",
            updated_at: "2026-06-26T00:00:00Z"
          }
        ]
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
        score_result: null,
        comparison_result: null,
        artifacts: [],
        linked_scenario_runs: [
          {
            id: "scenario-run-id",
            project_id: "project-id",
            scenario_id: "scenario-id",
            check_run_id: "check-run-id",
            requested_by_id: "user-id",
            status: "QUEUED",
            trigger_source: "check_run",
            failure_reason: null,
            queued_at: "2026-06-26T00:00:00Z",
            started_at: null,
            finished_at: null,
            duration_ms: null,
            created_at: "2026-06-26T00:00:00Z",
            updated_at: "2026-06-26T00:00:00Z"
          }
        ]
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

describe("fetchScenarioRunDetail", () => {
  it("returns a scenario run detail result when the API request succeeds", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({
        id: "scenario-run-id",
        project_id: "project-id",
        scenario_id: "scenario-id",
        check_run_id: null,
        requested_by_id: "user-id",
        status: "FAILED",
        trigger_source: "manual",
        failure_reason: "Expected element was not found.",
        queued_at: "2026-06-28T00:00:00Z",
        started_at: "2026-06-28T00:00:01Z",
        finished_at: "2026-06-28T00:00:02Z",
        duration_ms: 1000,
        created_at: "2026-06-28T00:00:00Z",
        updated_at: "2026-06-28T00:00:02Z",
        step_results: [
          {
            id: "step-result-id",
            scenario_run_id: "scenario-run-id",
            test_step_id: "step-id",
            step_order: 1,
            action: "assert_element_exists",
            target: "#dashboard",
            status: "FAILED",
            started_at: "2026-06-28T00:00:01Z",
            finished_at: "2026-06-28T00:00:02Z",
            duration_ms: 1000,
            error_message: "Expected element was not found.",
            failure_screenshot_artifact_id: "artifact-id",
            created_at: "2026-06-28T00:00:02Z",
            updated_at: "2026-06-28T00:00:02Z"
          }
        ],
        console_errors: [],
        network_failures: []
      })
    );

    await expect(
      fetchScenarioRunDetail({
        projectId: "project-id",
        scenarioId: "scenario-id",
        scenarioRunId: "scenario-run-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      scenarioRun: {
        id: "scenario-run-id",
        project_id: "project-id",
        scenario_id: "scenario-id",
        check_run_id: null,
        requested_by_id: "user-id",
        status: "FAILED",
        trigger_source: "manual",
        failure_reason: "Expected element was not found.",
        queued_at: "2026-06-28T00:00:00Z",
        started_at: "2026-06-28T00:00:01Z",
        finished_at: "2026-06-28T00:00:02Z",
        duration_ms: 1000,
        created_at: "2026-06-28T00:00:00Z",
        updated_at: "2026-06-28T00:00:02Z",
        step_results: [
          {
            id: "step-result-id",
            scenario_run_id: "scenario-run-id",
            test_step_id: "step-id",
            step_order: 1,
            action: "assert_element_exists",
            target: "#dashboard",
            status: "FAILED",
            started_at: "2026-06-28T00:00:01Z",
            finished_at: "2026-06-28T00:00:02Z",
            duration_ms: 1000,
            error_message: "Expected element was not found.",
            failure_screenshot_artifact_id: "artifact-id",
            created_at: "2026-06-28T00:00:02Z",
            updated_at: "2026-06-28T00:00:02Z"
          }
        ],
        console_errors: [],
        network_failures: []
      }
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/scenarios/scenario-id/runs/scenario-run-id",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("maps scenario run authentication and missing-resource responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      fetchScenarioRunDetail({
        projectId: "project-id",
        scenarioId: "scenario-id",
        scenarioRunId: "scenario-run-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      fetchScenarioRunDetail({
        projectId: "project-id",
        scenarioId: "scenario-id",
        scenarioRunId: "scenario-run-id",
        accessToken: "token",
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });
  });
});

describe("fetchScenarios", () => {
  it("returns scenarios when the API request succeeds", async () => {
    const fetcher = vi.fn(async () =>
      Response.json([
        {
          id: "scenario-id",
          project_id: "project-id",
          name: "Login flow",
          description: "Critical flow",
          is_active: true,
          created_at: "2026-06-29T00:00:00Z",
          updated_at: "2026-06-29T00:00:00Z",
          steps: [
            {
              id: "step-id",
              scenario_id: "scenario-id",
              step_order: 1,
              action: "navigate",
              target: "https://example.com/login",
              value: null,
              timeout_ms: null,
              is_critical: true,
              created_at: "2026-06-29T00:00:00Z",
              updated_at: "2026-06-29T00:00:00Z"
            }
          ]
        }
      ])
    );

    await expect(
      fetchScenarios({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      scenarios: [
        {
          id: "scenario-id",
          project_id: "project-id",
          name: "Login flow",
          description: "Critical flow",
          is_active: true,
          created_at: "2026-06-29T00:00:00Z",
          updated_at: "2026-06-29T00:00:00Z",
          steps: [
            {
              id: "step-id",
              scenario_id: "scenario-id",
              step_order: 1,
              action: "navigate",
              target: "https://example.com/login",
              value: null,
              timeout_ms: null,
              is_critical: true,
              created_at: "2026-06-29T00:00:00Z",
              updated_at: "2026-06-29T00:00:00Z"
            }
          ]
        }
      ]
    });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/projects/project-id/scenarios", {
      cache: "no-store",
      headers: {
        Authorization: "Bearer token"
      }
    });
  });
});

describe("createScenarioRun", () => {
  it("creates a scenario run when the API request succeeds", async () => {
    const fetcher = vi.fn(async () =>
      Response.json(
        {
          id: "scenario-run-id",
          project_id: "project-id",
          scenario_id: "scenario-id",
          check_run_id: null,
          requested_by_id: "user-id",
          status: "QUEUED",
          trigger_source: "manual",
          failure_reason: null,
          queued_at: "2026-06-29T00:00:00Z",
          started_at: null,
          finished_at: null,
          duration_ms: null,
          created_at: "2026-06-29T00:00:00Z",
          updated_at: "2026-06-29T00:00:00Z"
        },
        { status: 201 }
      )
    );

    await expect(
      createScenarioRun({
        projectId: "project-id",
        scenarioId: "scenario-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      scenarioRun: {
        id: "scenario-run-id",
        project_id: "project-id",
        scenario_id: "scenario-id",
        check_run_id: null,
        requested_by_id: "user-id",
        status: "QUEUED",
        trigger_source: "manual",
        failure_reason: null,
        queued_at: "2026-06-29T00:00:00Z",
        started_at: null,
        finished_at: null,
        duration_ms: null,
        created_at: "2026-06-29T00:00:00Z",
        updated_at: "2026-06-29T00:00:00Z"
      }
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/scenarios/scenario-id/runs",
      {
        method: "POST",
        cache: "no-store",
        headers: {
          Authorization: "Bearer token",
          "Content-Type": "application/json"
        },
        body: "{}"
      }
    );
  });

  it("maps inactive scenario responses to conflict", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 409 }));

    await expect(
      createScenarioRun({
        projectId: "project-id",
        scenarioId: "scenario-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "conflict" });
  });
});
