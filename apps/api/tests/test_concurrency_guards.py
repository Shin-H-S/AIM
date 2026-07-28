"""동시성 안전장치가 애플리케이션이 아니라 데이터베이스에 있는지 검증한다.

이 테스트들은 PostgreSQL에서만 의미가 있다 — 부분 유니크 인덱스도,
FOR UPDATE SKIP LOCKED도, advisory lock도 SQLite에는 없거나 무시된다.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from aim_api.models.alert import (
    Alert,
    AlertChannel,
    AlertStatus,
    AlertType,
    Incident,
    IncidentStatus,
)
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.user import User
from aim_api.services import alert_delivery, scan_scheduling
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker


def create_project(session: Session) -> Project:
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
    session.commit()
    return project


def add_check_run(
    session: Session,
    *,
    project: Project,
    trigger_source: str,
    status: str = CheckRunStatus.QUEUED.value,
) -> CheckRun:
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=project.owner_id,
        status=status,
        trigger_source=trigger_source,
    )
    session.add(check_run)
    session.commit()
    return check_run


@pytest.mark.parametrize("trigger_source", ["scheduled", "deploy"])
def test_second_active_automated_check_run_is_rejected(
    session: Session, trigger_source: str
) -> None:
    """배포 훅이 동시에 두 번 들어와도 큐가 쌓이면 안 된다."""
    project = create_project(session)
    add_check_run(session, project=project, trigger_source=trigger_source)

    with pytest.raises(IntegrityError):
        add_check_run(session, project=project, trigger_source=trigger_source)


def test_scheduled_and_deploy_check_runs_cannot_both_be_active(session: Session) -> None:
    project = create_project(session)
    add_check_run(session, project=project, trigger_source="scheduled")

    with pytest.raises(IntegrityError):
        add_check_run(session, project=project, trigger_source="deploy")


def test_manual_check_run_is_allowed_while_an_automated_one_runs(session: Session) -> None:
    """사용자가 정기 검사 도중 수동 실행을 누르는 것은 정상 동작이다."""
    project = create_project(session)
    add_check_run(session, project=project, trigger_source="scheduled")

    manual = add_check_run(session, project=project, trigger_source="manual")

    assert manual.id is not None


def test_agent_recheck_is_allowed_while_an_automated_check_run_is_active(
    session: Session,
) -> None:
    """조사 재검사가 정기 검사와 겹친다고 실패하면 조사 결론이 보수적으로 망가진다."""
    project = create_project(session)
    add_check_run(session, project=project, trigger_source="scheduled")

    recheck = add_check_run(session, project=project, trigger_source="agent_recheck")

    assert recheck.id is not None


def test_finished_automated_check_run_frees_the_slot(session: Session) -> None:
    project = create_project(session)
    finished = add_check_run(session, project=project, trigger_source="scheduled")
    finished.status = CheckRunStatus.COMPLETED.value
    session.commit()

    next_run = add_check_run(session, project=project, trigger_source="scheduled")

    assert next_run.id is not None


def test_two_projects_can_each_have_an_active_automated_check_run(session: Session) -> None:
    first = create_project(session)
    second = create_project(session)

    add_check_run(session, project=first, trigger_source="scheduled")
    add_check_run(session, project=second, trigger_source="scheduled")


def add_pending_alert(session: Session, *, project: Project) -> Alert:
    check_run = add_check_run(session, project=project, trigger_source="manual")
    incident = Incident(
        project_id=project.id,
        opened_check_run_id=check_run.id,
        trigger_type="SERVICE_CONNECTION_FAILURE",
        severity="RISK",
        status=IncidentStatus.OPEN.value,
        title="Service is down",
        summary="Connection refused",
        started_at=datetime.now(UTC),
    )
    session.add(incident)
    session.flush()
    alert = Alert(
        project_id=project.id,
        incident_id=incident.id,
        check_run_id=check_run.id,
        alert_type=AlertType.INCIDENT_OPENED.value,
        trigger_type="SERVICE_CONNECTION_FAILURE",
        channel=AlertChannel.WEBHOOK.value,
        status=AlertStatus.PENDING.value,
        subject="Service is down",
        body="Connection refused",
    )
    session.add(alert)
    session.commit()
    return alert


def test_a_claimed_alert_is_invisible_to_a_second_worker(
    session: Session, session_factory: sessionmaker[Session], db_engine: Engine
) -> None:
    """워커가 둘이어도 같은 알림을 두 번 발송하면 안 된다.

    첫 세션이 트랜잭션을 연 채 알림을 집으면, 두 번째 세션은 SKIP LOCKED 덕에
    그 행을 건너뛰고 빈 목록을 본다. 잠금이 없으면 둘 다 같은 알림을 읽는다.
    """
    project = create_project(session)
    add_pending_alert(session, project=project)

    first_worker = session_factory()
    second_worker = session_factory()
    try:
        claimed = alert_delivery.list_pending_alerts(first_worker, limit=10)
        assert len(claimed) == 1

        also_claimed = alert_delivery.list_pending_alerts(second_worker, limit=10)
        assert also_claimed == []
    finally:
        first_worker.rollback()
        first_worker.close()
        second_worker.rollback()
        second_worker.close()


def test_a_released_alert_becomes_visible_again(
    session: Session, session_factory: sessionmaker[Session]
) -> None:
    project = create_project(session)
    add_pending_alert(session, project=project)

    first_worker = session_factory()
    claimed = alert_delivery.list_pending_alerts(first_worker, limit=10)
    assert len(claimed) == 1
    first_worker.rollback()
    first_worker.close()

    second_worker = session_factory()
    try:
        assert len(alert_delivery.list_pending_alerts(second_worker, limit=10)) == 1
    finally:
        second_worker.rollback()
        second_worker.close()


def test_only_one_scheduler_holds_the_lock_at_a_time(
    session_factory: sessionmaker[Session],
) -> None:
    """beat가 둘이면 같은 프로젝트에 검사가 두 개 생기던 경합을 막는다."""
    first_scheduler = session_factory()
    second_scheduler = session_factory()
    try:
        with scan_scheduling.scheduler_lock(first_scheduler) as first_acquired:
            assert first_acquired is True

            with scan_scheduling.scheduler_lock(second_scheduler) as second_acquired:
                assert second_acquired is False
    finally:
        first_scheduler.close()
        second_scheduler.close()


def test_the_lock_is_released_for_the_next_tick(
    session_factory: sessionmaker[Session],
) -> None:
    first_scheduler = session_factory()
    second_scheduler = session_factory()
    try:
        with scan_scheduling.scheduler_lock(first_scheduler) as acquired:
            assert acquired is True

        with scan_scheduling.scheduler_lock(second_scheduler) as acquired_after_release:
            assert acquired_after_release is True
    finally:
        first_scheduler.close()
        second_scheduler.close()
