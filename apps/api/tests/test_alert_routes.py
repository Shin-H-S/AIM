from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base, get_db
from aim_api.main import app
from aim_api.models.alert import (
    Alert,
    AlertChannel,
    AlertStatus,
    AlertType,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentTriggerType,
)
from aim_api.models.check_run import CheckRun, CheckRunStatus
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


def record_incident_and_alert(
    *,
    project_id: str,
    owner_id: str,
    alert_status: AlertStatus = AlertStatus.PENDING,
    delivery_attempts: int = 0,
    last_error: str | None = None,
    sent_at: datetime | None = None,
) -> dict[str, str]:
    with get_testing_session() as session:
        check_run = CheckRun(
            project_id=UUID(project_id),
            requested_by_id=UUID(owner_id),
            status=CheckRunStatus.COMPLETED.value,
            finished_at=datetime(2026, 7, 3, 1, tzinfo=UTC),
        )
        session.add(check_run)
        session.flush()

        incident = Incident(
            project_id=UUID(project_id),
            opened_check_run_id=check_run.id,
            trigger_type=IncidentTriggerType.SERVICE_CONNECTION_FAILURE.value,
            severity=IncidentSeverity.RISK.value,
            status=IncidentStatus.OPEN.value,
            title="Service connection failed",
            summary="The service could not be reached.",
            evidence_json={
                "check_run_id": str(check_run.id),
                "failure_reason": "connection refused",
            },
            started_at=datetime(2026, 7, 3, 1, 1, tzinfo=UTC),
        )
        session.add(incident)
        session.flush()

        alert = Alert(
            project_id=UUID(project_id),
            incident_id=incident.id,
            check_run_id=check_run.id,
            alert_type=AlertType.INCIDENT_OPENED.value,
            trigger_type=incident.trigger_type,
            channel=AlertChannel.EMAIL.value,
            status=alert_status.value,
            recipient_email="owner@example.com",
            subject="[AIM] AIM Website: Service connection failed",
            body="Project: AIM Website\nIncident: Service connection failed",
            delivery_attempts=delivery_attempts,
            last_error=last_error,
            sent_at=sent_at,
        )
        session.add(alert)
        session.commit()

        return {
            "check_run_id": str(check_run.id),
            "incident_id": str(incident.id),
            "alert_id": str(alert.id),
        }


def test_list_project_incidents_requires_authentication(client: TestClient) -> None:
    response = client.get(f"/projects/{uuid4()}/incidents")

    assert response.status_code == 401


def test_list_project_incidents(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    records = record_incident_and_alert(project_id=project["id"], owner_id=project["owner_id"])

    response = client.get(f"/projects/{project['id']}/incidents", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == records["incident_id"]
    assert body[0]["project_id"] == project["id"]
    assert body[0]["opened_check_run_id"] == records["check_run_id"]
    assert body[0]["trigger_type"] == "SERVICE_CONNECTION_FAILURE"
    assert body[0]["severity"] == "RISK"
    assert body[0]["status"] == "OPEN"
    assert body[0]["title"] == "Service connection failed"
    assert body[0]["evidence_json"]["failure_reason"] == "connection refused"


def test_list_project_alerts(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    records = record_incident_and_alert(project_id=project["id"], owner_id=project["owner_id"])

    response = client.get(f"/projects/{project['id']}/alerts", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == records["alert_id"]
    assert body[0]["project_id"] == project["id"]
    assert body[0]["incident_id"] == records["incident_id"]
    assert body[0]["check_run_id"] == records["check_run_id"]
    assert body[0]["alert_type"] == "INCIDENT_OPENED"
    assert body[0]["channel"] == "EMAIL"
    assert body[0]["status"] == "PENDING"
    assert body[0]["recipient_email"] == "owner@example.com"
    assert body[0]["delivery_attempts"] == 0


def test_retry_failed_project_alert_queues_delivery(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued_alert_ids: list[str] = []

    def fake_enqueue_email_alert_retry(*, alert_id: UUID) -> str:
        queued_alert_ids.append(str(alert_id))
        return f"email-alert-retry:{alert_id}"

    monkeypatch.setattr(scan_queue, "enqueue_email_alert_retry", fake_enqueue_email_alert_retry)
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    records = record_incident_and_alert(
        project_id=project["id"],
        owner_id=project["owner_id"],
        alert_status=AlertStatus.FAILED,
        delivery_attempts=1,
        last_error="SMTP server unavailable",
    )

    response = client.post(
        f"/projects/{project['id']}/alerts/{records['alert_id']}/retry",
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == records["alert_id"]
    assert body["status"] == "PENDING"
    assert body["delivery_attempts"] == 1
    assert body["last_error"] is None
    assert body["sent_at"] is None
    assert queued_alert_ids == [records["alert_id"]]


def test_retry_project_alert_rejects_non_failed_alert(client: TestClient) -> None:
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    records = record_incident_and_alert(project_id=project["id"], owner_id=project["owner_id"])

    response = client.post(
        f"/projects/{project['id']}/alerts/{records['alert_id']}/retry",
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Only failed alerts can be retried."}


def test_retry_project_alert_restores_failed_status_when_queue_is_unavailable(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_enqueue_email_alert_retry(*, alert_id: UUID) -> str:
        _ = alert_id
        raise scan_queue.ScanQueueUnavailableError

    monkeypatch.setattr(scan_queue, "enqueue_email_alert_retry", fake_enqueue_email_alert_retry)
    headers = authenticated_headers(client)
    project = create_project(client, headers)
    records = record_incident_and_alert(
        project_id=project["id"],
        owner_id=project["owner_id"],
        alert_status=AlertStatus.FAILED,
        delivery_attempts=1,
        last_error="SMTP server unavailable",
    )

    response = client.post(
        f"/projects/{project['id']}/alerts/{records['alert_id']}/retry",
        headers=headers,
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "Alert delivery queue is unavailable."}

    with get_testing_session() as session:
        alert = session.get(Alert, UUID(records["alert_id"]))
        assert alert is not None
        assert alert.status == AlertStatus.FAILED.value
        assert alert.delivery_attempts == 1
        assert alert.last_error == "Alert delivery queue is unavailable."


def test_other_user_cannot_retry_project_alert(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queued_alert_ids: list[str] = []

    def fake_enqueue_email_alert_retry(*, alert_id: UUID) -> str:
        queued_alert_ids.append(str(alert_id))
        return f"email-alert-retry:{alert_id}"

    monkeypatch.setattr(scan_queue, "enqueue_email_alert_retry", fake_enqueue_email_alert_retry)
    owner_headers = authenticated_headers(client, "owner@example.com")
    other_headers = authenticated_headers(client, "other@example.com")
    project = create_project(client, owner_headers)
    records = record_incident_and_alert(
        project_id=project["id"],
        owner_id=project["owner_id"],
        alert_status=AlertStatus.FAILED,
        delivery_attempts=1,
        last_error="SMTP server unavailable",
    )

    response = client.post(
        f"/projects/{project['id']}/alerts/{records['alert_id']}/retry",
        headers=other_headers,
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found."}
    assert queued_alert_ids == []


def test_other_user_cannot_list_project_incidents_or_alerts(client: TestClient) -> None:
    owner_headers = authenticated_headers(client, "owner@example.com")
    other_headers = authenticated_headers(client, "other@example.com")
    project = create_project(client, owner_headers)
    record_incident_and_alert(project_id=project["id"], owner_id=project["owner_id"])

    incidents_response = client.get(f"/projects/{project['id']}/incidents", headers=other_headers)
    alerts_response = client.get(f"/projects/{project['id']}/alerts", headers=other_headers)

    assert incidents_response.status_code == 404
    assert incidents_response.json() == {"detail": "Project not found."}
    assert alerts_response.status_code == 404
    assert alerts_response.json() == {"detail": "Project not found."}
