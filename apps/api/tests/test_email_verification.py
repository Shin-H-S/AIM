from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from uuid import uuid4

import pytest
from aim_api.config import Settings
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models.email_verification_token import EmailVerificationToken
from aim_api.models.user import User
from aim_api.security import hash_password
from aim_api.services import email_verification
from aim_api.services.email_verification import (
    InvalidVerificationTokenError,
    confirm_email_verification,
    hash_verification_token,
    request_email_verification,
    start_email_verification,
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
        "email_verification_token_expire_minutes": 60 * 24,
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


def create_user(session: Session, *, verified: bool = False) -> User:
    user = User(
        email=f"{uuid4()}@example.com",
        password_hash=hash_password("correct horse battery"),
        email_verified_at=datetime.now(UTC) if verified else None,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def issued_token(session: Session, *, user: User) -> EmailVerificationToken:
    token = session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
    )
    assert token is not None
    return token


def start_and_capture_token(session: Session, *, user: User) -> str:
    sender = RecordingEmailSender()
    start_email_verification(session, user=user, settings=build_settings(), email_sender=sender)
    body = str(sender.messages[0].get_content())
    return body.split("token=")[1].split()[0]


def test_start_creates_token_and_sends_korean_email(session: Session) -> None:
    user = create_user(session)
    sender = RecordingEmailSender()

    start_email_verification(session, user=user, settings=build_settings(), email_sender=sender)

    assert user.email_verified_at is None
    token = issued_token(session, user=user)
    assert token.used_at is None
    assert len(sender.messages) == 1
    message = sender.messages[0]
    assert message["To"] == user.email
    assert message["Subject"] == "[AIM] 이메일 인증 안내"
    body = message.get_content()
    assert "이메일 주소 인증" in body
    assert "https://web.test.example/verify-email?token=" in body
    plaintext = body.split("token=")[1].split()[0]
    assert hash_verification_token(plaintext) == token.token_hash


def test_start_without_smtp_marks_user_verified(session: Session) -> None:
    user = create_user(session)

    start_email_verification(session, user=user, settings=build_settings(smtp_host=None))

    assert user.email_verified_at is not None
    assert session.scalar(select(EmailVerificationToken)) is None


def test_start_survives_email_failure_and_keeps_user_unverified(session: Session) -> None:
    user = create_user(session)

    class FailingSender:
        def send_message(self, message: EmailMessage) -> None:
            raise RuntimeError("smtp down")

    start_email_verification(
        session,
        user=user,
        settings=build_settings(),
        email_sender=FailingSender(),
    )

    assert user.email_verified_at is None
    assert issued_token(session, user=user) is not None


def test_request_for_unknown_email_is_silent(session: Session) -> None:
    sender = RecordingEmailSender()

    request_email_verification(
        session,
        email="nobody@example.com",
        settings=build_settings(),
        email_sender=sender,
    )

    assert sender.messages == []
    assert session.scalar(select(EmailVerificationToken)) is None


def test_request_for_verified_user_is_silent(session: Session) -> None:
    user = create_user(session, verified=True)
    sender = RecordingEmailSender()

    request_email_verification(
        session,
        email=user.email,
        settings=build_settings(),
        email_sender=sender,
    )

    assert sender.messages == []


def test_request_resends_for_unverified_user(session: Session) -> None:
    user = create_user(session)
    sender = RecordingEmailSender()

    request_email_verification(
        session,
        email=user.email,
        settings=build_settings(),
        email_sender=sender,
    )

    assert len(sender.messages) == 1
    assert issued_token(session, user=user) is not None


def test_confirm_marks_user_verified_once(session: Session) -> None:
    user = create_user(session)
    plaintext = start_and_capture_token(session, user=user)

    updated = confirm_email_verification(session, token=plaintext)

    assert updated.email_verified_at is not None
    assert issued_token(session, user=user).used_at is not None

    with pytest.raises(InvalidVerificationTokenError):
        confirm_email_verification(session, token=plaintext)


def test_confirm_rejects_expired_token(session: Session) -> None:
    user = create_user(session)
    plaintext = start_and_capture_token(session, user=user)
    token = issued_token(session, user=user)
    token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()

    with pytest.raises(InvalidVerificationTokenError):
        confirm_email_verification(session, token=plaintext)


def test_confirm_rejects_unknown_token(session: Session) -> None:
    with pytest.raises(InvalidVerificationTokenError):
        confirm_email_verification(session, token="not-a-token")


def test_confirm_invalidates_sibling_tokens(session: Session) -> None:
    user = create_user(session)
    first = start_and_capture_token(session, user=user)
    sender = RecordingEmailSender()
    request_email_verification(
        session,
        email=user.email,
        settings=build_settings(),
        email_sender=sender,
    )
    second = str(sender.messages[0].get_content()).split("token=")[1].split()[0]

    confirm_email_verification(session, token=second)

    with pytest.raises(InvalidVerificationTokenError):
        confirm_email_verification(session, token=first)


ClientFactory = Callable[[RecordingEmailSender | None], TestClient]


@pytest.fixture()
def client_factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[ClientFactory]:
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
    # 서비스가 읽는 런타임 설정을 고정해 메일 본문에 인증 링크(token=)가 포함되게 한다.
    monkeypatch.setattr(email_verification, "get_settings", build_settings)

    def factory(sender: RecordingEmailSender | None) -> TestClient:
        monkeypatch.setattr(email_verification, "build_smtp_email_sender", lambda _settings: sender)
        return TestClient(app)

    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_signup_without_smtp_auto_verifies_and_login_works(client_factory: ClientFactory) -> None:
    client = client_factory(None)

    signup = client.post(
        "/auth/signup",
        json={"email": "dev@example.com", "password": "correct horse battery"},
    )
    assert signup.status_code == 201
    assert signup.json()["email_verified_at"] is not None

    login = client.post(
        "/auth/login",
        json={"email": "dev@example.com", "password": "correct horse battery"},
    )
    assert login.status_code == 200


def test_signup_with_smtp_blocks_login_until_confirmed(client_factory: ClientFactory) -> None:
    sender = RecordingEmailSender()
    client = client_factory(sender)

    signup = client.post(
        "/auth/signup",
        json={"email": "owner@example.com", "password": "correct horse battery"},
    )
    assert signup.status_code == 201
    assert signup.json()["email_verified_at"] is None
    assert len(sender.messages) == 1

    blocked = client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery"},
    )
    assert blocked.status_code == 403
    assert blocked.json() == {"detail": "Email is not verified."}

    plaintext = str(sender.messages[0].get_content()).split("token=")[1].split()[0]
    confirm = client.post("/auth/email-verification/confirm", json={"token": plaintext})
    assert confirm.status_code == 204

    login = client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "correct horse battery"},
    )
    assert login.status_code == 200


def test_request_endpoint_returns_202_for_any_email(client_factory: ClientFactory) -> None:
    sender = RecordingEmailSender()
    client = client_factory(sender)

    signup = client.post(
        "/auth/signup",
        json={"email": "owner@example.com", "password": "correct horse battery"},
    )
    assert signup.status_code == 201

    known = client.post("/auth/email-verification/request", json={"email": "owner@example.com"})
    unknown = client.post("/auth/email-verification/request", json={"email": "nobody@example.com"})

    assert known.status_code == 202
    assert unknown.status_code == 202
    assert known.json() == unknown.json()


def test_confirm_endpoint_rejects_invalid_token(client_factory: ClientFactory) -> None:
    client = client_factory(RecordingEmailSender())

    response = client.post("/auth/email-verification/confirm", json={"token": "bogus"})

    assert response.status_code == 400
    assert response.json() == {"detail": "Verification token is invalid or expired."}
