from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, cast
from uuid import UUID

import pytest
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models.agent_investigation import AgentInvestigation
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.services import projects as project_service
from aim_api.services import scan_queue
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


def authenticated_headers(client: TestClient, email: str = "owner@example.com") -> dict[str, str]:
    payload = {"email": email, "password": "correct horse battery staple"}
    signup_response = client.post("/auth/signup", json=payload)
    assert signup_response.status_code in {201, 409}
    login_response = client.post("/auth/login", json=payload)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_project(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/projects",
        json={
            "name": "AIM Website",
            "service_url": "https://example.com",
            "environment": "production",
        },
        headers=headers,
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def create_check_run(project: dict[str, Any], *, status: str) -> str:
    with get_testing_session() as session:
        project_row = session.get(Project, UUID(project["id"]))
        assert project_row is not None
        assert project_row.owner_id is not None
        check_run = CheckRun(
            project_id=project_row.id,
            requested_by_id=project_row.owner_id,
            status=status,
            trigger_source="manual",
        )
        session.add(check_run)
        session.commit()
        return str(check_run.id)


def create_investigation(project: dict[str, Any], check_run_id: str) -> str:
    with get_testing_session() as session:
        investigation = AgentInvestigation(
            project_id=UUID(project["id"]),
            check_run_id=UUID(check_run_id),
            trigger="incident",
            root_cause="scenario_stale",
            confidence="high",
            summary="이동 흔적 명확",
            recommendation="시나리오 갱신",
            generator="llm:claude-haiku-4-5",
            recheck_used=True,
            tool_calls=[{"step": 1, "tool": "get_check_run", "result_summary": "점수 59"}],
            violations=[],
            llm_calls=[
                {
                    "model": "claude-haiku-4-5",
                    "input_tokens": 1200,
                    "output_tokens": 90,
                    "latency_ms": 800,
                }
            ],
            duration_ms=4200,
        )
        session.add(investigation)
        session.commit()
        return str(investigation.id)


def investigation_url(project_id: str, check_run_id: str) -> str:
    return f"/projects/{project_id}/check-runs/{check_run_id}/investigation"


def test_get_returns_404_when_missing(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    check_run_id = create_check_run(project, status=CheckRunStatus.FAILED.value)

    response = client.get(investigation_url(project["id"], check_run_id), headers=headers)

    assert response.status_code == 404


def test_get_returns_investigation_with_trace(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    check_run_id = create_check_run(project, status=CheckRunStatus.FAILED.value)
    create_investigation(project, check_run_id)

    response = client.get(investigation_url(project["id"], check_run_id), headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["root_cause"] == "scenario_stale"
    assert payload["generator"] == "llm:claude-haiku-4-5"
    assert payload["tool_calls"][0]["tool"] == "get_check_run"
    assert payload["llm_calls"][0]["input_tokens"] == 1200
    assert payload["violations"] == []


def test_post_enqueues_manual_investigation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[UUID, str]] = []

    def fake_enqueue(
        *, check_run_id: UUID, incident_id: UUID | None = None, trigger: str = "incident"
    ) -> str:
        captured.append((check_run_id, trigger))
        return "task-1"

    monkeypatch.setattr(scan_queue, "enqueue_agent_investigation", fake_enqueue)
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    check_run_id = create_check_run(project, status=CheckRunStatus.COMPLETED.value)

    response = client.post(investigation_url(project["id"], check_run_id), headers=headers)

    assert response.status_code == 202
    assert response.json() == {"task_id": "task-1"}
    assert captured == [(UUID(check_run_id), "manual")]


def test_post_rejects_running_check_run(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    check_run_id = create_check_run(project, status=CheckRunStatus.RUNNING.value)

    response = client.post(investigation_url(project["id"], check_run_id), headers=headers)

    assert response.status_code == 409


def test_post_rejects_duplicate_investigation(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    check_run_id = create_check_run(project, status=CheckRunStatus.FAILED.value)
    create_investigation(project, check_run_id)

    response = client.post(investigation_url(project["id"], check_run_id), headers=headers)

    assert response.status_code == 409


def test_get_hides_other_users_project(client: TestClient) -> None:
    owner_headers = authenticated_headers(client, email="owner@example.com")
    project = create_project(client, owner_headers)
    check_run_id = create_check_run(project, status=CheckRunStatus.FAILED.value)
    create_investigation(project, check_run_id)
    intruder_headers = authenticated_headers(client, email="intruder@example.com")

    response = client.get(investigation_url(project["id"], check_run_id), headers=intruder_headers)

    assert response.status_code == 404
