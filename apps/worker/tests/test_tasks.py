from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import (
    Artifact,
    AvailabilityResult,
    LighthouseResult,
    RunComparison,
    ScoreResult,
    SslResult,
)
from aim_api.models.scenario import (
    ConsoleError,
    NetworkFailure,
    ScenarioRun,
    ScenarioRunStatus,
    StepResult,
    StepResultStatus,
    TestScenario,
    TestStep,
)
from aim_api.models.user import User
from aim_api.services import scanner_results, score_results
from aim_worker import tasks
from aim_worker.artifacts import StoredArtifact
from aim_worker.availability import AvailabilityScanResult
from aim_worker.lighthouse import LighthouseScanResult
from aim_worker.playwright_runner import (
    ConsoleErrorEvidence,
    ExecutedStepResult,
    NetworkFailureEvidence,
    ScenarioExecutionResult,
)
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

    def fake_store_binary_artifact(
        *,
        artifact_type: str,
        storage_path: str,
        content_type: str,
        payload: bytes,
    ) -> StoredArtifact:
        return StoredArtifact(
            artifact_type=artifact_type,
            storage_backend="local",
            storage_path=storage_path,
            content_type=content_type,
            size_bytes=len(payload),
            checksum_sha256="b" * 64,
        )

    monkeypatch.setattr(tasks, "store_binary_artifact", fake_store_binary_artifact)


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


def create_scenario_run(
    session: Session,
    *,
    status: ScenarioRunStatus,
) -> ScenarioRun:
    user = User(email=f"{uuid4()}@example.com", password_hash="hashed-password")
    session.add(user)
    session.flush()
    project = Project(
        owner_id=user.id,
        name="AIM Website",
        service_url="https://example.com",
        verified_at=datetime.now(UTC),
        environment="production",
    )
    session.add(project)
    session.flush()
    scenario = TestScenario(
        project_id=project.id,
        name="Login flow",
        description="Critical login flow",
        is_active=True,
    )
    session.add(scenario)
    session.flush()
    step = TestStep(
        scenario_id=scenario.id,
        step_order=1,
        action="navigate",
        target="https://example.com/login",
        value=None,
        timeout_ms=None,
        is_critical=True,
    )
    session.add(step)
    session.flush()
    scenario_run = ScenarioRun(
        project_id=project.id,
        scenario_id=scenario.id,
        requested_by_id=user.id,
        status=status.value,
        trigger_source="manual",
    )
    session.add(scenario_run)
    session.commit()
    session.refresh(scenario_run)
    return scenario_run


def record_completed_baseline_result(
    session: Session,
    *,
    check_run: CheckRun,
    response_time_ms: int = 700,
    performance_score: int = 80,
) -> None:
    project = session.get(Project, check_run.project_id)
    assert project is not None
    availability_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url=project.service_url,
        final_url=project.service_url,
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
        service_url=project.service_url,
        is_applicable=True,
        is_valid=True,
        expires_at=datetime(2027, 6, 26, tzinfo=UTC),
        days_until_expiration=365,
        failure_reason=None,
    )
    lighthouse_result = scanner_results.record_lighthouse_result(
        session,
        check_run_id=check_run.id,
        service_url=project.service_url,
        is_successful=True,
        performance_score=performance_score,
        accessibility_score=95,
        seo_score=88,
        best_practices_score=92,
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
    score_result = session.scalars(select(ScoreResult)).one()
    assert score_result.check_run_id == check_run.id
    assert score_result.overall_score == 95
    assert score_result.grade == "A"
    assert score_result.deployment_risk == "STABLE"
    assert session.scalars(select(RunComparison)).all() == []


def test_run_check_run_records_previous_run_comparison(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_run = create_check_run(session, status=CheckRunStatus.COMPLETED)
    baseline_run.created_at = datetime(2026, 6, 27, 1, tzinfo=UTC)
    baseline_run.queued_at = baseline_run.created_at
    baseline_run.finished_at = baseline_run.created_at
    session.commit()
    record_completed_baseline_result(session, check_run=baseline_run)
    check_run = CheckRun(
        project_id=baseline_run.project_id,
        requested_by_id=baseline_run.requested_by_id,
        status=CheckRunStatus.QUEUED.value,
        trigger_source="manual",
        created_at=datetime(2026, 6, 27, 2, tzinfo=UTC),
        queued_at=datetime(2026, 6, 27, 2, tzinfo=UTC),
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)

    def fake_scan(service_url: str) -> AvailabilityScanResult:
        return available_result(service_url)

    monkeypatch.setattr(tasks, "scan_http_availability", fake_scan)

    tasks.run_check_run.run(str(check_run.id))

    comparison = session.scalars(select(RunComparison)).one()
    assert comparison.check_run_id == check_run.id
    assert comparison.baseline_check_run_id == baseline_run.id
    assert comparison.overall_score_delta == 3
    assert comparison.performance_score_delta == 10
    assert comparison.response_time_delta_ms == -577
    assert comparison.deployment_risk_changed is False


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
    score_result = session.scalars(select(ScoreResult)).one()
    assert score_result.overall_score == 42
    assert score_result.grade == "F"
    assert score_result.deployment_risk == "RISK"
    assert score_result.gate_reason == "Lighthouse CLI failed."


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
    score_result = session.scalars(select(ScoreResult)).one()
    assert score_result.deployment_risk == "RISK"
    assert score_result.grade == "D"
    assert score_result.gate_reason == "SSL certificate is expired."


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
    score_result = session.scalars(select(ScoreResult)).one()
    assert score_result.overall_score == 0
    assert score_result.grade == "F"
    assert score_result.deployment_risk == "RISK"


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


def test_run_scenario_run_records_successful_execution(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_run = create_scenario_run(session, status=ScenarioRunStatus.QUEUED)
    step = session.scalars(select(TestStep)).one()

    def fake_run_playwright_scenario(steps: list[TestStep]) -> ScenarioExecutionResult:
        assert [scenario_step.id for scenario_step in steps] == [step.id]
        return ScenarioExecutionResult(
            is_successful=True,
            failure_reason=None,
            step_results=[
                ExecutedStepResult(
                    test_step_id=step.id,
                    step_order=1,
                    action="navigate",
                    target="https://example.com/login",
                    status=StepResultStatus.PASSED,
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                    duration_ms=12,
                    error_message=None,
                )
            ],
            console_errors=[
                ConsoleErrorEvidence(
                    level="error",
                    message="Client crashed",
                    source_url="https://example.com/app.js",
                    line_number=10,
                    column_number=2,
                )
            ],
            network_failures=[
                NetworkFailureEvidence(
                    request_url="https://example.com/api",
                    method="GET",
                    resource_type="fetch",
                    failure_text="net::ERR_FAILED",
                )
            ],
        )

    monkeypatch.setattr(tasks, "run_playwright_scenario", fake_run_playwright_scenario)

    tasks.run_scenario_run.run(str(scenario_run.id))

    session.refresh(scenario_run)
    assert scenario_run.status == ScenarioRunStatus.COMPLETED.value
    assert scenario_run.started_at is not None
    assert scenario_run.finished_at is not None
    assert scenario_run.failure_reason is None
    step_result = session.scalars(select(StepResult)).one()
    assert step_result.scenario_run_id == scenario_run.id
    assert step_result.test_step_id == step.id
    assert step_result.status == StepResultStatus.PASSED.value
    assert step_result.duration_ms == 12
    console_error = session.scalars(select(ConsoleError)).one()
    assert console_error.scenario_run_id == scenario_run.id
    assert console_error.message == "Client crashed"
    assert console_error.source_url == "https://example.com/app.js"
    network_failure = session.scalars(select(NetworkFailure)).one()
    assert network_failure.scenario_run_id == scenario_run.id
    assert network_failure.request_url == "https://example.com/api"
    assert network_failure.failure_text == "net::ERR_FAILED"


def test_run_scenario_run_records_failed_execution(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_run = create_scenario_run(session, status=ScenarioRunStatus.QUEUED)
    step = session.scalars(select(TestStep)).one()

    def fake_run_playwright_scenario(steps: list[TestStep]) -> ScenarioExecutionResult:
        assert [scenario_step.id for scenario_step in steps] == [step.id]
        return ScenarioExecutionResult(
            is_successful=False,
            failure_reason="Expected element was not found.",
            step_results=[
                ExecutedStepResult(
                    test_step_id=step.id,
                    step_order=1,
                    action="assert_element_exists",
                    target="#dashboard",
                    status=StepResultStatus.FAILED,
                    started_at=datetime.now(UTC),
                    finished_at=datetime.now(UTC),
                    duration_ms=20,
                    error_message="Expected element was not found.",
                    failure_screenshot=b"fake-png",
                )
            ],
            console_errors=[],
            network_failures=[],
        )

    monkeypatch.setattr(tasks, "run_playwright_scenario", fake_run_playwright_scenario)

    tasks.run_scenario_run.run(str(scenario_run.id))

    session.refresh(scenario_run)
    assert scenario_run.status == ScenarioRunStatus.FAILED.value
    assert scenario_run.failure_reason == "Expected element was not found."
    step_result = session.scalars(select(StepResult)).one()
    assert step_result.status == StepResultStatus.FAILED.value
    assert step_result.error_message == "Expected element was not found."
    assert step_result.failure_screenshot_artifact_id is not None
    artifact = session.get(Artifact, step_result.failure_screenshot_artifact_id)
    assert artifact is not None
    assert artifact.check_run_id is None
    assert artifact.scenario_run_id == scenario_run.id
    assert artifact.artifact_type == "scenario_failure_screenshot"
    assert artifact.storage_path == f"scenario-runs/{scenario_run.id}/steps/1/failure.png"
    assert artifact.content_type == "image/png"
    assert artifact.size_bytes == len(b"fake-png")


def test_run_scenario_run_records_unexpected_runner_failure(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_run = create_scenario_run(session, status=ScenarioRunStatus.QUEUED)

    def fake_run_playwright_scenario(steps: list[TestStep]) -> ScenarioExecutionResult:
        _ = steps
        raise RuntimeError("browser crashed")

    monkeypatch.setattr(tasks, "run_playwright_scenario", fake_run_playwright_scenario)

    with pytest.raises(RuntimeError, match="browser crashed"):
        tasks.run_scenario_run.run(str(scenario_run.id))

    session.refresh(scenario_run)
    assert scenario_run.status == ScenarioRunStatus.FAILED.value
    assert scenario_run.failure_reason == tasks.SCENARIO_WORKER_FAILED_REASON
    assert scenario_run.finished_at is not None
    assert session.scalars(select(StepResult)).all() == []


def test_run_scenario_run_does_not_override_cancelled_run(session: Session) -> None:
    scenario_run = create_scenario_run(session, status=ScenarioRunStatus.CANCELLED)

    tasks.run_scenario_run.run(str(scenario_run.id))

    session.refresh(scenario_run)
    assert scenario_run.status == ScenarioRunStatus.CANCELLED.value
    assert scenario_run.started_at is None
    assert scenario_run.finished_at is None
    assert scenario_run.failure_reason is None


def test_run_scenario_run_ignores_missing_scenario_run(session: Session) -> None:
    _ = session

    tasks.run_scenario_run.run(str(uuid4()))
