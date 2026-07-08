from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.services import projects as project_service
from aim_api.services import scan_queue
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(project_service, "validate_service_url", lambda _: None)
    monkeypatch.setattr(scan_queue, "enqueue_check_run", lambda *, check_run_id: str(check_run_id))
    monkeypatch.setattr(
        scan_queue,
        "enqueue_scenario_run",
        lambda *, scenario_run_id: str(scenario_run_id),
    )
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


def create_project(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post("/projects", json=project_payload(), headers=headers)
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def mark_project_verified(project_id: str) -> None:
    with get_testing_session() as session:
        project = session.get(Project, UUID(project_id))
        assert project is not None
        project.verified_at = datetime.now(UTC)
        session.commit()


def create_verified_project(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    project = create_project(client, headers)
    mark_project_verified(project["id"])
    return project


def issue_token(client: TestClient, headers: dict[str, str], project_id: str) -> dict[str, Any]:
    response = client.post(
        f"/projects/{project_id}/tokens",
        json={"name": "github-actions"},
        headers=headers,
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def hook_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_issue_token_returns_plaintext_once(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)

    issued = issue_token(client, headers, project["id"])

    assert issued["name"] == "github-actions"
    assert issued["token"].startswith("aim_")
    assert issued["revoked_at"] is None

    listed = client.get(f"/projects/{project['id']}/tokens", headers=headers)
    assert listed.status_code == 200
    body = listed.json()
    assert len(body) == 1
    assert body[0]["id"] == issued["id"]
    assert "token" not in body[0]
    assert "token_hash" not in body[0]


def test_deploy_hook_creates_deploy_check_run(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    issued = issue_token(client, headers, project["id"])

    response = client.post(
        f"/hooks/projects/{project['id']}/check-runs",
        json={"deploy_ref": "3e7926b"},
        headers=hook_headers(issued["token"]),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["trigger_source"] == "deploy"
    assert body["deploy_ref"] == "3e7926b"
    assert body["status"] == "QUEUED"
    assert body["project_id"] == project["id"]
    assert body["requested_by_id"] == project["owner_id"]


def test_deploy_hook_allows_missing_deploy_ref(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    issued = issue_token(client, headers, project["id"])

    response = client.post(
        f"/hooks/projects/{project['id']}/check-runs",
        json={},
        headers=hook_headers(issued["token"]),
    )

    assert response.status_code == 201
    assert response.json()["deploy_ref"] is None


def test_deploy_hook_rejects_missing_or_invalid_token(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)

    missing = client.post(f"/hooks/projects/{project['id']}/check-runs", json={})
    invalid = client.post(
        f"/hooks/projects/{project['id']}/check-runs",
        json={},
        headers=hook_headers("aim_not-a-real-token"),
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "Invalid or missing deploy token."}


def test_deploy_hook_rejects_revoked_token(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    issued = issue_token(client, headers, project["id"])

    revoke = client.delete(
        f"/projects/{project['id']}/tokens/{issued['id']}",
        headers=headers,
    )
    assert revoke.status_code == 200
    assert revoke.json()["revoked_at"] is not None

    response = client.post(
        f"/hooks/projects/{project['id']}/check-runs",
        json={},
        headers=hook_headers(issued["token"]),
    )

    assert response.status_code == 401


def test_deploy_hook_rejects_token_of_other_project(client: TestClient) -> None:
    headers = authenticated_headers(client)
    first_project = create_verified_project(client, headers)
    second_project = create_verified_project(client, headers)
    issued = issue_token(client, headers, first_project["id"])

    response = client.post(
        f"/hooks/projects/{second_project['id']}/check-runs",
        json={},
        headers=hook_headers(issued["token"]),
    )

    assert response.status_code == 401


def test_deploy_hook_rejects_unverified_project(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    issued = issue_token(client, headers, project["id"])

    response = client.post(
        f"/hooks/projects/{project['id']}/check-runs",
        json={},
        headers=hook_headers(issued["token"]),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Project domain is not verified."}


def test_deploy_hook_rejects_when_check_run_is_active(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    issued = issue_token(client, headers, project["id"])

    first = client.post(
        f"/hooks/projects/{project['id']}/check-runs",
        json={},
        headers=hook_headers(issued["token"]),
    )
    assert first.status_code == 201

    second = client.post(
        f"/hooks/projects/{project['id']}/check-runs",
        json={},
        headers=hook_headers(issued["token"]),
    )

    assert second.status_code == 409
    assert second.json() == {"detail": "A check run is already active for this project."}


def test_deploy_hook_marks_check_run_failed_when_queue_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    issued = issue_token(client, headers, project["id"])

    def raise_queue_unavailable(*, check_run_id: UUID) -> str:
        raise scan_queue.ScanQueueUnavailableError

    monkeypatch.setattr(scan_queue, "enqueue_check_run", raise_queue_unavailable)

    response = client.post(
        f"/hooks/projects/{project['id']}/check-runs",
        json={},
        headers=hook_headers(issued["token"]),
    )

    assert response.status_code == 503
    with get_testing_session() as session:
        check_run = session.scalar(
            select(CheckRun).where(CheckRun.project_id == UUID(project["id"]))
        )
        assert check_run is not None
        assert check_run.status == CheckRunStatus.FAILED.value


def test_revoke_token_of_missing_project_returns_404(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)

    response = client.delete(
        f"/projects/{project['id']}/tokens/{uuid4()}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project API token not found."}
