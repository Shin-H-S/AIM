from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.user import User
from aim_worker import tasks
from aim_worker.availability import AvailabilityScanResult
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(tasks, "SessionLocal", testing_session_local)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as testing_session:
        yield testing_session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_check_run(
    session: Session,
    *,
    status: CheckRunStatus,
    service_url: str = "https://example.com",
) -> CheckRun:
    user = User(email=f"{uuid4()}@example.com", password_hash="hashed-password")
    session.add(user)
    session.flush()
    project = Project(
        owner_id=user.id,
        name="AIM Website",
        service_url=service_url,
        verified_at=datetime.now(UTC),
        environment="production",
    )
    session.add(project)
    session.flush()
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=user.id,
        status=status.value,
        trigger_source="manual",
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)
    return check_run


def available_result(service_url: str) -> AvailabilityScanResult:
    return AvailabilityScanResult(
        service_url=service_url,
        final_url=service_url,
        is_available=True,
        status_code=200,
        response_time_ms=123,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
        failure_reason=None,
    )


def unavailable_result(service_url: str) -> AvailabilityScanResult:
    return AvailabilityScanResult(
        service_url=service_url,
        final_url=service_url,
        is_available=False,
        status_code=503,
        response_time_ms=123,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
        failure_reason="Service returned HTTP 503.",
    )


def test_run_check_run_completes_when_availability_scan_succeeds(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_run = create_check_run(session, status=CheckRunStatus.QUEUED)
    scanned_urls: list[str] = []

    def fake_scan(service_url: str) -> AvailabilityScanResult:
        scanned_urls.append(service_url)
        return available_result(service_url)

    monkeypatch.setattr(tasks, "scan_http_availability", fake_scan)

    tasks.run_check_run.run(str(check_run.id))

    session.refresh(check_run)
    assert scanned_urls == ["https://example.com"]
    assert check_run.status == CheckRunStatus.COMPLETED.value
    assert check_run.started_at is not None
    assert check_run.finished_at is not None
    assert check_run.failure_reason is None


def test_run_check_run_fails_when_availability_scan_fails(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_run = create_check_run(session, status=CheckRunStatus.QUEUED)

    def fake_scan(service_url: str) -> AvailabilityScanResult:
        return unavailable_result(service_url)

    monkeypatch.setattr(tasks, "scan_http_availability", fake_scan)

    tasks.run_check_run.run(str(check_run.id))

    session.refresh(check_run)
    assert check_run.status == CheckRunStatus.FAILED.value
    assert check_run.failure_reason == "Service returned HTTP 503."
    assert check_run.finished_at is not None


def test_run_check_run_does_not_override_cancelled_run(session: Session) -> None:
    check_run = create_check_run(session, status=CheckRunStatus.CANCELLED)

    tasks.run_check_run.run(str(check_run.id))

    session.refresh(check_run)
    assert check_run.status == CheckRunStatus.CANCELLED.value
    assert check_run.started_at is None
    assert check_run.finished_at is None
    assert check_run.failure_reason is None


def test_run_check_run_records_unexpected_scan_failure(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_run = create_check_run(session, status=CheckRunStatus.QUEUED)

    def fail_scan(service_url: str) -> None:
        _ = service_url
        raise RuntimeError("browser crashed")

    monkeypatch.setattr(tasks, "scan_http_availability", fail_scan)

    with pytest.raises(RuntimeError, match="browser crashed"):
        tasks.run_check_run.run(str(check_run.id))

    session.refresh(check_run)
    assert check_run.status == CheckRunStatus.FAILED.value
    assert check_run.failure_reason == tasks.SCAN_WORKER_FAILED_REASON
    assert check_run.finished_at is not None


def test_run_check_run_ignores_missing_check_run(session: Session) -> None:
    _ = session

    tasks.run_check_run.run(str(uuid4()))
