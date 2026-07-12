from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from aim_api.config import get_settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    # jti/iat가 없는 토큰은 폐기 기능 도입 이전에 발급된 것 — 자연 만료까지 유효하다.
    token_id: str | None
    issued_at: datetime | None
    expires_at: datetime | None


def create_access_token(user_id: UUID, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + (
        expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload = {
        "sub": str(user_id),
        "type": "access",
        "jti": uuid4().hex,
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> AccessTokenClaims | None:
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except InvalidTokenError:
        return None

    if payload.get("type") != "access":
        return None

    subject = payload.get("sub")
    if not isinstance(subject, str):
        return None

    try:
        user_id = UUID(subject)
    except ValueError:
        return None

    token_id = payload.get("jti")

    return AccessTokenClaims(
        user_id=user_id,
        token_id=token_id if isinstance(token_id, str) else None,
        issued_at=claim_to_datetime(payload.get("iat")),
        expires_at=claim_to_datetime(payload.get("exp")),
    )


def claim_to_datetime(value: object) -> datetime | None:
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)

    return None
