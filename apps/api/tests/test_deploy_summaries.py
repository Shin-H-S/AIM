from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base
from aim_api.models.alert import Alert, AlertChannel, AlertStatus, AlertType
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import RunComparison, ScoreResult
from aim_api.models.scenario import ScenarioRun, ScenarioRunStatus, TestScenario
from aim_api.models.user import User
from aim_api.services import scanner_results, score_results
from aim_api.services.deploy_summaries import (
    build_comparison_line,
    build_deploy_summary_body,
    create_deploy_summary_alerts,
)
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


def create_project(session: Session, *, webhook_url: str | None) -> tuple[User, Project]:
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
        alert_webhook_url=webhook_url,
    )
    session.add(project)
    session.commit()
    session.refresh(user)
    session.refresh(project)
    return user, project


def create_deploy_check_run(
    session: Session,
    *,
    project: Project,
    requested_by_id: UUID,
    status: CheckRunStatus = CheckRunStatus.COMPLETED,
    trigger_source: str = "deploy",
    deploy_ref: str | None = "3e7926b",
    failure_reason: str | None = None,
) -> CheckRun:
    now = datetime.now(UTC)
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=requested_by_id,
        status=status.value,
        trigger_source=trigger_source,
        deploy_ref=deploy_ref,
        failure_reason=failure_reason,
        queued_at=now,
        started_at=now,
        finished_at=now,
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)
    return check_run


def record_score(session: Session, *, project: Project, check_run: CheckRun) -> ScoreResult:
    availability_result = scanner_results.record_availability_result(
        session,
        check_run_id=check_run.id,
        service_url=project.service_url,
        final_url=project.service_url,
        is_available=True,
        status_code=200,
        response_time_ms=200,
        redirect_count=0,
        uses_https=True,
        timed_out=False,
        failure_reason=None,
    )
    return score_results.record_score_result(
        session,
        check_run_id=check_run.id,
        project=project,
        availability_result=availability_result,
        ssl_result=None,
        lighthouse_result=None,
    )


def create_scenario_run(
    session: Session,
    *,
    project: Project,
    check_run: CheckRun,
    requested_by_id: UUID,
    status: ScenarioRunStatus,
) -> ScenarioRun:
    scenario = TestScenario(project_id=project.id, name="핵심 흐름")
    session.add(scenario)
    session.flush()
    scenario_run = ScenarioRun(
        project_id=project.id,
        scenario_id=scenario.id,
        check_run_id=check_run.id,
        requested_by_id=requested_by_id,
        status=status.value,
        trigger_source="check_run",
    )
    session.add(scenario_run)
    session.commit()
    session.refresh(scenario_run)
    return scenario_run


def test_creates_webhook_summary_for_completed_deploy_run(session: Session) -> None:
    user, project = create_project(session, webhook_url="https://discord.com/api/webhooks/x")
    check_run = create_deploy_check_run(session, project=project, requested_by_id=user.id)
    score_result = record_score(session, project=project, check_run=check_run)

    alerts = create_deploy_summary_alerts(
        session,
        check_run=check_run,
        project=project,
        score_result=score_result,
    )

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.alert_type == AlertType.DEPLOY_SUMMARY.value
    assert alert.trigger_type == "DEPLOY_CHECK_COMPLETED"
    assert alert.channel == AlertChannel.WEBHOOK.value
    assert alert.status == AlertStatus.PENDING.value
    assert alert.incident_id is None
    assert alert.check_run_id == check_run.id
    assert "배포 검사 완료" in alert.subject
    assert "3e7926b" in alert.subject
    assert f"{score_result.overall_score}점" in alert.subject
    assert "프로젝트: AIM Website" in alert.body
    assert "배포 참조: 3e7926b" in alert.body


def test_skips_non_deploy_trigger(session: Session) -> None:
    user, project = create_project(session, webhook_url="https://discord.com/api/webhooks/x")
    check_run = create_deploy_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        trigger_source="manual",
    )
    score_result = record_score(session, project=project, check_run=check_run)

    assert (
        create_deploy_summary_alerts(
            session,
            check_run=check_run,
            project=project,
            score_result=score_result,
        )
        == []
    )


def test_skips_without_webhook_url(session: Session) -> None:
    user, project = create_project(session, webhook_url=None)
    check_run = create_deploy_check_run(session, project=project, requested_by_id=user.id)
    score_result = record_score(session, project=project, check_run=check_run)

    assert (
        create_deploy_summary_alerts(
            session,
            check_run=check_run,
            project=project,
            score_result=score_result,
        )
        == []
    )


def test_waits_for_pending_scenario_runs(session: Session) -> None:
    user, project = create_project(session, webhook_url="https://discord.com/api/webhooks/x")
    check_run = create_deploy_check_run(session, project=project, requested_by_id=user.id)
    score_result = record_score(session, project=project, check_run=check_run)
    scenario_run = create_scenario_run(
        session,
        project=project,
        check_run=check_run,
        requested_by_id=user.id,
        status=ScenarioRunStatus.RUNNING,
    )

    assert (
        create_deploy_summary_alerts(
            session,
            check_run=check_run,
            project=project,
            score_result=score_result,
        )
        == []
    )

    scenario_run.status = ScenarioRunStatus.COMPLETED.value
    session.commit()

    alerts = create_deploy_summary_alerts(
        session,
        check_run=check_run,
        project=project,
        score_result=score_result,
    )
    assert len(alerts) == 1


def test_creates_summary_only_once(session: Session) -> None:
    user, project = create_project(session, webhook_url="https://discord.com/api/webhooks/x")
    check_run = create_deploy_check_run(session, project=project, requested_by_id=user.id)
    score_result = record_score(session, project=project, check_run=check_run)

    first = create_deploy_summary_alerts(
        session,
        check_run=check_run,
        project=project,
        score_result=score_result,
    )
    second = create_deploy_summary_alerts(
        session,
        check_run=check_run,
        project=project,
        score_result=score_result,
    )

    assert len(first) == 1
    assert second == []
    stored = session.scalars(select(Alert)).all()
    assert len(stored) == 1


def test_failed_deploy_run_summary_mentions_failure(session: Session) -> None:
    user, project = create_project(session, webhook_url="https://discord.com/api/webhooks/x")
    check_run = create_deploy_check_run(
        session,
        project=project,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED,
        failure_reason="Service is unavailable.",
    )

    alerts = create_deploy_summary_alerts(
        session,
        check_run=check_run,
        project=project,
        score_result=None,
    )

    assert len(alerts) == 1
    assert "배포 검사 실패" in alerts[0].subject
    assert "실패 사유: Service is unavailable." in alerts[0].body
    assert "결과: 점수 미산출" in alerts[0].body


def test_body_includes_result_link(session: Session) -> None:
    user, project = create_project(session, webhook_url="https://discord.com/api/webhooks/x")
    check_run = create_deploy_check_run(session, project=project, requested_by_id=user.id)
    score_result = record_score(session, project=project, check_run=check_run)

    body = build_deploy_summary_body(
        project=project,
        check_run=check_run,
        score_result=score_result,
        comparison=None,
        web_base_url="https://qaaimsync.com/",
    )

    expected_link = (
        f"결과 페이지: https://qaaimsync.com/projects/{project.id}/check-runs/{check_run.id}"
    )
    assert expected_link in body


def test_comparison_line_formats_deltas() -> None:
    comparison = RunComparison(overall_score_delta=2, response_time_delta_ms=-139)
    assert build_comparison_line(comparison) == "직전 대비: 종합 +2 · 응답 시간 -139ms"

    unchanged = RunComparison(overall_score_delta=0, response_time_delta_ms=0)
    assert build_comparison_line(unchanged) == "직전 대비: 변화 없음"

    assert build_comparison_line(None) is None
