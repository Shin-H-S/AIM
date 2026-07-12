import { describe, expect, it, vi } from "vitest";
import {
  cancelCheckRun,
  clearProjectBaseline,
  confirmPasswordReset,
  createCheckRun,
  createProject,
  createScenario,
  createScenarioRun,
  deleteProject,
  deleteScenario,
  downloadArtifact,
  fetchApiHealth,
  fetchBaselineComparison,
  fetchCheckRuns,
  fetchCheckRunAIReport,
  fetchCheckRunDetail,
  fetchCurrentUser,
  fetchProjectAlerts,
  fetchProject,
  fetchProjectIncidents,
  fetchProjectVerification,
  fetchProjects,
  fetchScenarioRuns,
  fetchScenarioRunDetail,
  fetchScenarios,
  getApiBaseUrl,
  getApiHealthUrl,
  getArtifactDownloadUrl,
  getBaselineComparisonUrl,
  getCancelCheckRunUrl,
  getCheckRunsUrl,
  getCheckRunAIReportUrl,
  getCheckRunDetailUrl,
  getCurrentUserUrl,
  getCreateScenarioRunUrl,
  getLoginUrl,
  getLogoutUrl,
  getProjectAlertsUrl,
  getProjectBaselineUrl,
  getProjectDetailUrl,
  getProjectIncidentsUrl,
  getProjectVerificationUrl,
  getProjectVerifyUrl,
  getProjectsUrl,
  getRetryAlertUrl,
  getScenarioUrl,
  getScenarioRunsUrl,
  getScenariosUrl,
  getScenarioRunDetailUrl,
  getSignupUrl,
  loginUser,
  logoutUser,
  requestPasswordReset,
  retryAlert,
  setProjectBaseline,
  signupUser,
  updateScenario,
  updateProject,
  verifyProjectDomain
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
    expect(getSignupUrl("http://localhost:8000")).toBe("http://localhost:8000/auth/signup");
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

describe("project endpoint URL builders", () => {
  it("builds project detail and verification endpoint URLs", () => {
    expect(getProjectDetailUrl("project-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id"
    );
    expect(getProjectVerificationUrl("project-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/verification"
    );
    expect(getProjectVerifyUrl("project-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/verify"
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

describe("alert endpoint URL builders", () => {
  it("builds incident and alert list endpoint URLs with pagination", () => {
    expect(getProjectIncidentsUrl("project-id", "http://localhost:8000", { limit: 10 })).toBe(
      "http://localhost:8000/projects/project-id/incidents?limit=10"
    );
    expect(
      getProjectAlertsUrl("project-id", "http://localhost:8000", { limit: 10, offset: 20 })
    ).toBe("http://localhost:8000/projects/project-id/alerts?limit=10&offset=20");
    expect(getRetryAlertUrl("project-id", "alert-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/alerts/alert-id/retry"
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
      getScenarioRunsUrl("project-id", "scenario-id", "http://localhost:8000", {
        limit: 10,
        offset: 20
      })
    ).toBe("http://localhost:8000/projects/project-id/scenarios/scenario-id/runs?limit=10&offset=20");
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

describe("getScenarioUrl", () => {
  it("builds the scenario detail endpoint URL", () => {
    expect(getScenarioUrl("project-id", "scenario-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/scenarios/scenario-id"
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

describe("requestPasswordReset", () => {
  it("posts the email and returns accepted", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 202 }));

    await expect(
      requestPasswordReset({
        email: "user@example.com",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "accepted" });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/auth/password-reset/request", {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ email: "user@example.com" })
    });
  });

  it("maps failures to unavailable", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(
      requestPasswordReset({
        email: "user@example.com",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unavailable" });
  });
});

describe("confirmPasswordReset", () => {
  it("posts the token with the new password", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 204 }));

    await expect(
      confirmPasswordReset({
        token: "reset-token",
        newPassword: "new password 456",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "success" });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/auth/password-reset/confirm", {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ token: "reset-token", new_password: "new password 456" })
    });
  });

  it("maps invalid tokens and unavailable responses", async () => {
    const invalidFetcher = vi.fn(async () => new Response(null, { status: 400 }));
    const unavailableFetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(
      confirmPasswordReset({
        token: "expired",
        newPassword: "new password 456",
        fetcher: invalidFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "invalid-token" });

    await expect(
      confirmPasswordReset({
        token: "reset-token",
        newPassword: "new password 456",
        fetcher: unavailableFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unavailable" });
  });
});

describe("signupUser", () => {
  it("creates a user account", async () => {
    const fetcher = vi.fn(async () =>
      Response.json(
        {
          id: "user-id",
          email: "user@example.com",
          is_active: true,
          created_at: "2026-07-02T00:00:00Z",
          updated_at: "2026-07-02T00:00:00Z"
        },
        { status: 201 }
      )
    );

    await expect(
      signupUser({
        payload: {
          email: "user@example.com",
          password: "password123"
        },
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      user: {
        id: "user-id",
        email: "user@example.com",
        is_active: true,
        created_at: "2026-07-02T00:00:00Z",
        updated_at: "2026-07-02T00:00:00Z"
      }
    });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/auth/signup", {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        email: "user@example.com",
        password: "password123"
      })
    });
  });

  it("maps signup error responses", async () => {
    const invalidFetcher = vi.fn(async () => new Response(null, { status: 422 }));
    const conflictFetcher = vi.fn(async () => new Response(null, { status: 409 }));
    const unavailableFetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(
      signupUser({
        payload: {
          email: "bad-email",
          password: "short"
        },
        fetcher: invalidFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "invalid" });

    await expect(
      signupUser({
        payload: {
          email: "user@example.com",
          password: "password123"
        },
        fetcher: conflictFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "email-already-registered" });

    await expect(
      signupUser({
        payload: {
          email: "user@example.com",
          password: "password123"
        },
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

describe("fetchProject", () => {
  it("returns a project detail when the API request succeeds", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({
        id: "project-id",
        owner_id: "user-id",
        name: "AIM Website",
        service_url: "https://example.com",
        description: null,
        environment: "production",
        scan_interval_minutes: 60,
        response_time_threshold_ms: 2000,
        quality_score_threshold: 80,
        is_verified: false,
        created_at: "2026-07-01T00:00:00Z",
        updated_at: "2026-07-01T00:00:00Z"
      })
    );

    await expect(
      fetchProject({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      project: {
        id: "project-id",
        owner_id: "user-id",
        name: "AIM Website",
        service_url: "https://example.com",
        description: null,
        environment: "production",
        scan_interval_minutes: 60,
        response_time_threshold_ms: 2000,
        quality_score_threshold: 80,
        is_verified: false,
        created_at: "2026-07-01T00:00:00Z",
        updated_at: "2026-07-01T00:00:00Z"
      }
    });
    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/projects/project-id", {
      cache: "no-store",
      headers: {
        Authorization: "Bearer token"
      }
    });
  });

  it("maps project detail authentication and missing-resource responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      fetchProject({
        projectId: "project-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      fetchProject({
        projectId: "missing-project",
        accessToken: "token",
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });
  });
});

describe("createProject", () => {
  it("creates a project with an authenticated request", async () => {
    const payload = {
      name: "AIM Website",
      service_url: "https://example.com",
      description: "Production site",
      environment: "production" as const,
      scan_interval_minutes: 60,
      response_time_threshold_ms: 2000,
      quality_score_threshold: 80
    };
    const fetcher = vi.fn(async () =>
      Response.json(
        {
          id: "project-id",
          owner_id: "user-id",
          ...payload,
          is_verified: false,
          created_at: "2026-07-01T00:00:00Z",
          updated_at: "2026-07-01T00:00:00Z"
        },
        { status: 201 }
      )
    );

    await expect(
      createProject({
        accessToken: "token",
        payload,
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      project: {
        id: "project-id",
        owner_id: "user-id",
        ...payload,
        is_verified: false,
        created_at: "2026-07-01T00:00:00Z",
        updated_at: "2026-07-01T00:00:00Z"
      }
    });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/projects", {
      method: "POST",
      cache: "no-store",
      headers: {
        Authorization: "Bearer token",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
  });

  it("maps invalid project create responses", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 422 }));

    await expect(
      createProject({
        accessToken: "token",
        payload: {
          name: "AIM Website",
          service_url: "http://localhost",
          description: null,
          environment: "development",
          scan_interval_minutes: 60,
          response_time_threshold_ms: 2000,
          quality_score_threshold: 80
        },
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "invalid" });
  });
});

describe("updateProject", () => {
  it("updates a project with an authenticated request", async () => {
    const payload = {
      name: "AIM Staging",
      service_url: "https://staging.example.com",
      description: null,
      environment: "staging" as const,
      scan_interval_minutes: 30,
      response_time_threshold_ms: 1500,
      quality_score_threshold: 85
    };
    const fetcher = vi.fn(async () =>
      Response.json({
        id: "project-id",
        owner_id: "user-id",
        ...payload,
        is_verified: false,
        created_at: "2026-07-01T00:00:00Z",
        updated_at: "2026-07-01T00:10:00Z"
      })
    );

    await expect(
      updateProject({
        projectId: "project-id",
        accessToken: "token",
        payload,
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      project: {
        id: "project-id",
        owner_id: "user-id",
        ...payload,
        is_verified: false,
        created_at: "2026-07-01T00:00:00Z",
        updated_at: "2026-07-01T00:10:00Z"
      }
    });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/projects/project-id", {
      method: "PATCH",
      cache: "no-store",
      headers: {
        Authorization: "Bearer token",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
  });

  it("maps missing project update responses", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      updateProject({
        projectId: "missing-project",
        accessToken: "token",
        payload: {
          name: "AIM Website",
          service_url: "https://example.com",
          description: null,
          environment: "development",
          scan_interval_minutes: 60,
          response_time_threshold_ms: 2000,
          quality_score_threshold: 80
        },
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });
  });
});

describe("project domain verification", () => {
  it("fetches project verification instructions", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({
        project_id: "project-id",
        verification_token: "aim_verify_token",
        meta_tag: '<meta name="aim-verification" content="aim_verify_token">',
        is_verified: false,
        verified_at: null
      })
    );

    await expect(
      fetchProjectVerification({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      verification: {
        project_id: "project-id",
        verification_token: "aim_verify_token",
        meta_tag: '<meta name="aim-verification" content="aim_verify_token">',
        is_verified: false,
        verified_at: null
      }
    });
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/verification",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("verifies a project domain", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({
        project_id: "project-id",
        verification_token: "aim_verify_token",
        meta_tag: '<meta name="aim-verification" content="aim_verify_token">',
        is_verified: true,
        verified_at: "2026-07-01T00:00:00Z",
        status: "verified"
      })
    );

    await expect(
      verifyProjectDomain({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      verification: {
        project_id: "project-id",
        verification_token: "aim_verify_token",
        meta_tag: '<meta name="aim-verification" content="aim_verify_token">',
        is_verified: true,
        verified_at: "2026-07-01T00:00:00Z"
      },
      status: "verified"
    });
    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/projects/project-id/verify", {
      method: "POST",
      cache: "no-store",
      headers: {
        Authorization: "Bearer token"
      }
    });
  });

  it("maps failed verification responses", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 400 }));

    await expect(
      verifyProjectDomain({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "verification-failed" });
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

describe("fetchProjectIncidents", () => {
  it("returns incidents when the API request succeeds", async () => {
    const incident = {
      id: "incident-id",
      project_id: "project-id",
      opened_check_run_id: "check-run-id",
      resolved_check_run_id: null,
      trigger_type: "SERVICE_CONNECTION_FAILURE",
      severity: "RISK",
      status: "OPEN",
      title: "Service connection failed",
      summary: "The service could not be reached.",
      evidence_json: {
        failure_reason: "connection refused"
      },
      started_at: "2026-07-03T00:00:00Z",
      resolved_at: null,
      created_at: "2026-07-03T00:00:00Z",
      updated_at: "2026-07-03T00:00:00Z"
    };
    const fetcher = vi.fn(async () => Response.json([incident]));

    await expect(
      fetchProjectIncidents({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000",
        limit: 5
      })
    ).resolves.toEqual({
      state: "success",
      incidents: [incident]
    });
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/incidents?limit=5",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("maps incident list authentication and missing-project responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      fetchProjectIncidents({
        projectId: "project-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      fetchProjectIncidents({
        projectId: "missing-project",
        accessToken: "token",
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });
  });
});

describe("fetchProjectAlerts", () => {
  it("returns alerts when the API request succeeds", async () => {
    const alert = {
      id: "alert-id",
      project_id: "project-id",
      incident_id: "incident-id",
      check_run_id: "check-run-id",
      alert_type: "INCIDENT_OPENED",
      trigger_type: "SERVICE_CONNECTION_FAILURE",
      channel: "EMAIL",
      status: "PENDING",
      recipient_email: "owner@example.com",
      subject: "[AIM] AIM Website: Service connection failed",
      body: "Project: AIM Website",
      delivery_attempts: 0,
      last_error: null,
      sent_at: null,
      created_at: "2026-07-03T00:00:00Z",
      updated_at: "2026-07-03T00:00:00Z"
    };
    const fetcher = vi.fn(async () => Response.json([alert]));

    await expect(
      fetchProjectAlerts({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000",
        limit: 5,
        offset: 10
      })
    ).resolves.toEqual({
      state: "success",
      alerts: [alert]
    });
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/alerts?limit=5&offset=10",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("maps alert list authentication and missing-project responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      fetchProjectAlerts({
        projectId: "project-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      fetchProjectAlerts({
        projectId: "missing-project",
        accessToken: "token",
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });
  });
});

describe("retryAlert", () => {
  it("retries a failed alert with an authenticated request", async () => {
    const alert = {
      id: "alert-id",
      project_id: "project-id",
      incident_id: "incident-id",
      check_run_id: "check-run-id",
      alert_type: "INCIDENT_OPENED",
      trigger_type: "SERVICE_CONNECTION_FAILURE",
      channel: "EMAIL",
      status: "PENDING",
      recipient_email: "owner@example.com",
      subject: "[AIM] AIM Website: Service connection failed",
      body: "Project: AIM Website",
      delivery_attempts: 1,
      last_error: null,
      sent_at: null,
      created_at: "2026-07-03T00:00:00Z",
      updated_at: "2026-07-03T00:00:00Z"
    };
    const fetcher = vi.fn(async () => Response.json(alert));

    await expect(
      retryAlert({
        projectId: "project-id",
        alertId: "alert-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      alert
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/alerts/alert-id/retry",
      {
        method: "POST",
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("maps retry alert error responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));
    const conflictFetcher = vi.fn(async () => new Response(null, { status: 409 }));
    const unavailableFetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(
      retryAlert({
        projectId: "project-id",
        alertId: "alert-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      retryAlert({
        projectId: "missing-project",
        alertId: "alert-id",
        accessToken: "token",
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });

    await expect(
      retryAlert({
        projectId: "project-id",
        alertId: "pending-alert",
        accessToken: "token",
        fetcher: conflictFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "conflict" });

    await expect(
      retryAlert({
        projectId: "project-id",
        alertId: "alert-id",
        accessToken: "token",
        fetcher: unavailableFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unavailable" });
  });
});

describe("createCheckRun", () => {
  it("creates a check run with an authenticated request", async () => {
    const fetcher = vi.fn(async () =>
      Response.json(
        {
          id: "check-run-id",
          project_id: "project-id",
          requested_by_id: "user-id",
          status: "QUEUED",
          trigger_source: "manual",
          failure_reason: null,
          queued_at: "2026-07-02T00:00:00Z",
          started_at: null,
          finished_at: null,
          created_at: "2026-07-02T00:00:00Z",
          updated_at: "2026-07-02T00:00:00Z"
        },
        { status: 201 }
      )
    );

    await expect(
      createCheckRun({
        projectId: "project-id",
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
        status: "QUEUED",
        trigger_source: "manual",
        failure_reason: null,
        queued_at: "2026-07-02T00:00:00Z",
        started_at: null,
        finished_at: null,
        created_at: "2026-07-02T00:00:00Z",
        updated_at: "2026-07-02T00:00:00Z"
      }
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/check-runs",
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

  it("maps check run creation error responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));
    const conflictFetcher = vi.fn(async () => new Response(null, { status: 409 }));
    const unavailableFetcher = vi.fn(async () => new Response(null, { status: 503 }));

    await expect(
      createCheckRun({
        projectId: "project-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      createCheckRun({
        projectId: "missing-project",
        accessToken: "token",
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });

    await expect(
      createCheckRun({
        projectId: "unverified-project",
        accessToken: "token",
        fetcher: conflictFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "conflict" });

    await expect(
      createCheckRun({
        projectId: "project-id",
        accessToken: "token",
        fetcher: unavailableFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unavailable" });
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

describe("fetchScenarioRuns", () => {
  it("returns scenario runs when the API request succeeds", async () => {
    const scenarioRun = {
      id: "scenario-run-id",
      project_id: "project-id",
      scenario_id: "scenario-id",
      check_run_id: null,
      requested_by_id: "user-id",
      status: "COMPLETED",
      trigger_source: "manual",
      failure_reason: null,
      queued_at: "2026-06-28T00:00:00Z",
      started_at: "2026-06-28T00:00:01Z",
      finished_at: "2026-06-28T00:00:02Z",
      duration_ms: 1000,
      created_at: "2026-06-28T00:00:00Z",
      updated_at: "2026-06-28T00:00:02Z"
    };
    const fetcher = vi.fn(async () => Response.json([scenarioRun]));

    await expect(
      fetchScenarioRuns({
        projectId: "project-id",
        scenarioId: "scenario-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000",
        limit: 5,
        offset: 10
      })
    ).resolves.toEqual({
      state: "success",
      scenarioRuns: [scenarioRun]
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/scenarios/scenario-id/runs?limit=5&offset=10",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("maps scenario run list authentication and missing-resource responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      fetchScenarioRuns({
        projectId: "project-id",
        scenarioId: "scenario-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      fetchScenarioRuns({
        projectId: "project-id",
        scenarioId: "missing-scenario",
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

describe("createScenario", () => {
  it("creates a scenario with ordered steps", async () => {
    const fetcher = vi.fn(async () =>
      Response.json(
        {
          id: "scenario-id",
          project_id: "project-id",
          name: "Login flow",
          description: "Critical login flow",
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
        },
        { status: 201 }
      )
    );

    const payload = {
      name: "Login flow",
      description: "Critical login flow",
      is_active: true,
      steps: [
        {
          action: "navigate" as const,
          target: "https://example.com/login",
          value: null,
          timeout_ms: null,
          is_critical: true
        }
      ]
    };

    await expect(
      createScenario({
        projectId: "project-id",
        accessToken: "token",
        payload,
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      scenario: {
        id: "scenario-id",
        project_id: "project-id",
        name: "Login flow",
        description: "Critical login flow",
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
    });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/projects/project-id/scenarios", {
      method: "POST",
      cache: "no-store",
      headers: {
        Authorization: "Bearer token",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });
  });

  it("maps scenario creation error responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));
    const invalidFetcher = vi.fn(async () => new Response(null, { status: 422 }));
    const unavailableFetcher = vi.fn(async () => new Response(null, { status: 503 }));
    const payload = {
      name: "Login flow",
      description: null,
      is_active: true,
      steps: [
        {
          action: "navigate" as const,
          target: "https://example.com/login",
          value: null,
          timeout_ms: null,
          is_critical: true
        }
      ]
    };

    await expect(
      createScenario({
        projectId: "project-id",
        accessToken: "bad-token",
        payload,
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      createScenario({
        projectId: "missing-project",
        accessToken: "token",
        payload,
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });

    await expect(
      createScenario({
        projectId: "project-id",
        accessToken: "token",
        payload,
        fetcher: invalidFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "invalid" });

    await expect(
      createScenario({
        projectId: "project-id",
        accessToken: "token",
        payload,
        fetcher: unavailableFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unavailable" });
  });
});

describe("updateScenario", () => {
  it("updates a scenario with ordered replacement steps", async () => {
    const fetcher = vi.fn(async () =>
      Response.json({
        id: "scenario-id",
        project_id: "project-id",
        name: "Updated login flow",
        description: null,
        is_active: false,
        created_at: "2026-06-29T00:00:00Z",
        updated_at: "2026-07-03T00:00:00Z",
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
            updated_at: "2026-07-03T00:00:00Z"
          }
        ]
      })
    );
    const payload = {
      name: "Updated login flow",
      description: null,
      is_active: false,
      steps: [
        {
          action: "navigate" as const,
          target: "https://example.com/login",
          value: null,
          timeout_ms: null,
          is_critical: true
        }
      ]
    };

    await expect(
      updateScenario({
        projectId: "project-id",
        scenarioId: "scenario-id",
        accessToken: "token",
        payload,
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      scenario: {
        id: "scenario-id",
        project_id: "project-id",
        name: "Updated login flow",
        description: null,
        is_active: false,
        created_at: "2026-06-29T00:00:00Z",
        updated_at: "2026-07-03T00:00:00Z",
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
            updated_at: "2026-07-03T00:00:00Z"
          }
        ]
      }
    });
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/scenarios/scenario-id",
      {
        method: "PATCH",
        cache: "no-store",
        headers: {
          Authorization: "Bearer token",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      }
    );
  });

  it("maps scenario update error responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));
    const invalidFetcher = vi.fn(async () => new Response(null, { status: 422 }));
    const unavailableFetcher = vi.fn(async () => new Response(null, { status: 503 }));
    const payload = {
      name: "Login flow",
      description: null,
      is_active: true,
      steps: [
        {
          action: "navigate" as const,
          target: "https://example.com/login",
          value: null,
          timeout_ms: null,
          is_critical: true
        }
      ]
    };

    await expect(
      updateScenario({
        projectId: "project-id",
        scenarioId: "scenario-id",
        accessToken: "bad-token",
        payload,
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      updateScenario({
        projectId: "project-id",
        scenarioId: "missing-scenario",
        accessToken: "token",
        payload,
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });

    await expect(
      updateScenario({
        projectId: "project-id",
        scenarioId: "scenario-id",
        accessToken: "token",
        payload,
        fetcher: invalidFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "invalid" });

    await expect(
      updateScenario({
        projectId: "project-id",
        scenarioId: "scenario-id",
        accessToken: "token",
        payload,
        fetcher: unavailableFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unavailable" });
  });
});

describe("deleteScenario", () => {
  it("deletes a scenario with an authenticated request", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 204 }));

    await expect(
      deleteScenario({
        projectId: "project-id",
        scenarioId: "scenario-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "success" });
    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/scenarios/scenario-id",
      {
        method: "DELETE",
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("maps scenario deletion authentication and missing-resource responses", async () => {
    const unauthorizedFetcher = vi.fn(async () => new Response(null, { status: 401 }));
    const notFoundFetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      deleteScenario({
        projectId: "project-id",
        scenarioId: "scenario-id",
        accessToken: "bad-token",
        fetcher: unauthorizedFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });

    await expect(
      deleteScenario({
        projectId: "project-id",
        scenarioId: "missing-scenario",
        accessToken: "token",
        fetcher: notFoundFetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });
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

describe("project baseline URL builders", () => {
  it("builds the project baseline URL", () => {
    expect(getProjectBaselineUrl("project-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/baseline"
    );
  });

  it("builds the baseline comparison URL", () => {
    expect(getBaselineComparisonUrl("project-id", "check-run-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id/baseline-comparison"
    );
  });

  it("appends an explicit baseline check run id", () => {
    expect(
      getBaselineComparisonUrl(
        "project-id",
        "check-run-id",
        "http://localhost:8000",
        "baseline-id"
      )
    ).toBe(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id/baseline-comparison?baseline_check_run_id=baseline-id"
    );
  });
});

const baselineProjectPayload = {
  id: "project-id",
  owner_id: "user-id",
  name: "AIM Website",
  service_url: "https://example.com",
  description: null,
  environment: "production",
  scan_interval_minutes: 60,
  response_time_threshold_ms: 2000,
  quality_score_threshold: 80,
  alert_email_enabled: true,
  alert_recipient_email: null,
  is_verified: true,
  baseline_check_run_id: "check-run-id",
  created_at: "2026-07-04T00:00:00Z",
  updated_at: "2026-07-04T00:00:00Z"
};

describe("setProjectBaseline", () => {
  it("sets the project baseline with an authenticated PUT request", async () => {
    const fetcher = vi.fn(async () => Response.json(baselineProjectPayload));

    await expect(
      setProjectBaseline({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      project: baselineProjectPayload
    });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/projects/project-id/baseline", {
      method: "PUT",
      cache: "no-store",
      headers: {
        Authorization: "Bearer token",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ check_run_id: "check-run-id" })
    });
  });

  it("returns conflict when the check run cannot be used as a baseline", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 409 }));

    await expect(
      setProjectBaseline({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "conflict" });
  });

  it("returns not-found when the check run does not belong to the project", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      setProjectBaseline({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });
  });
});

describe("clearProjectBaseline", () => {
  it("clears the project baseline with an authenticated DELETE request", async () => {
    const clearedProject = { ...baselineProjectPayload, baseline_check_run_id: null };
    const fetcher = vi.fn(async () => Response.json(clearedProject));

    await expect(
      clearProjectBaseline({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      project: clearedProject
    });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/projects/project-id/baseline", {
      method: "DELETE",
      cache: "no-store",
      headers: {
        Authorization: "Bearer token"
      }
    });
  });
});

describe("fetchBaselineComparison", () => {
  const comparison = {
    check_run_id: "check-run-id",
    baseline_check_run_id: "baseline-id",
    comparison_type: "baseline",
    overall_score_delta: 3,
    availability_score_delta: 0,
    web_performance_score_delta: 10,
    accessibility_score_delta: 0,
    seo_basic_quality_score_delta: 0,
    response_time_delta_ms: -200,
    performance_score_delta: 10,
    current_deployment_risk: "STABLE",
    baseline_deployment_risk: "STABLE",
    deployment_risk_changed: false,
    summary: "Overall score improved by 3. Response time improved by 200ms."
  };

  it("returns the baseline comparison when the API request succeeds", async () => {
    const fetcher = vi.fn(async () => Response.json(comparison));

    await expect(
      fetchBaselineComparison({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      comparison
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id/baseline-comparison",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("requests an explicit baseline when provided", async () => {
    const fetcher = vi.fn(async () => Response.json(comparison));

    await fetchBaselineComparison({
      projectId: "project-id",
      checkRunId: "check-run-id",
      baselineCheckRunId: "baseline-id",
      accessToken: "token",
      fetcher,
      apiBaseUrl: "http://localhost:8000"
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id/baseline-comparison?baseline_check_run_id=baseline-id",
      {
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
  });

  it("returns conflict when no baseline is configured", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 409 }));

    await expect(
      fetchBaselineComparison({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "conflict" });
  });
});


describe("cancelCheckRun", () => {
  it("cancels an active check run with an authenticated POST request", async () => {
    const checkRun = {
      id: "check-run-id",
      project_id: "project-id",
      requested_by_id: "user-id",
      status: "CANCELLED",
      trigger_source: "manual",
      failure_reason: null,
      queued_at: "2026-07-05T00:00:00Z",
      started_at: null,
      finished_at: "2026-07-05T00:00:10Z",
      created_at: "2026-07-05T00:00:00Z",
      updated_at: "2026-07-05T00:00:10Z"
    };
    const fetcher = vi.fn(async () => Response.json(checkRun));

    await expect(
      cancelCheckRun({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({
      state: "success",
      checkRun
    });

    expect(fetcher).toHaveBeenCalledWith(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id/cancel",
      {
        method: "POST",
        cache: "no-store",
        headers: {
          Authorization: "Bearer token"
        }
      }
    );
    expect(getCancelCheckRunUrl("project-id", "check-run-id", "http://localhost:8000")).toBe(
      "http://localhost:8000/projects/project-id/check-runs/check-run-id/cancel"
    );
  });

  it("returns not-found when the check run does not exist", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 404 }));

    await expect(
      cancelCheckRun({
        projectId: "project-id",
        checkRunId: "check-run-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "not-found" });
  });
});

describe("deleteProject", () => {
  it("deletes a project with an authenticated DELETE request", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 204 }));

    await expect(
      deleteProject({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "success" });

    expect(fetcher).toHaveBeenCalledWith("http://localhost:8000/projects/project-id", {
      method: "DELETE",
      cache: "no-store",
      headers: {
        Authorization: "Bearer token"
      }
    });
  });

  it("returns unauthorized when the session has expired", async () => {
    const fetcher = vi.fn(async () => new Response(null, { status: 401 }));

    await expect(
      deleteProject({
        projectId: "project-id",
        accessToken: "token",
        fetcher,
        apiBaseUrl: "http://localhost:8000"
      })
    ).resolves.toEqual({ state: "unauthorized" });
  });
});
