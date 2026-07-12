from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models.user import User
from aim_api.security import create_access_token, decode_access_token
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def client() -> Iterator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_database() -> Iterator[Session]:
        with testing_session_local() as session:
            yield session

    app.dependency_overrides[get_db] = override_database

    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def signup_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "email": "user@example.com",
        "password": "correct horse battery staple",
    }
    payload.update(overrides)
    return payload


def signup(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/auth/signup", json=signup_payload(**overrides))
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def login(client: TestClient, **overrides: Any) -> dict[str, Any]:
    payload = {
        "email": "user@example.com",
        "password": "correct horse battery staple",
    }
    payload.update(overrides)
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 200
    return cast(dict[str, Any], response.json())


@contextmanager
def get_testing_session() -> Iterator[Session]:
    override_database = cast(Callable[[], Iterator[Session]], app.dependency_overrides[get_db])
    dependency = override_database()
    session = next(dependency)
    try:
        yield session
    finally:
        for _ in dependency:
            pass


def test_signup_creates_user_without_exposing_password(client: TestClient) -> None:
    response = client.post(
        "/auth/signup",
        json=signup_payload(email=" User@Example.COM "),
    )

    assert response.status_code == 201
    body = response.json()
    assert UUID(body["id"])
    assert body["email"] == "user@example.com"
    assert body["is_active"] is True
    assert body["created_at"]
    assert body["updated_at"]
    assert "password" not in body
    assert "password_hash" not in body


def test_signup_hashes_password(client: TestClient) -> None:
    signup(client)

    with get_testing_session() as session:
        user = session.scalar(select(User).where(User.email == "user@example.com"))

    assert user is not None
    assert user.password_hash != "correct horse battery staple"
    assert user.password_hash.startswith("$argon2")


def test_signup_rejects_duplicate_email(client: TestClient) -> None:
    signup(client)

    response = client.post(
        "/auth/signup",
        json=signup_payload(email="USER@example.com"),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Email is already registered."}


def test_signup_rejects_short_password(client: TestClient) -> None:
    response = client.post("/auth/signup", json=signup_payload(password="short"))

    assert response.status_code == 422


def test_login_returns_bearer_token(client: TestClient) -> None:
    user = signup(client)

    body = login(client)

    assert body["token_type"] == "bearer"
    claims = decode_access_token(body["access_token"])
    assert claims is not None
    assert claims.user_id == UUID(user["id"])
    assert claims.token_id
    assert claims.issued_at is not None


def test_login_rejects_invalid_password(client: TestClient) -> None:
    signup(client)

    response = client.post(
        "/auth/login",
        json={
            "email": "user@example.com",
            "password": "wrong password",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}
    assert response.headers["www-authenticate"] == "Bearer"


def test_read_me_returns_authenticated_user(client: TestClient) -> None:
    user = signup(client)
    token = login(client)["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["id"] == user["id"]
    assert response.json()["email"] == "user@example.com"


def test_read_me_rejects_invalid_token(client: TestClient) -> None:
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-token"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials."}


def test_logout_requires_valid_token(client: TestClient) -> None:
    signup(client)
    token = login(client)["access_token"]

    response = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 204
    assert response.content == b""


def test_decode_access_token_rejects_expired_token() -> None:
    token = create_access_token(uuid4(), expires_delta=timedelta(seconds=-1))

    assert decode_access_token(token) is None
