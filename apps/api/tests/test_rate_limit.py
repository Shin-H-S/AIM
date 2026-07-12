from collections.abc import Iterator

import pytest
from aim_api.config import Settings
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.services import rate_limit
from aim_api.services.rate_limit import RedisRateLimiter, get_client_ip
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


class FakeRateLimiter:
    def __init__(self, *, allow: bool) -> None:
        self.allow = allow
        self.keys: list[str] = []

    def hit(self, *, key: str, limit: int, window_seconds: int) -> bool:
        self.keys.append(key)
        return self.allow


def build_request(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": raw_headers,
        "client": ("203.0.113.9", 40000),
        "query_string": b"",
    }
    return Request(scope)


def test_client_ip_prefers_forwarded_header() -> None:
    request = build_request({"X-Forwarded-For": "198.51.100.7, 10.0.0.1"})
    assert get_client_ip(request) == "198.51.100.7"


def test_client_ip_falls_back_to_remote_address() -> None:
    assert get_client_ip(build_request()) == "203.0.113.9"


def test_redis_rate_limiter_fails_open_without_redis() -> None:
    limiter = RedisRateLimiter("redis://127.0.0.1:1/0")

    assert limiter.hit(key="rate-limit:test:ip", limit=1, window_seconds=60) is True
    # 실패 후 백오프 동안은 재연결 없이 바로 통과한다.
    assert limiter._storage_unavailable_until > 0
    assert limiter.hit(key="rate-limit:test:ip", limit=1, window_seconds=60) is True


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_database() -> Iterator[Session]:
        with testing_session_local() as db_session:
            yield db_session

    app.dependency_overrides[get_db] = override_database

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_login_returns_429_when_limit_is_exceeded(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = FakeRateLimiter(allow=False)
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: limiter)

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {"detail": "Too many requests. Try again in a moment."}
    assert limiter.keys == ["rate-limit:auth-login:testclient"]


def test_login_passes_through_when_within_limit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = FakeRateLimiter(allow=True)
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: limiter)

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )

    # 한도 안이면 rate limit은 통과하고 자격 증명 검증(401)으로 넘어간다.
    assert response.status_code == 401
    assert limiter.keys == ["rate-limit:auth-login:testclient"]


def test_rate_limit_can_be_disabled_by_settings(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = FakeRateLimiter(allow=False)
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: limiter)
    monkeypatch.setattr(
        rate_limit,
        "get_settings",
        lambda: Settings(rate_limit_enabled=False),
    )

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "password123"},
    )

    assert response.status_code == 401
    assert limiter.keys == []


def test_password_reset_request_is_rate_limited(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = FakeRateLimiter(allow=False)
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: limiter)

    response = client.post(
        "/auth/password-reset/request",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 429
    assert limiter.keys == ["rate-limit:password-reset-request:testclient"]


def test_deploy_hook_is_rate_limited(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = FakeRateLimiter(allow=False)
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: limiter)

    response = client.post(
        "/hooks/projects/00000000-0000-0000-0000-000000000000/check-runs",
        json={},
    )

    assert response.status_code == 429
    assert limiter.keys == ["rate-limit:deploy-hook:testclient"]
