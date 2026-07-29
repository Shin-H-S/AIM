from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from aim_api.auth_cookies import ACCESS_TOKEN_COOKIE, CSRF_COOKIE, set_auth_cookies
from aim_api.config import get_settings
from aim_api.database import get_db
from aim_api.models.user import User
from aim_api.security import AccessTokenClaims, create_access_token, decode_access_token
from aim_api.services import token_revocation
from aim_api.services import users as user_service

# auto_error=False: 헤더가 없어도 401을 내지 않는다 — 쿠키 폴백이 이어받는다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def as_utc(value: datetime) -> datetime:
    """SQLite는 tzinfo를 보존하지 않으므로 naive 값을 UTC로 간주한다."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def get_request_token(request: Request, bearer_token: str | None) -> str | None:
    """Bearer 우선, 없으면 httpOnly 쿠키.

    명시적으로 실은 Authorization 헤더는 호출자의 의도다(스크립트·배포 훅·테스트).
    브라우저 세션은 쿠키로 온다 — JS가 토큰을 만질 수 없는 것이 전환의 목적이다.
    """
    if bearer_token:
        return bearer_token
    return request.cookies.get(ACCESS_TOKEN_COOKIE)


def renew_cookie_session_if_stale(
    request: Request, response: Response, claims: AccessTokenClaims
) -> None:
    """반감기를 지난 쿠키 세션을 새 토큰으로 연장한다(sliding session).

    30분 고정 만료는 localStorage 시절엔 어차피 안 보였지만, 쿠키 세계에선
    한창 쓰는 중에 소리 없이 로그아웃된다. 쿠키는 서버가 응답에 다시 실을 수
    있으므로 refresh 토큰 없이 여기서 연장한다 — 활동 중인 세션은 계속 살고,
    방치된 세션은 30분 뒤 자연 만료한다.

    옛 토큰은 폐기하지 않는다. 브라우저는 즉시 새 쿠키로 갈아타고, 옛 토큰의
    잔여 수명은 최대 30분 — 연장 도입 전과 정확히 같은 노출이다.
    """
    if claims.expires_at is None:
        return

    lifetime = timedelta(minutes=get_settings().jwt_access_token_expire_minutes)
    remaining = as_utc(claims.expires_at) - datetime.now(UTC)
    if remaining > lifetime / 2:
        return

    set_auth_cookies(
        response,
        access_token=create_access_token(claims.user_id),
        csrf_token=request.cookies.get(CSRF_COOKIE),
    )


def get_current_user(
    request: Request,
    response: Response,
    bearer_token: Annotated[str | None, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_db)],
) -> User:
    token = get_request_token(request, bearer_token)
    if token is None:
        raise authentication_error()

    claims = decode_access_token(token)
    if claims is None:
        raise authentication_error()

    if token_revocation.is_token_revoked(claims):
        raise authentication_error()

    try:
        user = user_service.get_user_by_id(session, claims.user_id)
    except user_service.UserNotFoundError as exc:
        raise authentication_error() from exc

    if not user.is_active:
        raise authentication_error()

    # 비밀번호 재설정 이전에 발급된 토큰은 전부 거부한다.
    if (
        user.token_invalid_before is not None
        and claims.issued_at is not None
        and as_utc(claims.issued_at) < as_utc(user.token_invalid_before)
    ):
        raise authentication_error()

    # Bearer 호출자는 토큰 수명을 스스로 관리한다 — 연장은 쿠키 세션만.
    if bearer_token is None:
        renew_cookie_session_if_stale(request, response, claims)

    return user
