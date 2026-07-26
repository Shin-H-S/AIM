import { describe, expect, it } from "vitest";
import { isHttpUrl, normalizeServiceUrl } from "./serviceUrl";

// 보이지 않는 문자는 이스케이프로만 적는다 — 소스에 직접 넣으면 읽을 수도, 검토할 수도 없다.
const ZERO_WIDTH_SPACE = "\u200B";
const BOM = "\uFEFF";
const SOFT_HYPHEN = "\u00AD";
const LTR_MARK = "\u200E";

describe("normalizeServiceUrl", () => {
  it("keeps a well-formed url untouched", () => {
    expect(normalizeServiceUrl("https://lab.qaaimsync.com/")).toBe("https://lab.qaaimsync.com/");
    expect(normalizeServiceUrl("http://example.com:8080/path")).toBe(
      "http://example.com:8080/path"
    );
  });

  it("adds https when the scheme is omitted", () => {
    expect(normalizeServiceUrl("lab.qaaimsync.com")).toBe("https://lab.qaaimsync.com");
    expect(normalizeServiceUrl("example.com/status")).toBe("https://example.com/status");
  });

  it("strips invisible characters that survive trim", () => {
    // 붙여넣기로 섞이는 제로폭 공백·BOM·소프트 하이픈 — 파싱 실패의 흔한 원인이다.
    expect(normalizeServiceUrl(`${ZERO_WIDTH_SPACE}https://lab.qaaimsync.com/`)).toBe(
      "https://lab.qaaimsync.com/"
    );
    expect(normalizeServiceUrl(`${BOM}https://example.com`)).toBe("https://example.com");
    expect(normalizeServiceUrl(`https://exam${SOFT_HYPHEN}ple.com`)).toBe("https://example.com");
    expect(normalizeServiceUrl(`  ${LTR_MARK} https://example.com  `)).toBe("https://example.com");
  });

  it("leaves other schemes alone so validation can reject them", () => {
    expect(normalizeServiceUrl("ftp://example.com")).toBe("ftp://example.com");
    expect(normalizeServiceUrl("mailto:someone@example.com")).toBe("mailto:someone@example.com");
  });

  it("returns an empty string for blank input", () => {
    expect(normalizeServiceUrl(`   ${ZERO_WIDTH_SPACE} `)).toBe("");
  });
});

describe("isHttpUrl", () => {
  it("accepts http and https", () => {
    expect(isHttpUrl("https://example.com")).toBe(true);
    expect(isHttpUrl("http://example.com")).toBe(true);
  });

  it("rejects other schemes and unparsable input", () => {
    expect(isHttpUrl("ftp://example.com")).toBe(false);
    expect(isHttpUrl("mailto:someone@example.com")).toBe(false);
    expect(isHttpUrl("example.com")).toBe(false);
    expect(isHttpUrl("")).toBe(false);
  });

  it("accepts what normalize produces for scheme-less input", () => {
    expect(isHttpUrl(normalizeServiceUrl("lab.qaaimsync.com"))).toBe(true);
  });
});
