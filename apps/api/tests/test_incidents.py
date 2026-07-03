from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base
from aim_api.models.alert import (
    Alert,
    AlertStatus,
    AlertType,
    Incident,
    IncidentStatus,
    IncidentTriggerType,
)
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import AvailabilityResult, ScoreResult
from aim_api.models.scenario import ScenarioRun, ScenarioRunStatus, TestScenario
from aim_api.models.user import User
from aim_api.services import incidents, scanner_results, score_results
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
    requested_by_id: UUID,
    status: CheckRunStatus,
    created_at: datetime,
) -> CheckRun:
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=requested_by_id,
        status=status.value,
        trigger_source="manual",
        queued_at=created_at,
        started_at=created_at,
        finished_at=created_at,
        created_at=created_at,
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)
    return check_run


def record_score_for_availability(
    session: Session,
    *,
    project: Project,
    check_run: CheckRun,
    is_available: bool,
    status_code: int | None,
    response_time_ms: int | None,
    timed_out: bool = False,
    failure_reason: str | None = None,
) -> tuple[AvailabilityResult, ScoreResult]:
    availability_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url=project.service_url,
        final_url=project.service_url if is_available else None,
        is_available=is_available,
        status_code=status_code,
        response_time_ms=response_time_ms,
        redirect_count=0,
        uses_https=True,
        timed_out=timed_out,
        failure_reason=failure_reason,
    )
    score_result = score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=None,
        lighthouse_result=None,
    )
    return availability_result, score_result


def test_sync_incidents_opens_connection_failure_and_pending_email_alert(
    session: Session,
) -> None:
    user, project = create_project(session)
    check_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED,
        created_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    availability_result, score_result = record_score_for_availability(
        session,
        project=project,
        check_run=check_run,
        is_available=False,
        status_code=None,
        response_time_ms=None,
        timed_out=True,
        failure_reason="Connection timed out.",
    )

    result = incidents.sync_incidents_for_check_run(
        session,
        check_run=check_run,
        project=project,
        availability_result=availability_result,
        lighthouse_result=None,
        score_result=score_result,
    )

    assert len(result.opened_incidents) == 1
    incident = session.scalars(select(Incident)).one()
    assert incident.project_id == project.id
    assert incident.opened_check_run_id == check_run.id
    assert incident.trigger_type == IncidentTriggerType.SERVICE_CONNECTION_FAILURE.value
    assert incident.status == IncidentStatus.OPEN.value
    assert incident.resolved_at is None
    assert incident.evidence_json["timed_out"] is True

    alert = session.scalars(select(Alert)).one()
    assert alert.incident_id == incident.id
    assert alert.check_run_id == check_run.id
    assert alert.alert_type == AlertType.INCIDENT_OPENED.value
    assert alert.status == AlertStatus.PENDING.value
    assert alert.recipient_email == user.email


def test_sync_incidents_uses_project_alert_recipient_email(session: Session) -> None:
    user, project = create_project(session)
    project.alert_recipient_email = "alerts@example.com"
    session.commit()
    check_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED,
        created_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    availability_result, score_result = record_score_for_availability(
        session,
        project=project,
        check_run=check_run,
        is_available=False,
        status_code=None,
        response_time_ms=None,
        failure_reason="Connection timed out.",
    )

    incidents.sync_incidents_for_check_run(
        session,
        check_run=check_run,
        project=project,
        availability_result=availability_result,
        lighthouse_result=None,
        score_result=score_result,
    )

    alert = session.scalars(select(Alert)).one()
    assert alert.recipient_email == "alerts@example.com"


def test_sync_incidents_skips_email_alert_when_project_alert_email_is_disabled(
    session: Session,
) -> None:
    user, project = create_project(session)
    project.alert_email_enabled = False
    session.commit()
    check_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED,
        created_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    availability_result, score_result = record_score_for_availability(
        session,
        project=project,
        check_run=check_run,
        is_available=False,
        status_code=None,
        response_time_ms=None,
        failure_reason="Connection timed out.",
    )

    result = incidents.sync_incidents_for_check_run(
        session,
        check_run=check_run,
        project=project,
        availability_result=availability_result,
        lighthouse_result=None,
        score_result=score_result,
    )

    assert len(result.opened_incidents) == 1
    assert result.alerts == []
    assert session.scalars(select(Incident)).one()
    assert session.scalars(select(Alert)).all() == []


def test_sync_incidents_does_not_duplicate_existing_open_incident(
    session: Session,
) -> None:
    user, project = create_project(session)
    first_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED,
        created_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    first_availability, first_score = record_score_for_availability(
        session,
        project=project,
        check_run=first_run,
        is_available=False,
        status_code=None,
        response_time_ms=None,
        failure_reason="DNS resolution failed.",
    )
    incidents.sync_incidents_for_check_run(
        session,
        check_run=first_run,
        project=project,
        availability_result=first_availability,
        lighthouse_result=None,
        score_result=first_score,
    )

    second_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED,
        created_at=datetime(2026, 7, 1, 2, tzinfo=UTC),
    )
    second_availability, second_score = record_score_for_availability(
        session,
        project=project,
        check_run=second_run,
        is_available=False,
        status_code=None,
        response_time_ms=None,
        failure_reason="Connection timed out.",
    )

    result = incidents.sync_incidents_for_check_run(
        session,
        check_run=second_run,
        project=project,
        availability_result=second_availability,
        lighthouse_result=None,
        score_result=second_score,
    )

    incident = session.scalars(select(Incident)).one()
    assert result.opened_incidents == []
    assert incident.opened_check_run_id == first_run.id
    assert incident.summary == "Connection timed out."
    assert session.scalars(select(Alert)).all()[0].alert_type == AlertType.INCIDENT_OPENED.value
    assert len(session.scalars(select(Alert)).all()) == 1


def test_sync_incidents_resolves_recovered_incident_and_records_recovery_alert(
    session: Session,
) -> None:
    user, project = create_project(session)
    failed_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED,
        created_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    failed_availability, failed_score = record_score_for_availability(
        session,
        project=project,
        check_run=failed_run,
        is_available=False,
        status_code=None,
        response_time_ms=None,
        failure_reason="Connection timed out.",
    )
    incidents.sync_incidents_for_check_run(
        session,
        check_run=failed_run,
        project=project,
        availability_result=failed_availability,
        lighthouse_result=None,
        score_result=failed_score,
    )

    recovered_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 7, 1, 2, tzinfo=UTC),
    )
    recovered_availability, recovered_score = record_score_for_availability(
        session,
        project=project,
        check_run=recovered_run,
        is_available=True,
        status_code=200,
        response_time_ms=300,
    )

    result = incidents.sync_incidents_for_check_run(
        session,
        check_run=recovered_run,
        project=project,
        availability_result=recovered_availability,
        lighthouse_result=None,
        score_result=recovered_score,
    )

    assert len(result.resolved_incidents) == 1
    incident = session.scalars(select(Incident)).one()
    assert incident.status == IncidentStatus.RESOLVED.value
    assert incident.resolved_check_run_id == recovered_run.id
    assert incident.resolved_at is not None
    alerts = session.scalars(select(Alert).order_by(Alert.created_at.asc(), Alert.id.asc())).all()
    assert [alert.alert_type for alert in alerts] == [
        AlertType.INCIDENT_OPENED.value,
        AlertType.INCIDENT_RECOVERED.value,
    ]


def test_sync_incidents_detects_repeated_5xx_response(session: Session) -> None:
    user, project = create_project(session)
    previous_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED,
        created_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    record_score_for_availability(
        session,
        project=project,
        check_run=previous_run,
        is_available=False,
        status_code=503,
        response_time_ms=120,
        failure_reason="Service returned HTTP 503.",
    )
    current_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED,
        created_at=datetime(2026, 7, 1, 2, tzinfo=UTC),
    )
    current_availability, current_score = record_score_for_availability(
        session,
        project=project,
        check_run=current_run,
        is_available=False,
        status_code=502,
        response_time_ms=100,
        failure_reason="Service returned HTTP 502.",
    )

    incidents.sync_incidents_for_check_run(
        session,
        check_run=current_run,
        project=project,
        availability_result=current_availability,
        lighthouse_result=None,
        score_result=current_score,
    )

    incident = session.scalars(select(Incident)).one()
    assert incident.trigger_type == IncidentTriggerType.REPEATED_5XX_RESPONSE.value
    assert incident.evidence_json["status_code"] == 502


def test_sync_incidents_detects_response_time_and_performance_thresholds(
    session: Session,
) -> None:
    user, project = create_project(session)
    check_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    availability_result, _ = record_score_for_availability(
        session,
        project=project,
        check_run=check_run,
        is_available=True,
        status_code=200,
        response_time_ms=1_500,
    )
    lighthouse_result = scanner_results.record_lighthouse_result(
        session,
        check_run_id=check_run.id,
        service_url=project.service_url,
        is_successful=True,
        performance_score=60,
        accessibility_score=95,
        seo_score=90,
        best_practices_score=90,
        largest_contentful_paint_ms=2_000,
        cumulative_layout_shift=0.02,
        total_blocking_time_ms=50,
        raw_json_artifact_id=None,
        failure_reason=None,
    )
    score_result = score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=None,
        lighthouse_result=lighthouse_result,
    )

    incidents.sync_incidents_for_check_run(
        session,
        check_run=check_run,
        project=project,
        availability_result=availability_result,
        lighthouse_result=lighthouse_result,
        score_result=score_result,
    )

    trigger_types = {
        incident.trigger_type
        for incident in session.scalars(select(Incident).order_by(Incident.trigger_type)).all()
    }
    assert trigger_types == {
        IncidentTriggerType.PERFORMANCE_SCORE_BELOW_THRESHOLD.value,
        IncidentTriggerType.RESPONSE_TIME_ABOVE_THRESHOLD.value,
    }
    assert len(session.scalars(select(Alert)).all()) == 2


def test_sync_incidents_detects_failed_linked_scenario(session: Session) -> None:
    user, project = create_project(session)
    check_run = create_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.COMPLETED,
        created_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    scenario = TestScenario(
        project_id=project.id,
        name="Login flow",
        description=None,
        is_active=True,
    )
    session.add(scenario)
    session.flush()
    scenario_run = ScenarioRun(
        project_id=project.id,
        scenario_id=scenario.id,
        check_run_id=check_run.id,
        requested_by_id=user.id,
        status=ScenarioRunStatus.FAILED.value,
        trigger_source="check_run",
        failure_reason="Expected dashboard element was not found.",
        started_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
        finished_at=datetime(2026, 7, 1, 1, tzinfo=UTC),
    )
    session.add(scenario_run)
    session.commit()

    availability_result, score_result = record_score_for_availability(
        session,
        project=project,
        check_run=check_run,
        is_available=True,
        status_code=200,
        response_time_ms=200,
    )

    incidents.sync_incidents_for_check_run(
        session,
        check_run=check_run,
        project=project,
        availability_result=availability_result,
        lighthouse_result=None,
        score_result=score_result,
    )

    incident = session.scalars(select(Incident)).one()
    assert incident.trigger_type == IncidentTriggerType.CRITICAL_SCENARIO_FAILURE.value
    assert incident.evidence_json["scenario_run_id"] == str(scenario_run.id)
    assert session.scalars(select(Alert)).one().alert_type == AlertType.INCIDENT_OPENED.value
