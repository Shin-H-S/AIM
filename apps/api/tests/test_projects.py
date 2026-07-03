from collections.abc import Iterator
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models import Project
from aim_api.services import domain_verification
from aim_api.services import projects as project_service
from aim_api.url_validation import UrlValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(project_service, "validate_service_url", lambda _: None)
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


def project_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "AIM Website",
        "service_url": "https://example.com",
        "description": "Public production site",
        "environment": "production",
        "scan_interval_minutes": 60,
        "response_time_threshold_ms": 2_000,
        "quality_score_threshold": 80,
    }
    payload.update(overrides)
    return payload


def create_project(client: TestClient, **overrides: Any) -> dict[str, Any]:
    headers = overrides.pop("headers", authenticated_headers(client))
    response = client.post("/projects", json=project_payload(**overrides), headers=headers)
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def signup_payload(email: str) -> dict[str, str]:
    return {
        "email": email,
        "password": "correct horse battery staple",
    }


def authenticated_headers(client: TestClient, email: str = "owner@example.com") -> dict[str, str]:
    signup_response = client.post("/auth/signup", json=signup_payload(email))
    assert signup_response.status_code in {201, 409}
    login_response = client.post("/auth/login", json=signup_payload(email))
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_project_requires_authentication(client: TestClient) -> None:
    response = client.post("/projects", json=project_payload())

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_create_project(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json=project_payload(name="  AIM API  "),
        headers=authenticated_headers(client),
    )

    assert response.status_code == 201
    body = response.json()
    assert UUID(body["id"])
    assert UUID(body["owner_id"])
    assert body["name"] == "AIM API"
    assert body["service_url"] == "https://example.com/"
    assert body["description"] == "Public production site"
    assert body["environment"] == "production"
    assert body["scan_interval_minutes"] == 60
    assert body["response_time_threshold_ms"] == 2_000
    assert body["quality_score_threshold"] == 80
    assert body["alert_email_enabled"] is True
    assert body["alert_recipient_email"] is None
    assert body["is_verified"] is False
    assert body["created_at"]
    assert body["updated_at"]


def test_list_projects(client: TestClient) -> None:
    headers = authenticated_headers(client)
    first_project = create_project(client, headers=headers, name="First")
    second_project = create_project(client, headers=headers, name="Second")

    response = client.get("/projects", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [project["id"] for project in body] == [second_project["id"], first_project["id"]]


def test_get_project(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers=headers)

    response = client.get(f"/projects/{project['id']}", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == project["id"]
    assert response.json()["is_verified"] is False


def test_get_project_returns_404_for_missing_project(client: TestClient) -> None:
    response = client.get(f"/projects/{uuid4()}", headers=authenticated_headers(client))

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_update_project(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers=headers)

    response = client.patch(
        f"/projects/{project['id']}",
        json={
            "name": "Updated AIM",
            "description": None,
            "environment": "staging",
            "quality_score_threshold": 90,
            "alert_email_enabled": False,
            "alert_recipient_email": " Alerts@Example.COM ",
        },
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == project["id"]
    assert body["name"] == "Updated AIM"
    assert body["description"] is None
    assert body["environment"] == "staging"
    assert body["quality_score_threshold"] == 90
    assert body["alert_email_enabled"] is False
    assert body["alert_recipient_email"] == "alerts@example.com"


def test_update_project_requires_at_least_one_field(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers=headers)

    response = client.patch(f"/projects/{project['id']}", json={}, headers=headers)

    assert response.status_code == 422


def test_delete_project(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers=headers)

    delete_response = client.delete(f"/projects/{project['id']}", headers=headers)
    get_response = client.get(f"/projects/{project['id']}", headers=headers)

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_create_project_rejects_invalid_environment(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json=project_payload(environment="qa"),
        headers=authenticated_headers(client),
    )

    assert response.status_code == 422


def test_create_project_rejects_non_http_service_url(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json=project_payload(service_url="file:///tmp/aim"),
        headers=authenticated_headers(client),
    )

    assert response.status_code == 422


def test_create_project_rejects_invalid_alert_recipient_email(client: TestClient) -> None:
    response = client.post(
        "/projects",
        json=project_payload(alert_recipient_email="not-an-email"),
        headers=authenticated_headers(client),
    )

    assert response.status_code == 422


def test_create_project_rejects_unsafe_service_url(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_service_url(_: str) -> None:
        raise UrlValidationError("Internal details must not be exposed.")

    monkeypatch.setattr(project_service, "validate_service_url", reject_service_url)

    response = client.post(
        "/projects",
        json=project_payload(service_url="https://internal.example.com"),
        headers=authenticated_headers(client),
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Service URL is not allowed."}
    assert "internal.example.com" not in response.text


def test_update_project_rejects_unsafe_service_url(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers=headers)

    def reject_service_url(_: str) -> None:
        raise UrlValidationError("Internal details must not be exposed.")

    monkeypatch.setattr(project_service, "validate_service_url", reject_service_url)

    response = client.patch(
        f"/projects/{project['id']}",
        json={"service_url": "https://internal.example.com"},
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "Service URL is not allowed."}
    assert "Internal details" not in response.text


def test_get_project_verification(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers=headers)

    response = client.get(f"/projects/{project['id']}/verification", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project["id"]
    assert body["verification_token"].startswith("aim_verify_")
    assert body["meta_tag"] == (
        f'<meta name="aim-verification" content="{body["verification_token"]}" />'
    )
    assert body["is_verified"] is False
    assert body["verified_at"] is None


def test_other_user_cannot_get_project_verification(client: TestClient) -> None:
    owner_headers = authenticated_headers(client, "owner@example.com")
    other_headers = authenticated_headers(client, "other@example.com")
    owner_project = create_project(client, headers=owner_headers)

    response = client.get(f"/projects/{owner_project['id']}/verification", headers=other_headers)

    assert response.status_code == 404


def test_verify_project_domain(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers=headers)
    verification = client.get(f"/projects/{project['id']}/verification", headers=headers).json()
    token = verification["verification_token"]

    monkeypatch.setattr(
        domain_verification,
        "fetch_verification_html",
        lambda _: f'<html><head><meta name="aim-verification" content="{token}" /></head></html>',
    )

    response = client.post(f"/projects/{project['id']}/verify", headers=headers)
    project_response = client.get(f"/projects/{project['id']}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "verified"
    assert body["is_verified"] is True
    assert body["verified_at"] is not None
    assert project_response.json()["is_verified"] is True


def test_verify_project_domain_fails_without_meta_tag(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers=headers)

    monkeypatch.setattr(
        domain_verification,
        "fetch_verification_html",
        lambda _: "<html><head></head><body>No token</body></html>",
    )

    response = client.post(f"/projects/{project['id']}/verify", headers=headers)

    assert response.status_code == 400
    assert response.json() == {"detail": "Domain verification failed."}
    assert "No token" not in response.text


def test_list_projects_returns_only_current_users_projects(client: TestClient) -> None:
    owner_headers = authenticated_headers(client, "owner@example.com")
    other_headers = authenticated_headers(client, "other@example.com")
    owner_project = create_project(client, headers=owner_headers, name="Owner Project")
    create_project(client, headers=other_headers, name="Other Project")

    response = client.get("/projects", headers=owner_headers)

    assert response.status_code == 200
    body = response.json()
    assert [project["id"] for project in body] == [owner_project["id"]]


def test_other_user_cannot_read_project(client: TestClient) -> None:
    owner_headers = authenticated_headers(client, "owner@example.com")
    other_headers = authenticated_headers(client, "other@example.com")
    owner_project = create_project(client, headers=owner_headers)

    response = client.get(f"/projects/{owner_project['id']}", headers=other_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_other_user_cannot_update_project(client: TestClient) -> None:
    owner_headers = authenticated_headers(client, "owner@example.com")
    other_headers = authenticated_headers(client, "other@example.com")
    owner_project = create_project(client, headers=owner_headers)

    response = client.patch(
        f"/projects/{owner_project['id']}",
        json={"name": "Hijacked"},
        headers=other_headers,
    )
    owner_response = client.get(f"/projects/{owner_project['id']}", headers=owner_headers)

    assert response.status_code == 404
    assert owner_response.json()["name"] == "AIM Website"


def test_other_user_cannot_delete_project(client: TestClient) -> None:
    owner_headers = authenticated_headers(client, "owner@example.com")
    other_headers = authenticated_headers(client, "other@example.com")
    owner_project = create_project(client, headers=owner_headers)

    response = client.delete(f"/projects/{owner_project['id']}", headers=other_headers)
    owner_response = client.get(f"/projects/{owner_project['id']}", headers=owner_headers)

    assert response.status_code == 404
    assert owner_response.status_code == 200


def test_project_table_is_registered_in_metadata() -> None:
    assert Project.__tablename__ in Base.metadata.tables
