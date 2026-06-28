from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models.check_run import CheckRun
from aim_api.models.project import Project
from aim_api.models.scenario import ScenarioRun
from aim_api.services import artifacts, scan_queue, scanner_results, score_results
from aim_api.services import projects as project_service
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


def scenario_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Login flow",
        "description": "Critical login flow",
        "is_active": True,
        "steps": [
            {
                "action": "navigate",
                "target": "https://example.com/login",
                "is_critical": True,
            }
        ],
    }
    payload.update(overrides)
    return payload


def create_scenario(
    client: TestClient,
    *,
    project_id: str,
    headers: dict[str, str],
    **overrides: Any,
) -> dict[str, Any]:
    response = client.post(
        f"/projects/{project_id}/scenarios",
        json=scenario_payload(**overrides),
        headers=headers,
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def create_check_run(
    client: TestClient, project_id: str, headers: dict[str, str]
) -> dict[str, Any]:
    response = client.post(f"/projects/{project_id}/check-runs", json={}, headers=headers)
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_create_check_run_requires_authentication(client: TestClient) -> None:
    response = client.post(f"/projects/{uuid4()}/check-runs", json={})

    assert response.status_code == 401


def test_create_check_run_requires_verified_project(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)

    response = client.post(f"/projects/{project['id']}/check-runs", json={}, headers=headers)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Project must be verified before creating a check run.",
    }


def test_create_check_run(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)

    response = client.post(f"/projects/{project['id']}/check-runs", json={}, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert UUID(body["id"])
    assert body["project_id"] == project["id"]
    assert UUID(body["requested_by_id"])
    assert body["status"] == "QUEUED"
    assert body["trigger_source"] == "manual"
    assert body["failure_reason"] is None
    assert body["queued_at"]
    assert body["started_at"] is None
    assert body["finished_at"] is None


def test_create_check_run_enqueues_scan_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueued_check_run_ids: list[str] = []

    def fake_enqueue_check_run(*, check_run_id: UUID) -> str:
        enqueued_check_run_ids.append(str(check_run_id))
        return str(check_run_id)

    monkeypatch.setattr(scan_queue, "enqueue_check_run", fake_enqueue_check_run)
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)

    response = client.post(f"/projects/{project['id']}/check-runs", json={}, headers=headers)

    assert response.status_code == 201
    assert enqueued_check_run_ids == [response.json()["id"]]


def test_create_check_run_creates_and_enqueues_active_scenario_runs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueued_scenario_run_ids: list[str] = []

    def fake_enqueue_scenario_run(*, scenario_run_id: UUID) -> str:
        enqueued_scenario_run_ids.append(str(scenario_run_id))
        return str(scenario_run_id)

    monkeypatch.setattr(scan_queue, "enqueue_scenario_run", fake_enqueue_scenario_run)
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    active_scenario = create_scenario(client, project_id=project["id"], headers=headers)
    create_scenario(
        client,
        project_id=project["id"],
        headers=headers,
        name="Inactive flow",
        is_active=False,
    )

    response = client.post(f"/projects/{project['id']}/check-runs", json={}, headers=headers)

    assert response.status_code == 201
    check_run_id = response.json()["id"]
    with get_testing_session() as session:
        scenario_run = session.scalars(select(ScenarioRun)).one()
        assert scenario_run.check_run_id == UUID(check_run_id)
        assert scenario_run.scenario_id == UUID(active_scenario["id"])
        assert scenario_run.trigger_source == "check_run"
        assert scenario_run.status == "QUEUED"
    assert enqueued_scenario_run_ids == [str(scenario_run.id)]


def test_create_check_run_returns_503_when_scan_queue_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_enqueue_check_run(*, check_run_id: UUID) -> str:
        _ = check_run_id
        raise scan_queue.ScanQueueUnavailableError

    monkeypatch.setattr(scan_queue, "enqueue_check_run", fake_enqueue_check_run)
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)

    response = client.post(f"/projects/{project['id']}/check-runs", json={}, headers=headers)

    assert response.status_code == 503
    assert response.json() == {"detail": "Scan queue is unavailable."}
    with get_testing_session() as session:
        check_run = session.scalars(select(CheckRun)).one()
        assert check_run.status == "FAILED"
        assert check_run.failure_reason == "Scan queue is unavailable."
        assert check_run.finished_at is not None


def test_create_check_run_marks_linked_scenario_runs_failed_when_queue_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_enqueue_scenario_run(*, scenario_run_id: UUID) -> str:
        _ = scenario_run_id
        raise scan_queue.ScanQueueUnavailableError

    monkeypatch.setattr(scan_queue, "enqueue_scenario_run", fake_enqueue_scenario_run)
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    create_scenario(client, project_id=project["id"], headers=headers)

    response = client.post(f"/projects/{project['id']}/check-runs", json={}, headers=headers)

    assert response.status_code == 503
    with get_testing_session() as session:
        check_run = session.scalars(select(CheckRun)).one()
        scenario_run = session.scalars(select(ScenarioRun)).one()
        assert check_run.status == "FAILED"
        assert scenario_run.check_run_id == check_run.id
        assert scenario_run.status == "FAILED"
        assert scenario_run.failure_reason == "Scan queue is unavailable."
        assert scenario_run.finished_at is not None


def test_list_check_runs(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    first_run = create_check_run(client, project["id"], headers)
    second_run = create_check_run(client, project["id"], headers)

    response = client.get(f"/projects/{project['id']}/check-runs", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [check_run["id"] for check_run in body] == [second_run["id"], first_run["id"]]


def test_get_check_run(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    check_run = create_check_run(client, project["id"], headers)

    response = client.get(
        f"/projects/{project['id']}/check-runs/{check_run['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == check_run["id"]
    assert body["availability_result"] is None
    assert body["ssl_result"] is None
    assert body["lighthouse_result"] is None
    assert body["score_result"] is None
    assert body["comparison_result"] is None
    assert body["artifacts"] == []


def test_get_check_run_includes_scanner_results(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    check_run = create_check_run(client, project["id"], headers)

    with get_testing_session() as session:
        availability_result = scanner_results.record_availability_result(
            session,
            check_run_id=UUID(check_run["id"]),
            service_url="https://example.com",
            final_url="https://example.com/health",
            is_available=True,
            status_code=204,
            response_time_ms=123,
            redirect_count=1,
            uses_https=True,
            timed_out=False,
            failure_reason=None,
        )
        ssl_result = scanner_results.record_ssl_result(
            session,
            check_run_id=UUID(check_run["id"]),
            service_url="https://example.com/health",
            is_applicable=True,
            is_valid=True,
            expires_at=datetime(2027, 6, 26, tzinfo=UTC),
            days_until_expiration=365,
            failure_reason=None,
        )
        artifact = artifacts.record_artifact(
            session,
            check_run_id=UUID(check_run["id"]),
            artifact_type="lighthouse_raw_json",
            storage_backend="local",
            storage_path=f"check-runs/{check_run['id']}/lighthouse/raw.json",
            content_type="application/json",
            size_bytes=17,
            checksum_sha256="a" * 64,
        )
        lighthouse_result = scanner_results.record_lighthouse_result(
            session,
            check_run_id=UUID(check_run["id"]),
            service_url="https://example.com/health",
            is_successful=True,
            performance_score=90,
            accessibility_score=95,
            seo_score=88,
            best_practices_score=92,
            largest_contentful_paint_ms=1200,
            cumulative_layout_shift=0.02,
            total_blocking_time_ms=30,
            raw_json_artifact_id=artifact.id,
            failure_reason=None,
        )
        score_project = session.get(Project, UUID(project["id"]))
        assert score_project is not None
        score_results.record_score_result(
            session,
            check_run_id=UUID(check_run["id"]),
            project=score_project,
            availability_result=availability_result,
            ssl_result=ssl_result,
            lighthouse_result=lighthouse_result,
        )

    response = client.get(
        f"/projects/{project['id']}/check-runs/{check_run['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == check_run["id"]
    assert body["availability_result"] == {
        "service_url": "https://example.com",
        "final_url": "https://example.com/health",
        "is_available": True,
        "status_code": 204,
        "response_time_ms": 123,
        "redirect_count": 1,
        "uses_https": True,
        "timed_out": False,
        "failure_reason": None,
        "created_at": body["availability_result"]["created_at"],
        "updated_at": body["availability_result"]["updated_at"],
    }
    assert body["ssl_result"] == {
        "service_url": "https://example.com/health",
        "is_applicable": True,
        "is_valid": True,
        "expires_at": "2027-06-26T00:00:00",
        "days_until_expiration": 365,
        "failure_reason": None,
        "created_at": body["ssl_result"]["created_at"],
        "updated_at": body["ssl_result"]["updated_at"],
    }
    assert body["lighthouse_result"] == {
        "service_url": "https://example.com/health",
        "is_successful": True,
        "performance_score": 90,
        "accessibility_score": 95,
        "seo_score": 88,
        "best_practices_score": 92,
        "largest_contentful_paint_ms": 1200,
        "cumulative_layout_shift": 0.02,
        "total_blocking_time_ms": 30,
        "raw_json_artifact_id": str(artifact.id),
        "failure_reason": None,
        "created_at": body["lighthouse_result"]["created_at"],
        "updated_at": body["lighthouse_result"]["updated_at"],
    }
    assert body["score_result"] == {
        "availability_score": 100,
        "functional_stability_score": None,
        "web_performance_score": 90,
        "accessibility_score": 95,
        "seo_basic_quality_score": 90,
        "regression_stability_score": None,
        "overall_score": 95,
        "evaluated_weight": 60,
        "grade": "A",
        "deployment_risk": "STABLE",
        "gate_reason": None,
        "scoring_version": "2026-06-28.scenario-v1",
        "created_at": body["score_result"]["created_at"],
        "updated_at": body["score_result"]["updated_at"],
    }
    assert body["comparison_result"] is None
    assert body["artifacts"] == [
        {
            "id": str(artifact.id),
            "artifact_type": "lighthouse_raw_json",
            "storage_backend": "local",
            "storage_path": f"check-runs/{check_run['id']}/lighthouse/raw.json",
            "content_type": "application/json",
            "size_bytes": 17,
            "checksum_sha256": "a" * 64,
            "created_at": body["artifacts"][0]["created_at"],
        }
    ]


def test_cancel_check_run(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    check_run = create_check_run(client, project["id"], headers)

    response = client.post(
        f"/projects/{project['id']}/check-runs/{check_run['id']}/cancel",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CANCELLED"
    assert body["finished_at"] is not None


def test_other_user_cannot_create_check_run_for_project(client: TestClient) -> None:
    owner_headers = authenticated_headers(client, "owner@example.com")
    other_headers = authenticated_headers(client, "other@example.com")
    project = create_verified_project(client, owner_headers)

    response = client.post(f"/projects/{project['id']}/check-runs", json={}, headers=other_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_other_user_cannot_read_check_run(client: TestClient) -> None:
    owner_headers = authenticated_headers(client, "owner@example.com")
    other_headers = authenticated_headers(client, "other@example.com")
    project = create_verified_project(client, owner_headers)
    check_run = create_check_run(client, project["id"], owner_headers)

    response = client.get(
        f"/projects/{project['id']}/check-runs/{check_run['id']}",
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}


def test_missing_check_run_returns_404(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)

    response = client.get(f"/projects/{project['id']}/check-runs/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Check run not found."}
