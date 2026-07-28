from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt as pyjwt
import pytest
from aim_api.config import get_settings
from aim_api.security import AccessTokenClaims, create_access_token, decode_access_token
from aim_api.services import token_revocation
from aim_api.services.token_revocation import RedisTokenRevocationStore, revoke_token
from fastapi.testclient import TestClient


class InMemoryRevocationStore:
    def __init__(self) -> None:
        self.revoked: dict[str, int] = {}

    def revoke(self, *, token_id: str, ttl_seconds: int) -> None:
        self.revoked[token_id] = ttl_seconds

    def is_revoked(self, *, token_id: str) -> bool:
        return token_id in self.revoked


@pytest.fixture()
def revocation_store(monkeypatch: pytest.MonkeyPatch) -> InMemoryRevocationStore:
    store = InMemoryRevocationStore()
    monkeypatch.setattr(token_revocation, "get_revocation_store", lambda: store)
    return store


@pytest.fixture()
def client(api_client: TestClient, revocation_store: InMemoryRevocationStore) -> TestClient:
    return api_client


def signup_and_login(client: TestClient) -> str:
    payload = {"email": "user@example.com", "password": "correct horse battery"}
    assert client.post("/auth/signup", json=payload).status_code == 201
    login = client.post("/auth/login", json=payload)
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert isinstance(token, str)
    return token


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_logout_revokes_the_token_server_side(
    client: TestClient,
    revocation_store: InMemoryRevocationStore,
) -> None:
    token = signup_and_login(client)

    assert client.get("/auth/me", headers=auth_headers(token)).status_code == 200
    assert client.post("/auth/logout", headers=auth_headers(token)).status_code == 204

    claims = decode_access_token(token)
    assert claims is not None and claims.token_id in revocation_store.revoked
    assert client.get("/auth/me", headers=auth_headers(token)).status_code == 401


def test_logged_out_token_cannot_logout_again(client: TestClient) -> None:
    token = signup_and_login(client)

    assert client.post("/auth/logout", headers=auth_headers(token)).status_code == 204
    assert client.post("/auth/logout", headers=auth_headers(token)).status_code == 401


def test_legacy_token_without_jti_still_works(client: TestClient) -> None:
    token = signup_and_login(client)
    claims = decode_access_token(token)
    assert claims is not None

    settings = get_settings()
    now = datetime.now(UTC)
    legacy_token = pyjwt.encode(
        {
            "sub": str(claims.user_id),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    assert client.get("/auth/me", headers=auth_headers(legacy_token)).status_code == 200
    # jti가 없어도 로그아웃 호출이 실패하지 않는다.
    assert client.post("/auth/logout", headers=auth_headers(legacy_token)).status_code == 204


class RecordingEmailSender:
    def __init__(self) -> None:
        self.bodies: list[str] = []

    def send_message(self, message: object) -> None:
        self.bodies.append(str(getattr(message, "get_content", lambda: "")()))


def test_password_reset_invalidates_existing_sessions(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from aim_api.config import Settings
    from aim_api.services import password_resets

    sender = RecordingEmailSender()
    monkeypatch.setattr(password_resets, "build_smtp_email_sender", lambda _: sender)
    monkeypatch.setattr(
        password_resets,
        "get_settings",
        lambda: Settings(web_base_url="https://web.test.example"),
    )

    token = signup_and_login(client)
    claims = decode_access_token(token)
    assert claims is not None

    # 재설정보다 확실히 이전에 발급된 유효 토큰을 직접 만든다 (iat 10초 전).
    settings = get_settings()
    issued_at = datetime.now(UTC) - timedelta(seconds=10)
    old_token = pyjwt.encode(
        {
            "sub": str(claims.user_id),
            "type": "access",
            "jti": uuid4().hex,
            "iat": issued_at,
            "exp": issued_at + timedelta(minutes=30),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert client.get("/auth/me", headers=auth_headers(old_token)).status_code == 200

    assert (
        client.post(
            "/auth/password-reset/request",
            json={"email": "user@example.com"},
        ).status_code
        == 202
    )
    reset_token = sender.bodies[0].split("token=")[1].split()[0]

    confirm = client.post(
        "/auth/password-reset/confirm",
        json={"token": reset_token, "new_password": "new password 456"},
    )
    assert confirm.status_code == 204

    # 재설정 이전에 발급된 토큰은 거부된다.
    assert client.get("/auth/me", headers=auth_headers(old_token)).status_code == 401

    # 새 비밀번호로 다시 로그인하면 정상 동작한다.
    relogin = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "new password 456"},
    )
    assert relogin.status_code == 200
    new_token = relogin.json()["access_token"]
    assert client.get("/auth/me", headers=auth_headers(new_token)).status_code == 200


def test_revoke_token_uses_remaining_lifetime(
    revocation_store: InMemoryRevocationStore,
) -> None:
    token = create_access_token(uuid4(), expires_delta=timedelta(minutes=10))
    claims = decode_access_token(token)
    assert claims is not None

    revoke_token(claims)

    assert claims.token_id is not None
    ttl = revocation_store.revoked[claims.token_id]
    assert 9 * 60 <= ttl <= 10 * 60


def test_revoke_skips_tokens_without_jti(
    revocation_store: InMemoryRevocationStore,
) -> None:
    claims = AccessTokenClaims(
        user_id=UUID(int=1),
        token_id=None,
        issued_at=None,
        expires_at=None,
    )

    revoke_token(claims)

    assert revocation_store.revoked == {}


def test_redis_store_fails_open_without_redis() -> None:
    store = RedisTokenRevocationStore("redis://127.0.0.1:1/0")

    store.revoke(token_id="abc", ttl_seconds=60)
    assert store.is_revoked(token_id="abc") is False


class RecordingNotifier:
    def __init__(self) -> None:
        self.titles: list[str] = []

    def __call__(self, *, title: str, detail: str, request_id: str | None = None) -> None:
        self.titles.append(title)


def test_revocation_fail_open_notifies_once_per_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """폐기한 토큰이 계속 통하는 상태는 로그 한 줄로 지나가면 안 된다."""
    notifier = RecordingNotifier()
    monkeypatch.setattr(token_revocation, "notify_ops_in_background", notifier)
    store = RedisTokenRevocationStore("redis://127.0.0.1:1/0")

    store.revoke(token_id="t1", ttl_seconds=60)
    # 백오프를 지나 재시도가 또 실패해도 재알림하지 않는다.
    store._storage_unavailable_until = 0.0
    assert store.is_revoked(token_id="t1") is False

    assert notifier.titles == ["Token revocation fail-open"]


def test_revocation_recovery_notifies_and_rearms(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier = RecordingNotifier()
    monkeypatch.setattr(token_revocation, "notify_ops_in_background", notifier)
    store = RedisTokenRevocationStore("redis://127.0.0.1:1/0")

    store.revoke(token_id="t1", ttl_seconds=60)  # 장애 알림
    store._storage_unavailable_until = 0.0
    monkeypatch.setattr(store._client, "exists", lambda key: 0)
    store.is_revoked(token_id="t1")  # 복구 알림

    assert notifier.titles == ["Token revocation fail-open", "Token revocation recovered"]
