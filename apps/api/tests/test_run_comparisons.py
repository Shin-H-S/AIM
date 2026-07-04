from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import (
    AvailabilityResult,
    LighthouseResult,
    RunComparison,
    ScoreResult,
)
from aim_api.models.user import User
from aim_api.services import run_comparisons, scanner_results, score_results
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


def create_project(session: Session) -> tuple[User, Project]:
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
    session.commit()
    session.refresh(user)
    session.refresh(project)
    return user, project


def create_check_run(
    session: Session,
    *,
    project: Project,
    user: User,
    status: CheckRunStatus,
    created_at: datetime,
) -> CheckRun:
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=user.id,
        status=status.value,
        trigger_source="manual",
        created_at=created_at,
        queued_at=created_at,
        started_at=created_at,
        finished_at=created_at if status in terminal_statuses() else None,
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)
    return check_run


def terminal_statuses() -> set[CheckRunStatus]:
    return {
        CheckRunStatus.COMPLETED,
        CheckRunStatus.FAILED,
        CheckRunStatus.CANCELLED,
    }


def record_scan_outputs(
    session: Session,
    *,
    project: Project,
    check_run: CheckRun,
    response_time_ms: int,
    performance_score: int,
) -> tuple[AvailabilityResult, LighthouseResult, ScoreResult]:
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
    score_result = score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=ssl_result,
        lighthouse_result=lighthouse_result,
    )
    return availability_result, lighthouse_result, score_result


def test_record_previous_run_comparison_returns_none_without_baseline(session: Session) -> None:
    user, project = create_project(session)
    check_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 1, tzinfo=UTC),
    )
    availability_result, lighthouse_result, score_result = record_scan_outputs(
        session,
        project=project,
        check_run=check_run,
        response_time_ms=500,
        performance_score=90,
    )

    comparison = run_comparisons.record_previous_run_comparison(
        session,
        check_run=check_run,
        current_score_result=score_result,
        current_availability_result=availability_result,
        current_lighthouse_result=lighthouse_result,
    )

    assert comparison is None
    assert session.scalars(select(RunComparison)).all() == []


def test_record_previous_run_comparison_stores_metric_deltas(session: Session) -> None:
    user, project = create_project(session)
    baseline_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 1, tzinfo=UTC),
    )
    target_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.RUNNING,
        created_at=datetime(2026, 6, 27, 2, tzinfo=UTC),
    )
    record_scan_outputs(
        session,
        project=project,
        check_run=baseline_run,
        response_time_ms=700,
        performance_score=80,
    )
    availability_result, lighthouse_result, score_result = record_scan_outputs(
        session,
        project=project,
        check_run=target_run,
        response_time_ms=500,
        performance_score=90,
    )

    comparison = run_comparisons.record_previous_run_comparison(
        session,
        check_run=target_run,
        current_score_result=score_result,
        current_availability_result=availability_result,
        current_lighthouse_result=lighthouse_result,
    )

    assert comparison is not None
    assert comparison.check_run_id == target_run.id
    assert comparison.baseline_check_run_id == baseline_run.id
    assert comparison.comparison_type == "previous_run"
    assert comparison.overall_score_delta == 3
    assert comparison.web_performance_score_delta == 10
    assert comparison.performance_score_delta == 10
    assert comparison.response_time_delta_ms == -200
    assert comparison.deployment_risk_changed is False
    assert comparison.summary == ("Overall score improved by 3. Response time improved by 200ms.")


def test_record_previous_run_comparison_updates_existing_result(session: Session) -> None:
    user, project = create_project(session)
    baseline_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )
    target_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.RUNNING,
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    record_scan_outputs(
        session,
        project=project,
        check_run=baseline_run,
        response_time_ms=700,
        performance_score=80,
    )
    availability_result, lighthouse_result, score_result = record_scan_outputs(
        session,
        project=project,
        check_run=target_run,
        response_time_ms=500,
        performance_score=90,
    )

    first_comparison = run_comparisons.record_previous_run_comparison(
        session,
        check_run=target_run,
        current_score_result=score_result,
        current_availability_result=availability_result,
        current_lighthouse_result=lighthouse_result,
    )
    second_comparison = run_comparisons.record_previous_run_comparison(
        session,
        check_run=target_run,
        current_score_result=score_result,
        current_availability_result=availability_result,
        current_lighthouse_result=lighthouse_result,
    )

    assert first_comparison is not None
    assert second_comparison is not None
    assert second_comparison.id == first_comparison.id
    assert session.scalars(select(RunComparison)).all() == [second_comparison]


def test_compute_baseline_comparison_uses_pinned_baseline(session: Session) -> None:
    user, project = create_project(session)
    baseline_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 1, tzinfo=UTC),
    )
    recent_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 2, tzinfo=UTC),
    )
    target_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 3, tzinfo=UTC),
    )
    record_scan_outputs(
        session,
        project=project,
        check_run=baseline_run,
        response_time_ms=700,
        performance_score=80,
    )
    record_scan_outputs(
        session,
        project=project,
        check_run=recent_run,
        response_time_ms=100,
        performance_score=95,
    )
    record_scan_outputs(
        session,
        project=project,
        check_run=target_run,
        response_time_ms=500,
        performance_score=90,
    )
    project.baseline_check_run_id = baseline_run.id
    session.commit()

    comparison = run_comparisons.compute_baseline_comparison(
        session,
        project=project,
        check_run=target_run,
    )

    assert comparison.comparison_type == "baseline"
    assert comparison.check_run_id == target_run.id
    assert comparison.baseline_check_run_id == baseline_run.id
    assert comparison.overall_score_delta == 3
    assert comparison.web_performance_score_delta == 10
    assert comparison.performance_score_delta == 10
    assert comparison.response_time_delta_ms == -200
    assert comparison.deployment_risk_changed is False
    assert comparison.current_deployment_risk == comparison.baseline_deployment_risk
    assert comparison.summary == ("Overall score improved by 3. Response time improved by 200ms.")
    assert session.scalars(select(RunComparison)).all() == []


def test_compute_baseline_comparison_with_explicit_override(session: Session) -> None:
    user, project = create_project(session)
    pinned_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 1, tzinfo=UTC),
    )
    explicit_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 2, tzinfo=UTC),
    )
    target_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 3, tzinfo=UTC),
    )
    for check_run, response_time_ms in ((pinned_run, 900), (explicit_run, 700), (target_run, 500)):
        record_scan_outputs(
            session,
            project=project,
            check_run=check_run,
            response_time_ms=response_time_ms,
            performance_score=90,
        )
    project.baseline_check_run_id = pinned_run.id
    session.commit()

    comparison = run_comparisons.compute_baseline_comparison(
        session,
        project=project,
        check_run=target_run,
        baseline_check_run_id=explicit_run.id,
    )

    assert comparison.baseline_check_run_id == explicit_run.id
    assert comparison.response_time_delta_ms == -200


def test_compute_baseline_comparison_requires_configuration(session: Session) -> None:
    user, project = create_project(session)
    target_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 1, tzinfo=UTC),
    )
    record_scan_outputs(
        session,
        project=project,
        check_run=target_run,
        response_time_ms=500,
        performance_score=90,
    )

    with pytest.raises(run_comparisons.BaselineNotConfiguredError):
        run_comparisons.compute_baseline_comparison(
            session,
            project=project,
            check_run=target_run,
        )


def test_compute_baseline_comparison_rejects_baseline_from_other_project(
    session: Session,
) -> None:
    user, project = create_project(session)
    other_user, other_project = create_project(session)
    other_project_run = create_check_run(
        session,
        project=other_project,
        user=other_user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 1, tzinfo=UTC),
    )
    target_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 2, tzinfo=UTC),
    )
    record_scan_outputs(
        session,
        project=project,
        check_run=target_run,
        response_time_ms=500,
        performance_score=90,
    )

    with pytest.raises(run_comparisons.BaselineCheckRunMissingError):
        run_comparisons.compute_baseline_comparison(
            session,
            project=project,
            check_run=target_run,
            baseline_check_run_id=other_project_run.id,
        )


def test_compute_baseline_comparison_requires_score_results(session: Session) -> None:
    user, project = create_project(session)
    baseline_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 1, tzinfo=UTC),
    )
    target_run = create_check_run(
        session,
        project=project,
        user=user,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 6, 27, 2, tzinfo=UTC),
    )
    record_scan_outputs(
        session,
        project=project,
        check_run=target_run,
        response_time_ms=500,
        performance_score=90,
    )
    project.baseline_check_run_id = baseline_run.id
    session.commit()

    with pytest.raises(run_comparisons.BaselineComparisonNotAvailableError):
        run_comparisons.compute_baseline_comparison(
            session,
            project=project,
            check_run=target_run,
        )
