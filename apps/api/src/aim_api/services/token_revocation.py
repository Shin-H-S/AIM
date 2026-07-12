import logging
import time
from datetime import UTC, datetime
from functools import lru_cache
from typing import Protocol, cast

import redis

from aim_api.config import get_settings
from aim_api.security import AccessTokenClaims

logger = logging.getLogger(__name__)

REVOKED_TOKEN_KEY_PREFIX = "revoked-token"
REDIS_SOCKET_TIMEOUT_SECONDS = 0.2
# 저장소 장애 시 이 시간 동안은 재연결을 시도하지 않는다.
STORAGE_RETRY_BACKOFF_SECONDS = 30.0
MIN_REVOCATION_TTL_SECONDS = 60


class TokenRevocationStore(Protocol):
    def revoke(self, *, token_id: str, ttl_seconds: int) -> None:
        """토큰 id를 만료까지 거부 목록에 올린다."""

    def is_revoked(self, *, token_id: str) -> bool:
        """토큰 id가 거부 목록에 있으면 True."""


class RedisTokenRevocationStore:
    """Redis 기반 거부 목록.

    Redis에 접근할 수 없으면 폐기를 조용히 건너뛰고 검증은 통과시킨다(fail-open) —
    토큰 수명이 30분으로 제한돼 있어 저장소 장애가 로그인 전체 장애가 되면 안 된다.
    """

    def __init__(self, redis_url: str) -> None:
        self._client = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
        )
        self._storage_unavailable_until = 0.0

    def _storage_available(self) -> bool:
        return time.monotonic() >= self._storage_unavailable_until

    def _mark_storage_unavailable(self) -> None:
        self._storage_unavailable_until = time.monotonic() + STORAGE_RETRY_BACKOFF_SECONDS

    def revoke(self, *, token_id: str, ttl_seconds: int) -> None:
        if not self._storage_available():
            return

        try:
            self._client.set(
                f"{REVOKED_TOKEN_KEY_PREFIX}:{token_id}",
                "1",
                ex=max(ttl_seconds, MIN_REVOCATION_TTL_SECONDS),
            )
        except redis.RedisError:
            self._mark_storage_unavailable()
            logger.warning("Token revocation storage is unavailable; skipping revoke.")

    def is_revoked(self, *, token_id: str) -> bool:
        if not self._storage_available():
            return False

        try:
            # redis-py 타입 스텁이 sync/async 반환을 유니온으로 노출해 cast가 필요하다.
            count = cast("int", self._client.exists(f"{REVOKED_TOKEN_KEY_PREFIX}:{token_id}"))
            return count > 0
        except redis.RedisError:
            self._mark_storage_unavailable()
            logger.warning("Token revocation storage is unavailable; allowing token.")
            return False


@lru_cache
def get_revocation_store() -> TokenRevocationStore:
    return RedisTokenRevocationStore(get_settings().redis_url)


def revoke_token(claims: AccessTokenClaims) -> None:
    """로그아웃한 토큰을 남은 수명 동안 거부 목록에 올린다."""
    if claims.token_id is None:
        return

    remaining_seconds = MIN_REVOCATION_TTL_SECONDS
    if claims.expires_at is not None:
        remaining_seconds = int((claims.expires_at - datetime.now(UTC)).total_seconds())

    get_revocation_store().revoke(token_id=claims.token_id, ttl_seconds=remaining_seconds)


def is_token_revoked(claims: AccessTokenClaims) -> bool:
    if claims.token_id is None:
        return False

    return get_revocation_store().is_revoked(token_id=claims.token_id)
