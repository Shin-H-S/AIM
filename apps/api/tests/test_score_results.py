from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import ScoreResult
from aim_api.models.scenario import (
    ScenarioRun,
    ScenarioRunStatus,
    StepResult,
    StepResultStatus,
    TestScenario,
    TestStep,
)
from aim_api.models.user import User
from aim_api.services import scanner_results, score_results
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with testing_session_local() as testing_session:
        yield testing_session

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_check_run(session: Session) -> tuple[Project, CheckRun]:
    user = User(email=f"{uuid4()}@example.com", password_hash="hashed-password")
    session.add(user)
    session.flush()
    project = Project(
        owner_id=user.id,
        name="AIM Website",
        service_url="https://example.com",
        verified_at=datetime.now(UTC),
        environment="production",
        response_time_threshold_ms=1_000,
        quality_score_threshold=80,
    )
    session.add(project)
    session.flush()
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=user.id,
        status=CheckRunStatus.RUNNING.value,
        trigger_source="manual",
    )
    session.add(check_run)
    session.commit()
    session.refresh(project)
    session.refresh(check_run)
    return project, check_run


def create_scenario_run(
    session: Session,
    *,
    project: Project,
    status: ScenarioRunStatus,
    step_status: StepResultStatus,
    failure_reason: str | None = None,
) -> ScenarioRun:
    scenario = TestScenario(
        project_id=project.id,
        name=f"Login flow {uuid4()}",
        description=None,
        is_active=True,
    )
    session.add(scenario)
    session.flush()
    step = TestStep(
        scenario_id=scenario.id,
        step_order=1,
        action="assert_element_exists",
        target="#dashboard",
        value=None,
        timeout_ms=None,
        is_critical=True,
    )
    session.add(step)
    session.flush()
    scenario_run = ScenarioRun(
        project_id=project.id,
        scenario_id=scenario.id,
        requested_by_id=project.owner_id,
        status=status.value,
        trigger_source="manual",
        failure_reason=failure_reason,
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_ms=25,
    )
    session.add(scenario_run)
    session.flush()
    session.add(
        StepResult(
            scenario_run_id=scenario_run.id,
            test_step_id=step.id,
            step_order=1,
            action=step.action,
            target=step.target,
            status=step_status.value,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            duration_ms=25,
            error_message=failure_reason if step_status == StepResultStatus.FAILED else None,
        )
    )
    session.commit()
    session.refresh(scenario_run)
    return scenario_run


def test_record_score_result_calculates_stable_partial_score(session: Session) -> None:
    project, check_run = create_check_run(session)
    availability_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        final_url="https://example.com",
        is_available=True,
        status_code=200,
        response_time_ms=500,
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
        performance_score=90,
        accessibility_score=95,
        seo_score=80,
        best_practices_score=100,
        largest_contentful_paint_ms=1200,
        cumulative_layout_shift=0.02,
        total_blocking_time_ms=30,
        raw_json_artifact_id=None,
        failure_reason=None,
    )

    result = score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=ssl_result,
        lighthouse_result=lighthouse_result,
    )

    assert result.overall_score == 95
    assert result.evaluated_weight == 60
    assert result.grade == "A"
    assert result.deployment_risk == "STABLE"
    assert result.gate_reason is None
    assert result.functional_stability_score is None
    assert result.regression_stability_score is None


def test_record_score_result_includes_successful_scenario_score(session: Session) -> None:
    project, check_run = create_check_run(session)
    create_scenario_run(
        session,
        project=project,
        status=ScenarioRunStatus.COMPLETED,
        step_status=StepResultStatus.PASSED,
    )
    availability_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        final_url="https://example.com",
        is_available=True,
        status_code=200,
        response_time_ms=500,
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
        performance_score=90,
        accessibility_score=95,
        seo_score=80,
        best_practices_score=100,
        largest_contentful_paint_ms=1200,
        cumulative_layout_shift=0.02,
        total_blocking_time_ms=30,
        raw_json_artifact_id=None,
        failure_reason=None,
    )

    result = score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=ssl_result,
        lighthouse_result=lighthouse_result,
    )

    assert result.functional_stability_score == 100
    assert result.overall_score == 97
    assert result.evaluated_weight == 90
    assert result.deployment_risk == "STABLE"
    assert result.gate_reason is None


def test_record_score_result_marks_failed_scenario_as_deployment_risk(
    session: Session,
) -> None:
    project, check_run = create_check_run(session)
    create_scenario_run(
        session,
        project=project,
        status=ScenarioRunStatus.FAILED,
        step_status=StepResultStatus.FAILED,
        failure_reason="Expected dashboard element was not found.",
    )
    availability_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        final_url="https://example.com",
        is_available=True,
        status_code=200,
        response_time_ms=500,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
        failure_reason=None,
    )

    result = score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=None,
        lighthouse_result=None,
    )

    assert result.functional_stability_score == 0
    assert result.overall_score == 45
    assert result.evaluated_weight == 55
    assert result.grade == "F"
    assert result.deployment_risk == "RISK"
    assert result.gate_reason == "Expected dashboard element was not found."


def test_record_score_result_marks_unavailable_service_as_risk(session: Session) -> None:
    project, check_run = create_check_run(session)
    availability_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        final_url=None,
        is_available=False,
        status_code=503,
        response_time_ms=None,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
        failure_reason="Service returned HTTP 503.",
    )

    result = score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=None,
        lighthouse_result=None,
    )

    assert result.availability_score == 0
    assert result.overall_score == 0
    assert result.evaluated_weight == 25
    assert result.grade == "F"
    assert result.deployment_risk == "RISK"
    assert result.gate_reason == "Service returned HTTP 503."


def test_record_score_result_caps_grade_for_slow_response(session: Session) -> None:
    project, check_run = create_check_run(session)
    availability_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        final_url="https://example.com",
        is_available=True,
        status_code=200,
        response_time_ms=2_500,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
        failure_reason=None,
    )

    result = score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=None,
        lighthouse_result=None,
    )

    assert result.availability_score == 60
    assert result.overall_score == 60
    assert result.grade == "D"
    assert result.deployment_risk == "WARNING"
    assert result.gate_reason == "Response time is over twice the configured threshold."


def test_record_score_result_updates_existing_result(session: Session) -> None:
    project, check_run = create_check_run(session)
    first_result = score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=None,
        ssl_result=None,
        lighthouse_result=None,
    )
    availability_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url="https://example.com",
        final_url="https://example.com",
        is_available=True,
        status_code=200,
        response_time_ms=500,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
        failure_reason=None,
    )
    second_result = score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=None,
        lighthouse_result=None,
    )

    assert second_result.id == first_result.id
    assert session.scalars(select(ScoreResult)).all() == [second_result]
    assert second_result.overall_score == 100
    assert second_result.deployment_risk == "STABLE"
