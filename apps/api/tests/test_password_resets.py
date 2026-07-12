from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from uuid import uuid4

import pytest
from aim_api.config import Settings
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models.password_reset_token import PasswordResetToken
from aim_api.models.user import User
from aim_api.security import hash_password, verify_password
from aim_api.services import password_resets
from aim_api.services.password_resets import (
    InvalidResetTokenError,
    confirm_password_reset,
    hash_reset_token,
    request_password_reset,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


class RecordingEmailSender:
    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    def send_message(self, message: EmailMessage) -> None:
        self.messages.append(message)


def build_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "smtp_host": "smtp.test",
        "smtp_from_email": "noreply@test.example",
        "web_base_url": "https://web.test.example",
        "password_reset_token_expire_minutes": 30,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as testing_session:
        yield testing_session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_user(session: Session, *, password: str = "correct horse battery") -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        password_hash=hash_password(password),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def issued_token(session: Session, *, user: User) -> PasswordResetToken:
    token = session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    assert token is not None
    return token


def test_request_creates_token_and_sends_korean_email(session: Session) -> None:
    user = create_user(session)
    sender = RecordingEmailSender()

    request_password_reset(
        session,
        email=user.email,
        settings=build_settings(),
        email_sender=sender,
    )

    token = issued_token(session, user=user)
    assert token.used_at is None
    assert len(sender.messages) == 1
    message = sender.messages[0]
    assert message["To"] == user.email
    assert message["Subject"] == "[AIM] 비밀번호 재설정 안내"
    body = message.get_content()
    assert "비밀번호 재설정" in body
    assert "https://web.test.example/password-reset/confirm?token=" in body
    plaintext = body.split("token=")[1].split()[0]
    assert hash_reset_token(plaintext) == token.token_hash


def test_request_for_unknown_email_is_silent(session: Session) -> None:
    sender = RecordingEmailSender()

    request_password_reset(
        session,
        email="nobody@example.com",
        settings=build_settings(),
        email_sender=sender,
    )

    assert sender.messages == []
    assert session.scalar(select(PasswordResetToken)) is None


def test_request_survives_email_failure(session: Session) -> None:
    user = create_user(session)

    class FailingSender:
        def send_message(self, message: EmailMessage) -> None:
            raise RuntimeError("smtp down")

    request_password_reset(
        session,
        email=user.email,
        settings=build_settings(),
        email_sender=FailingSender(),
    )

    assert issued_token(session, user=user) is not None


def request_and_capture_token(session: Session, *, user: User) -> str:
    sender = RecordingEmailSender()
    request_password_reset(
        session,
        email=user.email,
        settings=build_settings(),
        email_sender=sender,
    )
    body = str(sender.messages[0].get_content())
    return body.split("token=")[1].split()[0]


def test_confirm_replaces_password_once(session: Session) -> None:
    user = create_user(session, password="old password 123")
    plaintext = request_and_capture_token(session, user=user)

    updated = confirm_password_reset(
        session,
        token=plaintext,
        new_password="new password 456",
    )

    assert verify_password("new password 456", updated.password_hash)
    assert not verify_password("old password 123", updated.password_hash)
    assert issued_token(session, user=user).used_at is not None

    with pytest.raises(InvalidResetTokenError):
        confirm_password_reset(session, token=plaintext, new_password="another pass 789")


def test_confirm_rejects_expired_token(session: Session) -> None:
    user = create_user(session)
    plaintext = request_and_capture_token(session, user=user)
    token = issued_token(session, user=user)
    token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()

    with pytest.raises(InvalidResetTokenError):
        confirm_password_reset(session, token=plaintext, new_password="new password 456")


def test_confirm_rejects_unknown_token(session: Session) -> None:
    with pytest.raises(InvalidResetTokenError):
        confirm_password_reset(session, token="not-a-token", new_password="new password 456")


def test_confirm_invalidates_sibling_tokens(session: Session) -> None:
    user = create_user(session)
    first = request_and_capture_token(session, user=user)
    second = request_and_capture_token(session, user=user)

    confirm_password_reset(session, token=second, new_password="new password 456")

    with pytest.raises(InvalidResetTokenError):
        confirm_password_reset(session, token=first, new_password="another pass 789")


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
    monkeypatch.setattr(password_resets, "build_smtp_email_sender", lambda _: None)

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_request_endpoint_returns_202_for_any_email(client: TestClient) -> None:
    signup = client.post(
        "/auth/signup",
        json={"email": "owner@example.com", "password": "correct horse battery"},
    )
    assert signup.status_code == 201

    known = client.post("/auth/password-reset/request", json={"email": "owner@example.com"})
    unknown = client.post("/auth/password-reset/request", json={"email": "nobody@example.com"})

    assert known.status_code == 202
    assert unknown.status_code == 202
    assert known.json() == unknown.json()


def test_confirm_endpoint_rejects_invalid_token(client: TestClient) -> None:
    response = client.post(
        "/auth/password-reset/confirm",
        json={"token": "bogus", "new_password": "new password 456"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Reset token is invalid or expired."}
