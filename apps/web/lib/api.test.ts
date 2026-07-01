import { describe, expect, it, vi } from "vitest";
import {
  createScenarioRun,
  downloadArtifact,
  fetchApiHealth,
  fetchCheckRuns,
  fetchCheckRunAIReport,
  fetchCheckRunDetail,
  fetchCurrentUser,
  fetchProjects,
  fetchScenarioRunDetail,
  fetchScenarios,
  getApiBaseUrl,
  getApiHealthUrl,
  getArtifactDownloadUrl,
  getCheckRunsUrl,
  getCheckRunAIReportUrl,
  getCheckRunDetailUrl,
  getCurrentUserUrl,
  getCreateScenarioRunUrl,
  getLoginUrl,
  getLogoutUrl,
  getProjectsUrl,
  getScenariosUrl,
  getScenarioRunDetailUrl,
  loginUser,
  logoutUser
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

describe("auth endpoint URL builders", () => {
  it("builds auth endpoint URLs", () => {
    expect(getLoginUrl("http://localhost:8000")).toBe("http://localhost:8000/auth/login");
    expect(getCurrentUserUrl("http://localhost:8000")).toBe("http://localhost:8000/auth/me");
    expect(getLogoutUrl("http://localhost:8000")).toBe("http://localhost:8000/auth/logout");
  });
});

describe("getProjectsUrl", () => {
  it("builds the project list endpoint URL with pagination", () => {
    expect(getProjectsUrl("http://localhost:8000", { limit: 20, offset: 5 })).toBe(
      "http://localhost:8000/projects?limit=20&offset=5"
    );
  });
});

describe("getCheckRunsUrl", () => {
  it("builds the check run list endpoint URL with pagination", () => {
    expect(getCheckRunsUrl("project-id", "http://localhost:8000", { limit: 1 })).toBe(
      "http://localhost:8000/projects/project-id/check-runs?limit=1"
    );
  });
});

describe("getCheckRunDetailUrl", () => {
  it("builds the check run detail endpoint URL", () => {
    expect(getCheckRunDetailUrl("project-id", "check-run-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id"
    );
  });
});

describe("getCheckRunAIReportUrl", () => {
  it("builds the check run AI report endpoint URL", () => {
    expect(getCheckRunAIReportUrl("project-id", "check-run-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id/ai-report"
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

describe("loginUser", () => {
  it("returns an access token when login succeeds", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({
        access_token: " access-token ",
        token_type: "bearer"
      })
    );

    await expect(
      loginUser({
        email: "user@example.com",
        password: "password",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      accessToken: "access-token",
      tokenType: "bearer"
    });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/auth/login", {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        email: "user@example.com",
        password: "password"
      })
    });
  });

  it("maps invalid credentials and unavailable login responses", async () => {
    const invalidFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const unavailableFetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(
      loginUser({
        email: "user@example.com",
        password: "wrong-password",
        fetcher: invalidFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "invalid-credentials" });

    await expect(
      loginUser({
        email: "user@example.com",
        password: "password",
        fetcher: unavailableFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unavailable" });
  });
});

describe("fetchCurrentUser", () => {
  it("returns the current user with the authenticated request", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({
        id: "user-id",
        email: "user@example.com",
        is_active: true,
        created_at: "2026-07-01T00:00:00Z",
        updated_at: "2026-07-01T00:00:00Z"
      })
    );

    await expect(
      fetchCurrentUser({
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      user: {
        id: "user-id",
        email: "user@example.com",
        is_active: true,
        created_at: "2026-07-01T00:00:00Z",
        updated_at: "2026-07-01T00:00:00Z"
      }
    });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/auth/me", {
      cache: "no-store",
      headers: {
        Authorization: "Bearer token"
      }
    });
  });

  it("maps current-user authentication and unavailable responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const unavailableFetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(
      fetchCurrentUser({
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      fetchCurrentUser({
        accessToken: "token",
        fetcher: unavailableFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unavailable" });
  });
});

describe("logoutUser", () => {
  it("logs out with the authenticated request", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 204 }));

    await expect(
      logoutUser({
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "success" });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/auth/logout", {
      method: "POST",
      cache: "no-store",
      headers: {
        Authorization: "Bearer token"
      }
    });
  });

  it("maps logout authentication and unavailable responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const unavailableFetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(
      logoutUser({
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      logoutUser({
        accessToken: "token",
        fetcher: unavailableFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unavailable" });
  });
});

describe("fetchProjects", () => {
  it("returns projects when the API request succeeds", async () => {
    const fetcher = vi.fn(async () =>
      Response.json([
        {
          id: "project-id",
          owner_id: "user-id",
          name: "AIM Website",
          service_url: "https://example.com",
          description: "Production site",
          environment: "production",
          scan_interval_minutes: 60,
          response_time_threshold_ms: 2000,
          quality_score_threshold: 80,
          is_verified: true,
          created_at: "2026-07-01T00:00:00Z",
          updated_at: "2026-07-01T00:00:00Z"
        }
      ])
    );

    await expect(
      fetchProjects({
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000",
        limit: 20
      })
    ).resolves.toEqual({
      state: "success",
      projects: [
        {
          id: "project-id",
          owner_id: "user-id",
          name: "AIM Website",
          service_url: "https://example.com",
          description: "Production site",
          environment: "production",
          scan_interval_minutes: 60,
          response_time_threshold_ms: 2000,
          quality_score_threshold: 80,
          is_verified: true,
          created_at: "2026-07-01T00:00:00Z",
          updated_at: "2026-07-01T00:00:00Z"
        }
      ]
    });
    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/projects?limit=20", {
      cache: "no-store",
      headers: {
        Authorization: "Bearer token"
      }
    });
  });

  it("maps project list authentication and unavailable responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const unavailableFetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(
      fetchProjects({
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      fetchProjects({
        accessToken: "token",
        fetcher: unavailableFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unavailable" });
  });
});

describe("fetchCheckRuns", () => {
  it("returns check runs when the API request succeeds", async () => {
    const fetcher = vi.fn(async () =>
      Response.json([
        {
          id: "check-run-id",
          project_id: "project-id",
          requested_by_id: "user-id",
          status: "FAILED",
          trigger_source: "manual",
          failure_reason: "Service returned HTTP 503.",
          queued_at: "2026-07-01T00:00:00Z",
          started_at: "2026-07-01T00:00:01Z",
          finished_at: "2026-07-01T00:00:02Z",
          created_at: "2026-07-01T00:00:00Z",
          updated_at: "2026-07-01T00:00:02Z"
        }
      ])
    );

    await expect(
      fetchCheckRuns({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000",
        limit: 1
      })
    ).resolves.toEqual({
      state: "success",
      checkRuns: [
        {
          id: "check-run-id",
          project_id: "project-id",
          requested_by_id: "user-id",
          status: "FAILED",
          trigger_source: "manual",
          failure_reason: "Service returned HTTP 503.",
          queued_at: "2026-07-01T00:00:00Z",
          started_at: "2026-07-01T00:00:01Z",
          finished_at: "2026-07-01T00:00:02Z",
          created_at: "2026-07-01T00:00:00Z",
          updated_at: "2026-07-01T00:00:02Z"
        }
      ]
    });
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/check-runs?limit=1",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("maps check run list authentication and missing-project responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      fetchCheckRuns({
        projectId: "project-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      fetchCheckRuns({
        projectId: "missing-project",
        accessToken: "token",
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });
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
        ai_report: {
          id: "ai-report-id",
          check_run_id: "check-run-id",
          summary: "This run is stable based on collected evidence.",
          overall_score: 95,
          grade: "A",
          deployment_risk: "STABLE",
          gate_reason: null,
          generated_at: "2026-06-26T00:00:03Z",
          created_at: "2026-06-26T00:00:03Z",
          updated_at: "2026-06-26T00:00:03Z"
        },
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
        ai_report: {
          id: "ai-report-id",
          check_run_id: "check-run-id",
          summary: "This run is stable based on collected evidence.",
          overall_score: 95,
          grade: "A",
          deployment_risk: "STABLE",
          gate_reason: null,
          generated_at: "2026-06-26T00:00:03Z",
          created_at: "2026-06-26T00:00:03Z",
          updated_at: "2026-06-26T00:00:03Z"
        },
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

describe("fetchCheckRunAIReport", () => {
  it("returns an AI report detail result when the API request succeeds", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({
        id: "ai-report-id",
        check_run_id: "check-run-id",
        schema_version: "2026-06-30.ai-diagnosis-report.v1",
        input_schema_version: "2026-06-29.ai-diagnosis-input.v1",
        summary: "This run is risky based on collected evidence.",
        overall_score: 55,
        grade: "D",
        deployment_risk: "RISK",
        gate_reason: "Critical scenario run failed.",
        generated_at: "2026-06-30T04:00:00Z",
        created_at: "2026-06-30T04:00:01Z",
        updated_at: "2026-06-30T04:00:02Z",
        report_json: {
          schema_version: "2026-06-30.ai-diagnosis-report.v1",
          input_schema_version: "2026-06-29.ai-diagnosis-input.v1",
          project_id: "project-id",
          check_run_id: "check-run-id",
          generated_at: "2026-06-30T04:00:00Z",
          summary: "This run is risky based on collected evidence.",
          score: {
            overall_score: 55,
            grade: "D",
            deployment_risk: "RISK",
            gate_reason: "Critical scenario run failed.",
            evidence_ids: ["score-result"]
          },
          top_issues: [
            {
              id: "functional-risk",
              priority: 1,
              title: "Critical user flow failed",
              statement_type: "confirmed_observation",
              severity: "risk",
              category: "functional_stability",
              summary: "The linked login scenario failed.",
              evidence_ids: ["scenario-run"],
              expected_user_impact: "Users may be blocked from logging in.",
              recommended_next_action: "Inspect the failed step and screenshot evidence.",
              unknown_reason: null
            }
          ],
          improved_areas: [],
          regressed_areas: [
            {
              id: "overall_score-regressed",
              category: "regression",
              summary: "Overall score regressed by 20 compared with the baseline.",
              evidence_ids: ["run-comparison"],
              metric_name: "overall_score",
              previous_value: 75,
              current_value: 55,
              delta: -20
            }
          ],
          generation_warnings: []
        }
      })
    );

    const result = await fetchCheckRunAIReport({
      projectId: "project-id",
      checkRunId: "check-run-id",
      accessToken: "token",
      fetcher,
      apiBaseUrl: "http://localhost:8000"
    });

    expect(result.state).toBe("success");
    if (result.state !== "success") {
      throw new Error("expected AI report fetch to succeed");
    }
    expect(result.report.report_json.top_issues[0].statement_type).toBe(
      "confirmed_observation"
    );
    expect(result.report.report_json.regressed_areas[0].metric_name).toBe("overall_score");
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id/ai-report",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("maps AI report authentication and missing-resource responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      fetchCheckRunAIReport({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      fetchCheckRunAIReport({
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
