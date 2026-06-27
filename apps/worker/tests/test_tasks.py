from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import Artifact, AvailabilityResult, LighthouseResult, SslResult
from aim_api.models.user import User
from aim_worker import tasks
from aim_worker.artifacts import StoredArtifact
from aim_worker.availability import AvailabilityScanResult
from aim_worker.lighthouse import LighthouseScanResult
from aim_worker.ssl_inspection import SslInspectionResult
from sqlalchemy import create_engine, select
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


@pytest.fixture(autouse=True)
def ssl_inspection(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_inspect_ssl_certificate(service_url: str) -> SslInspectionResult:
        return valid_ssl_result(service_url)

    monkeypatch.setattr(tasks, "inspect_ssl_certificate", fake_inspect_ssl_certificate)


@pytest.fixture(autouse=True)
def lighthouse_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_lighthouse_scan(service_url: str) -> LighthouseScanResult:
        return successful_lighthouse_result(service_url)

    monkeypatch.setattr(tasks, "run_lighthouse_scan", fake_run_lighthouse_scan)


@pytest.fixture(autouse=True)
def artifact_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_store_json_artifact(
        *,
        check_run_id: UUID,
        artifact_type: str,
        payload: dict[str, object],
        relative_path: str,
    ) -> StoredArtifact:
        _ = payload
        return StoredArtifact(
            artifact_type=artifact_type,
            storage_backend="local",
            storage_path=f"check-runs/{check_run_id}/{relative_path}",
            content_type="application/json",
            size_bytes=17,
            checksum_sha256="a" * 64,
        )

    monkeypatch.setattr(tasks, "store_json_artifact", fake_store_json_artifact)


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


def valid_ssl_result(service_url: str) -> SslInspectionResult:
    return SslInspectionResult(
        service_url=service_url,
        is_applicable=service_url.startswith("https://"),
        is_valid=True,
        expires_at=datetime(2027, 6, 26, tzinfo=UTC),
        days_until_expiration=365,
        failure_reason=None,
    )


def invalid_ssl_result(service_url: str) -> SslInspectionResult:
    return SslInspectionResult(
        service_url=service_url,
        is_applicable=True,
        is_valid=False,
        expires_at=datetime(2025, 6, 26, tzinfo=UTC),
        days_until_expiration=-365,
        failure_reason="SSL certificate is expired.",
    )


def successful_lighthouse_result(service_url: str) -> LighthouseScanResult:
    return LighthouseScanResult(
        service_url=service_url,
        is_successful=True,
        performance_score=90,
        accessibility_score=95,
        seo_score=88,
        best_practices_score=92,
        largest_contentful_paint_ms=1200,
        cumulative_layout_shift=0.02,
        total_blocking_time_ms=30,
        raw_json={"categories": {}},
        failure_reason=None,
    )


def failed_lighthouse_result(service_url: str) -> LighthouseScanResult:
    return LighthouseScanResult(
        service_url=service_url,
        is_successful=False,
        performance_score=None,
        accessibility_score=None,
        seo_score=None,
        best_practices_score=None,
        largest_contentful_paint_ms=None,
        cumulative_layout_shift=None,
        total_blocking_time_ms=None,
        raw_json=None,
        failure_reason="Lighthouse CLI failed.",
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
    availability_result = session.scalars(select(AvailabilityResult)).one()
    assert availability_result.check_run_id == check_run.id
    assert availability_result.is_available is True
    assert availability_result.status_code == 200
    ssl_result = session.scalars(select(SslResult)).one()
    assert ssl_result.check_run_id == check_run.id
    assert ssl_result.is_applicable is True
    assert ssl_result.is_valid is True
    lighthouse_result = session.scalars(select(LighthouseResult)).one()
    assert lighthouse_result.check_run_id == check_run.id
    assert lighthouse_result.is_successful is True
    assert lighthouse_result.performance_score == 90
    artifact = session.scalars(select(Artifact)).one()
    assert artifact.check_run_id == check_run.id
    assert artifact.artifact_type == "lighthouse_raw_json"
    assert artifact.storage_path == f"check-runs/{check_run.id}/lighthouse/raw.json"
    assert lighthouse_result.raw_json_artifact_id == artifact.id


def test_run_check_run_fails_when_lighthouse_scan_fails(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_run = create_check_run(session, status=CheckRunStatus.QUEUED)

    def fake_scan(service_url: str) -> AvailabilityScanResult:
        return available_result(service_url)

    def fake_run_lighthouse_scan(service_url: str) -> LighthouseScanResult:
        return failed_lighthouse_result(service_url)

    monkeypatch.setattr(tasks, "scan_http_availability", fake_scan)
    monkeypatch.setattr(tasks, "run_lighthouse_scan", fake_run_lighthouse_scan)

    tasks.run_check_run.run(str(check_run.id))

    session.refresh(check_run)
    assert check_run.status == CheckRunStatus.FAILED.value
    assert check_run.failure_reason == "Lighthouse CLI failed."
    assert check_run.finished_at is not None
    lighthouse_result = session.scalars(select(LighthouseResult)).one()
    assert lighthouse_result.is_successful is False
    assert lighthouse_result.failure_reason == "Lighthouse CLI failed."
    assert session.scalars(select(Artifact)).all() == []


def test_run_check_run_records_unexpected_artifact_storage_failure(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_run = create_check_run(session, status=CheckRunStatus.QUEUED)

    def fake_scan(service_url: str) -> AvailabilityScanResult:
        return available_result(service_url)

    def fail_store_json_artifact(
        *,
        check_run_id: UUID,
        artifact_type: str,
        payload: dict[str, object],
        relative_path: str,
    ) -> StoredArtifact:
        _ = check_run_id, artifact_type, payload, relative_path
        raise OSError("disk full")

    monkeypatch.setattr(tasks, "scan_http_availability", fake_scan)
    monkeypatch.setattr(tasks, "store_json_artifact", fail_store_json_artifact)

    with pytest.raises(OSError, match="disk full"):
        tasks.run_check_run.run(str(check_run.id))

    session.refresh(check_run)
    assert check_run.status == CheckRunStatus.FAILED.value
    assert check_run.failure_reason == tasks.SCAN_WORKER_FAILED_REASON
    assert check_run.finished_at is not None
    assert session.scalars(select(LighthouseResult)).all() == []
    assert session.scalars(select(Artifact)).all() == []


def test_run_check_run_fails_when_ssl_inspection_fails(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_run = create_check_run(session, status=CheckRunStatus.QUEUED)

    def fake_scan(service_url: str) -> AvailabilityScanResult:
        return available_result(service_url)

    def fake_inspect_ssl_certificate(service_url: str) -> SslInspectionResult:
        return invalid_ssl_result(service_url)

    monkeypatch.setattr(tasks, "scan_http_availability", fake_scan)
    monkeypatch.setattr(tasks, "inspect_ssl_certificate", fake_inspect_ssl_certificate)

    tasks.run_check_run.run(str(check_run.id))

    session.refresh(check_run)
    assert check_run.status == CheckRunStatus.FAILED.value
    assert check_run.failure_reason == "SSL certificate is expired."
    assert check_run.finished_at is not None
    availability_result = session.scalars(select(AvailabilityResult)).one()
    assert availability_result.is_available is True
    ssl_result = session.scalars(select(SslResult)).one()
    assert ssl_result.is_valid is False
    assert ssl_result.failure_reason == "SSL certificate is expired."


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
    availability_result = session.scalars(select(AvailabilityResult)).one()
    assert availability_result.is_available is False
    assert availability_result.status_code == 503
    assert availability_result.failure_reason == "Service returned HTTP 503."
    assert session.scalars(select(SslResult)).all() == []


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
