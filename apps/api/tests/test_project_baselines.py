from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import pytest
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.services import projects as project_service
from aim_api.services import scan_queue, scanner_results, score_results
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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


def create_verified_project(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.post("/projects", json=project_payload(), headers=headers)
    assert response.status_code == 201
    project = cast(dict[str, Any], response.json())
    with get_testing_session() as session:
        stored_project = session.get(Project, UUID(project["id"]))
        assert stored_project is not None
        stored_project.verified_at = datetime.now(UTC)
        session.commit()
    return project


def create_check_run(
    client: TestClient, project_id: str, headers: dict[str, str]
) -> dict[str, Any]:
    response = client.post(f"/projects/{project_id}/check-runs", json={}, headers=headers)
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def record_scored_terminal_run(
    check_run_id: str,
    *,
    response_time_ms: int,
    performance_score: int,
) -> None:
    with get_testing_session() as session:
        check_run = session.get(CheckRun, UUID(check_run_id))
        assert check_run is not None
        project = session.get(Project, check_run.project_id)
        assert project is not None
        check_run.status = CheckRunStatus.COMPLETED.value
        check_run.finished_at = datetime.now(UTC)
        session.commit()

        availability_result = scanner_results.record_availability_result(
            session,
            check_run_id=check_run.id,
            service_url="https://example.com",
            final_url="https://example.com",
            is_available=True,
            status_code=200,
            response_time_ms=response_time_ms,
            redirect_count=0,
            uses_https=True,
            timed_out=False,
            failure_reason=None,
        )
        ssl_result = scanner_results.record_ssl_result(
            session,
            check_run_id=check_run.id,
            service_url="https://example.com",
            is_applicable=True,
            is_valid=True,
            expires_at=datetime(2027, 6, 27, tzinfo=UTC),
            days_until_expiration=365,
            failure_reason=None,
        )
        lighthouse_result = scanner_results.record_lighthouse_result(
            session,
            check_run_id=check_run.id,
            service_url="https://example.com",
            is_successful=True,
            performance_score=performance_score,
            accessibility_score=95,
            seo_score=90,
            best_practices_score=90,
            largest_contentful_paint_ms=1200,
            cumulative_layout_shift=0.02,
            total_blocking_time_ms=30,
            raw_json_artifact_id=None,
            failure_reason=None,
        )
        score_results.record_score_result(
            session,
            check_run_id=check_run.id,
            project=project,
            availability_result=availability_result,
            ssl_result=ssl_result,
            lighthouse_result=lighthouse_result,
        )


def test_set_and_clear_project_baseline(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    check_run = create_check_run(client, project["id"], headers)
    record_scored_terminal_run(check_run["id"], response_time_ms=500, performance_score=90)

    set_response = client.put(
        f"/projects/{project['id']}/baseline",
        json={"check_run_id": check_run["id"]},
        headers=headers,
    )

    assert set_response.status_code == 200
    assert set_response.json()["baseline_check_run_id"] == check_run["id"]

    project_response = client.get(f"/projects/{project['id']}", headers=headers)
    assert project_response.json()["baseline_check_run_id"] == check_run["id"]

    clear_response = client.delete(f"/projects/{project['id']}/baseline", headers=headers)

    assert clear_response.status_code == 200
    assert clear_response.json()["baseline_check_run_id"] is None


def test_set_project_baseline_rejects_unscored_check_run(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    check_run = create_check_run(client, project["id"], headers)

    response = client.put(
        f"/projects/{project['id']}/baseline",
        json={"check_run_id": check_run["id"]},
        headers=headers,
    )

    assert response.status_code == 409


def test_set_project_baseline_returns_404_for_other_projects_check_run(
    client: TestClient,
) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    other_project = create_verified_project(client, headers)
    other_check_run = create_check_run(client, other_project["id"], headers)
    record_scored_terminal_run(other_check_run["id"], response_time_ms=500, performance_score=90)

    response = client.put(
        f"/projects/{project['id']}/baseline",
        json={"check_run_id": other_check_run["id"]},
        headers=headers,
    )

    assert response.status_code == 404


def test_get_baseline_comparison_uses_pinned_baseline(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    baseline_run = create_check_run(client, project["id"], headers)
    record_scored_terminal_run(baseline_run["id"], response_time_ms=700, performance_score=80)
    target_run = create_check_run(client, project["id"], headers)
    record_scored_terminal_run(target_run["id"], response_time_ms=500, performance_score=90)
    set_response = client.put(
        f"/projects/{project['id']}/baseline",
        json={"check_run_id": baseline_run["id"]},
        headers=headers,
    )
    assert set_response.status_code == 200

    response = client.get(
        f"/projects/{project['id']}/check-runs/{target_run['id']}/baseline-comparison",
        headers=headers,
    )

    assert response.status_code == 200
    comparison = response.json()
    assert comparison["comparison_type"] == "baseline"
    assert comparison["check_run_id"] == target_run["id"]
    assert comparison["baseline_check_run_id"] == baseline_run["id"]
    assert comparison["overall_score_delta"] == 3
    assert comparison["web_performance_score_delta"] == 10
    assert comparison["performance_score_delta"] == 10
    assert comparison["response_time_delta_ms"] == -200
    assert comparison["deployment_risk_changed"] is False


def test_get_baseline_comparison_returns_409_without_baseline(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    target_run = create_check_run(client, project["id"], headers)
    record_scored_terminal_run(target_run["id"], response_time_ms=500, performance_score=90)

    response = client.get(
        f"/projects/{project['id']}/check-runs/{target_run['id']}/baseline-comparison",
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "No baseline check run is configured for this project."


def test_get_baseline_comparison_with_explicit_baseline_param(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    baseline_run = create_check_run(client, project["id"], headers)
    record_scored_terminal_run(baseline_run["id"], response_time_ms=900, performance_score=70)
    target_run = create_check_run(client, project["id"], headers)
    record_scored_terminal_run(target_run["id"], response_time_ms=500, performance_score=90)

    response = client.get(
        f"/projects/{project['id']}/check-runs/{target_run['id']}/baseline-comparison",
        params={"baseline_check_run_id": baseline_run["id"]},
        headers=headers,
    )

    assert response.status_code == 200
    comparison = response.json()
    assert comparison["baseline_check_run_id"] == baseline_run["id"]
    assert comparison["response_time_delta_ms"] == -400


def test_other_user_cannot_read_baseline_comparison(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_verified_project(client, headers)
    target_run = create_check_run(client, project["id"], headers)
    record_scored_terminal_run(target_run["id"], response_time_ms=500, performance_score=90)
    other_headers = authenticated_headers(client, email="intruder@example.com")

    response = client.get(
        f"/projects/{project['id']}/check-runs/{target_run['id']}/baseline-comparison",
        headers=other_headers,
    )

    assert response.status_code == 404
