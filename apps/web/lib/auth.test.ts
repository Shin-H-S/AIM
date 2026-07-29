import { afterEach, describe, expect, it, vi } from "vitest";
import { CSRF_COOKIE_NAME, getCsrfToken, hasSession } from "./auth";

function stubCookies(cookie: string) {
  vi.stubGlobal("document", { cookie });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("cookie session state", () => {
  it("reads the csrf token from the cookie jar", () => {
    stubCookies(`theme=dark; ${CSRF_COOKIE_NAME}=csrf-value; other=1`);

    expect(getCsrfToken()).toBe("csrf-value");
    expect(hasSession()).toBe(true);
  });

  it("decodes an encoded csrf value", () => {
    stubCookies(`${CSRF_COOKIE_NAME}=${encodeURIComponent("a=b c")}`);

    expect(getCsrfToken()).toBe("a=b c");
  });

  it("treats a missing csrf cookie as signed out", () => {
    stubCookies("theme=dark");

    expect(getCsrfToken()).toBeNull();
    expect(hasSession()).toBe(false);
  });

  it("treats an empty csrf cookie as signed out", () => {
    stubCookies(`${CSRF_COOKIE_NAME}=`);

    expect(getCsrfToken()).toBeNull();
    expect(hasSession()).toBe(false);
  });

  it("does not match cookies whose name merely contains the csrf name", () => {
    stubCookies(`not_${CSRF_COOKIE_NAME}=intruder`);

    expect(getCsrfToken()).toBeNull();
  });

  it("returns null outside the browser", () => {
    // vitest node 환경에는 document가 없다 — SSR 경로와 같은 조건이다.
    expect(getCsrfToken()).toBeNull();
    expect(hasSession()).toBe(false);
  });
});
