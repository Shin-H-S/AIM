"""httpOnly 세션 쿠키 — 토큰을 JS가 닿을 수 없는 곳으로.

**왜**: 액세스 토큰이 localStorage에 있으면 XSS 한 번으로 그대로 털린다.
CSP의 connect-src가 유일한 완화책이었는데, 그건 "실행된 스크립트가 밖으로
보내는 것"을 막을 뿐 탈취 표면 자체를 없애지 못한다. httpOnly 쿠키는 스크립트가
토큰을 읽는 경로를 원천 차단한다.

**CSRF**: 쿠키는 브라우저가 자동 첨부하므로 CSRF 표면이 새로 생긴다.
1차 방어는 SameSite=Lax(웹과 API가 같은 등록 도메인의 서브도메인이라 정상
요청은 same-site로 실린다), 2차는 double-submit — JS가 읽을 수 있는 csrf
쿠키 값을 헤더로 되돌려 보내게 하고 서버가 둘의 일치를 확인한다. 공격자
사이트는 우리 도메인의 쿠키를 읽을 수 없어 헤더를 만들 수 없다.

**Bearer는 그대로 유효**: Authorization 헤더는 공격자 사이트가 붙일 수 없어
CSRF 면역이다. 배포 훅·스크립트·테스트가 쓰는 Bearer 경로를 막을 이유가 없다.
"""

import secrets

from fastapi import Response

from aim_api.config import get_settings

ACCESS_TOKEN_COOKIE = "aim_access_token"
# httpOnly가 아니다 — 프런트가 값을 읽어 헤더로 되돌려 보내는 것이 double-submit의
# 요체다. 이 쿠키가 새어도 공격자는 "그 값을 헤더에 실을" 능력이 없으면 무용하다.
CSRF_COOKIE = "aim_csrf"
CSRF_HEADER = "x-csrf-token"

CSRF_TOKEN_BYTES = 32


def new_csrf_token() -> str:
    return secrets.token_hex(CSRF_TOKEN_BYTES)


def set_auth_cookies(
    response: Response, *, access_token: str, csrf_token: str | None = None
) -> str:
    """세션 쿠키 한 쌍을 싣는다. 사용한 csrf 토큰을 돌려준다.

    csrf_token을 넘기면 그 값을 유지한 채 만료만 연장한다 — 세션 연장 때
    csrf를 회전시키면, 옛 값을 헤더에 실은 in-flight 요청이 403으로 튕긴다.
    double-submit의 안전성은 값의 신선도가 아니라 "우리 도메인 쿠키를 읽을 수
    있는가"에서 나오므로 세션 수명 동안 값을 유지해도 잃는 것이 없다.
    """
    settings = get_settings()
    max_age_seconds = settings.jwt_access_token_expire_minutes * 60
    if csrf_token is None:
        csrf_token = new_csrf_token()

    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        access_token,
        max_age=max_age_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        domain=settings.auth_cookie_domain,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age_seconds,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        domain=settings.auth_cookie_domain,
        path="/",
    )
    return csrf_token


def clear_auth_cookies(response: Response) -> None:
    """로그아웃 시 두 쿠키를 함께 지운다 — csrf만 남으면 프런트가 세션이 있다고 착각한다."""
    settings = get_settings()
    for cookie_name in (ACCESS_TOKEN_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            cookie_name,
            domain=settings.auth_cookie_domain,
            path="/",
        )
