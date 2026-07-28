import pytest
import redis as redis_module
from aim_api.config import Settings
from aim_api.services import rate_limit
from aim_api.services.rate_limit import RedisRateLimiter, get_client_ip
from fastapi import Request
from fastapi.testclient import TestClient


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
def client(api_client: TestClient) -> TestClient:
    return api_client


@pytest.fixture(autouse=True)
def rate_limiting_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """이 파일은 레이트 리밋 자체를 검증하므로 명시적으로 켠다.

    스위트 전체는 레이트 리밋을 끄고 돈다(conftest.py) — 모든 테스트가 같은
    IP에서 요청하므로, 켜 두면 한도를 넘겨 서로를 망가뜨린다. 그러니 여기서
    주변 설정에 기대지 않고 직접 켜야 한다.
    """
    monkeypatch.setattr(rate_limit, "get_settings", lambda: Settings(rate_limit_enabled=True))


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


class RecordingNotifier:
    def __init__(self) -> None:
        self.titles: list[str] = []

    def __call__(self, *, title: str, detail: str, request_id: str | None = None) -> None:
        self.titles.append(title)


def test_fail_open_notifies_once_per_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    """백오프 창마다 재알림하면 장애 하나가 알림 수십 건이 된다."""
    notifier = RecordingNotifier()
    monkeypatch.setattr(rate_limit, "notify_ops_in_background", notifier)
    limiter = RedisRateLimiter("redis://127.0.0.1:1/0")

    assert limiter.hit(key="rate-limit:test:ip", limit=1, window_seconds=60) is True
    # 백오프를 지나 재시도가 다시 실패해도 알림은 처음 1회뿐이어야 한다.
    limiter._storage_unavailable_until = 0.0
    assert limiter.hit(key="rate-limit:test:ip", limit=1, window_seconds=60) is True

    assert notifier.titles == ["Rate limiter fail-open"]


def test_recovery_notifies_and_rearms(monkeypatch: pytest.MonkeyPatch) -> None:
    """복구를 알리지 않으면 운영자는 장애가 끝났는지 모른 채 남는다."""
    notifier = RecordingNotifier()
    monkeypatch.setattr(rate_limit, "notify_ops_in_background", notifier)
    limiter = RedisRateLimiter("redis://127.0.0.1:1/0")

    class FakePipeline:
        def incr(self, key: str) -> None: ...
        def expire(self, key: str, window: int, nx: bool) -> None: ...
        def execute(self) -> list[int]:
            return [1]

    limiter.hit(key="rate-limit:test:ip", limit=1, window_seconds=60)  # 장애 알림
    limiter._storage_unavailable_until = 0.0
    monkeypatch.setattr(limiter._client, "pipeline", lambda: FakePipeline())
    limiter.hit(key="rate-limit:test:ip", limit=1, window_seconds=60)  # 복구 알림

    assert notifier.titles == ["Rate limiter fail-open", "Rate limiter recovered"]

    # 복구 뒤 다시 장애가 나면 재무장돼 다시 알린다.
    def broken_pipeline() -> FakePipeline:
        raise redis_module.RedisError("down again")

    monkeypatch.setattr(limiter._client, "pipeline", broken_pipeline)
    limiter._storage_unavailable_until = 0.0
    limiter.hit(key="rate-limit:test:ip", limit=1, window_seconds=60)

    assert notifier.titles[-1] == "Rate limiter fail-open"
