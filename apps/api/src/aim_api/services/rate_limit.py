import logging
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol

import redis
from fastapi import HTTPException, Request, status

from aim_api.config import get_settings

logger = logging.getLogger(__name__)

RATE_LIMIT_KEY_PREFIX = "rate-limit"
DEFAULT_WINDOW_SECONDS = 60
# 로컬/테스트처럼 Redis가 없는 환경에서 요청을 오래 붙잡지 않도록 짧게 잡는다.
REDIS_SOCKET_TIMEOUT_SECONDS = 0.2
# 저장소 장애 시 이 시간 동안은 재연결을 시도하지 않고 바로 통과시킨다.
STORAGE_RETRY_BACKOFF_SECONDS = 30.0


class RateLimiter(Protocol):
    def hit(self, *, key: str, limit: int, window_seconds: int) -> bool:
        """요청 1회를 기록하고 한도 이내면 True를 반환한다."""


class RedisRateLimiter:
    """Redis INCR 기반 fixed-window 카운터.

    Redis에 접근할 수 없으면 요청을 차단하는 대신 통과시킨다(fail-open) —
    rate limit은 보조 방어선이므로 저장소 장애가 서비스 장애가 되면 안 된다.
    실패 후 일정 시간은 재연결 시도 없이 바로 통과시켜 요청 지연을 막는다.
    """

    def __init__(self, redis_url: str) -> None:
        self._client = redis.Redis.from_url(
            redis_url,
            socket_connect_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
        )
        self._storage_unavailable_until = 0.0

    def hit(self, *, key: str, limit: int, window_seconds: int) -> bool:
        if time.monotonic() < self._storage_unavailable_until:
            return True

        try:
            pipeline = self._client.pipeline()
            pipeline.incr(key)
            pipeline.expire(key, window_seconds, nx=True)
            count = pipeline.execute()[0]
        except redis.RedisError:
            self._storage_unavailable_until = time.monotonic() + STORAGE_RETRY_BACKOFF_SECONDS
            logger.warning("Rate limiter storage is unavailable; allowing requests.")
            return True

        return int(count) <= limit


@lru_cache
def get_rate_limiter() -> RateLimiter:
    return RedisRateLimiter(get_settings().redis_url)


def get_client_ip(request: Request) -> str:
    # Caddy가 X-Forwarded-For를 실제 클라이언트 주소로 설정한다(신뢰되지 않은
    # 클라이언트 제공 값은 프록시에서 대체됨). 프록시 없이 직접 접속하면 remote 주소.
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


def rate_limited(
    scope: str,
    *,
    limit: int,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> Callable[[Request], None]:
    """지정한 스코프에 IP당 fixed-window 한도를 거는 FastAPI 의존성을 만든다."""

    def dependency(request: Request) -> None:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return

        client_ip = get_client_ip(request)
        key = f"{RATE_LIMIT_KEY_PREFIX}:{scope}:{client_ip}"
        if get_rate_limiter().hit(key=key, limit=limit, window_seconds=window_seconds):
            return

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again in a moment.",
            headers={"Retry-After": str(window_seconds)},
        )

    return dependency
