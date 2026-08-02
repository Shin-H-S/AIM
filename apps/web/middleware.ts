import { NextResponse, type NextRequest } from "next/server";

/**
 * nonce 기반 CSP — script-src에서 'unsafe-inline'을 걷어내는 마지막 층.
 *
 * 왜 미들웨어인가: nonce는 요청마다 달라야 해서 Caddy의 정적 헤더로는
 * 불가능하다. 요청 헤더에 CSP를 실어 보내면 Next가 자기 인라인 스크립트
 * (RSC 페이로드 부트스트랩)에 nonce를 자동으로 붙이고, 우리가 직접 넣는
 * 인라인 스크립트(테마 초기화)는 layout에서 x-nonce를 읽어 붙인다.
 *
 * 위협 모델: httpOnly 쿠키 전환으로 XSS의 토큰 탈취는 이미 막았지만,
 * 실행된 스크립트는 여전히 사용자 세션으로 API를 부릴 수 있다(같은
 * 오리진은 csrf 쿠키를 읽을 수 있으므로). nonce CSP는 주입된 스크립트의
 * 실행 자체를 막는다.
 *
 * dev는 HMR·react-refresh가 eval·인라인을 쓰므로 완화한다 — 운영 검증은
 * production 빌드로 도는 Playwright E2E와 자기 검사(best practices)가 맡는다.
 */

const API_ORIGIN = new URL(
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).origin;

function buildCsp(nonce: string): string {
  const scriptSrc =
    process.env.NODE_ENV === "development"
      ? "'self' 'unsafe-eval' 'unsafe-inline'"
      : `'self' 'nonce-${nonce}' 'strict-dynamic'`;

  return [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self' ${API_ORIGIN}`,
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "object-src 'none'"
  ].join("; ");
}

export function middleware(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = buildCsp(nonce);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  // Next는 요청 헤더의 CSP를 보고 자기 인라인 스크립트에 nonce를 붙인다.
  requestHeaders.set("content-security-policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      // 정적 자산은 HTML이 아니라 CSP가 필요 없다 — 미들웨어 비용도 아낀다.
      source: "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|ico)$).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" }
      ]
    }
  ]
};
