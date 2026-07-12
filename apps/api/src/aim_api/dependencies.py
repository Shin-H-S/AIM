from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.models.user import User
from aim_api.security import decode_access_token
from aim_api.services import token_revocation
from aim_api.services import users as user_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


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


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_db)],
) -> User:
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

    return user
