/**
 * 세션 상태 — 토큰 없는 세계.
 *
 * 액세스 토큰은 더 이상 JS가 만질 수 없다: 로그인하면 서버가 httpOnly 쿠키로
 * 심고, 브라우저가 자동 첨부하며, 로그아웃하면 서버가 지운다. 이 모듈이 다루는
 * 것은 토큰이 아니라 **세션의 흔적**이다 — 서버가 함께 심는 csrf 쿠키는 JS가
 * 읽을 수 있고(double-submit의 요체), 그 존재가 "로그인돼 있음"의 근사값이다.
 *
 * 근사값인 이유: httpOnly 쿠키의 만료를 JS는 볼 수 없다. csrf 쿠키가 있어도
 * 세션이 이미 만료됐을 수 있으므로, 최종 판정은 항상 API의 401이다. 여기의
 * hasSession()은 "로그인 화면을 보여줄까, 앱 화면을 보여줄까"라는 UI 힌트다.
 */

export const SESSION_CHANGE_EVENT = "aim:session-changed";

// 서버(auth_cookies.py)와 같은 이름 — 여기만 고치면 어긋난다.
export const CSRF_COOKIE_NAME = "aim_csrf";
export const CSRF_HEADER_NAME = "X-CSRF-Token";

export function getCsrfToken(): string | null {
  if (typeof document === "undefined") {
    return null;
  }

  for (const part of document.cookie.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === CSRF_COOKIE_NAME) {
      const value = rest.join("=");
      return value ? decodeURIComponent(value) : null;
    }
  }
  return null;
}

export function hasSession(): boolean {
  return getCsrfToken() !== null;
}

/**
 * 로그인·로그아웃 직후 호출해 같은 탭의 세션 UI(헤더 등)를 갱신한다.
 * 쿠키에는 storage 이벤트 같은 변경 통지가 없어 수동으로 알린다.
 */
export function notifySessionChanged(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(new Event(SESSION_CHANGE_EVENT));
}
