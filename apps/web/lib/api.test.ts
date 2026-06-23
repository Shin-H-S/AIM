import { describe, expect, it, vi } from "vitest";
import { fetchApiHealth, getApiBaseUrl, getApiHealthUrl } from "./api";

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
