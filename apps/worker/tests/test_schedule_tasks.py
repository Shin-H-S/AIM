from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.user import User
from aim_api.services import scan_queue
from aim_api.services.scan_queue import SCHEDULE_CHECK_RUNS_TASK_NAME
from aim_api.services.scan_scheduling import SCHEDULED_TRIGGER_SOURCE
from aim_worker import tasks
from aim_worker.celery_app import celery_app
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


@pytest.fixture()
def scheduled_check_run_queue(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    enqueued_check_run_ids: list[str] = []

    def fake_enqueue_scheduled_check_run(*, check_run_id: UUID) -> str:
        enqueued_check_run_ids.append(str(check_run_id))
        return str(check_run_id)

    monkeypatch.setattr(
        tasks,
        "enqueue_scheduled_check_run",
        fake_enqueue_scheduled_check_run,
    )
    return enqueued_check_run_ids


def create_project(
    session: Session,
    *,
    is_verified: bool = True,
    scan_interval_minutes: int = 60,
) -> Project:
    user = User(email=f"{uuid4()}@example.com", password_hash="hashed-password")
    session.add(user)
    session.flush()
    project = Project(
        owner_id=user.id,
        name="AIM Website",
        service_url="https://example.com",
        verified_at=datetime.now(UTC) - timedelta(days=1) if is_verified else None,
        environment="production",
        scan_interval_minutes=scan_interval_minutes,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def create_recent_check_run(session: Session, *, project: Project) -> CheckRun:
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=project.owner_id,
        status=CheckRunStatus.COMPLETED.value,
        trigger_source="manual",
        created_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)
    return check_run


def list_check_runs(session: Session) -> list[CheckRun]:
    return list(session.scalars(select(CheckRun)))


def test_schedule_due_check_runs_creates_and_enqueues_scheduled_run(
    session: Session,
    scheduled_check_run_queue: list[str],
) -> None:
    project = create_project(session)

    result = tasks.schedule_due_check_runs.run()

    assert result == {
        "due_project_count": 1,
        "scheduled_count": 1,
        "enqueue_failed_count": 0,
    }
    check_runs = list_check_runs(session)
    assert len(check_runs) == 1
    scheduled_run = check_runs[0]
    assert scheduled_run.project_id == project.id
    assert scheduled_run.requested_by_id == project.owner_id
    assert scheduled_run.status == CheckRunStatus.QUEUED.value
    assert scheduled_run.trigger_source == SCHEDULED_TRIGGER_SOURCE
    assert scheduled_check_run_queue == [str(scheduled_run.id)]


def test_schedule_due_check_runs_skips_unverified_project(
    session: Session,
    scheduled_check_run_queue: list[str],
) -> None:
    create_project(session, is_verified=False)

    result = tasks.schedule_due_check_runs.run()

    assert result == {
        "due_project_count": 0,
        "scheduled_count": 0,
        "enqueue_failed_count": 0,
    }
    assert list_check_runs(session) == []
    assert scheduled_check_run_queue == []


def test_schedule_due_check_runs_skips_project_scanned_recently(
    session: Session,
    scheduled_check_run_queue: list[str],
) -> None:
    project = create_project(session)
    recent_check_run = create_recent_check_run(session, project=project)

    result = tasks.schedule_due_check_runs.run()

    assert result == {
        "due_project_count": 0,
        "scheduled_count": 0,
        "enqueue_failed_count": 0,
    }
    assert [check_run.id for check_run in list_check_runs(session)] == [recent_check_run.id]
    assert scheduled_check_run_queue == []


def test_schedule_due_check_runs_marks_run_failed_when_queue_unavailable(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_project(session)

    def failing_enqueue(*, check_run_id: UUID) -> str:
        raise scan_queue.ScanQueueUnavailableError

    monkeypatch.setattr(tasks, "enqueue_scheduled_check_run", failing_enqueue)

    result = tasks.schedule_due_check_runs.run()

    assert result == {
        "due_project_count": 1,
        "scheduled_count": 0,
        "enqueue_failed_count": 1,
    }
    check_runs = list_check_runs(session)
    assert len(check_runs) == 1
    failed_run = check_runs[0]
    assert failed_run.status == CheckRunStatus.FAILED.value
    assert failed_run.failure_reason == tasks.SCHEDULED_CHECK_RUN_ENQUEUE_FAILED_REASON


def test_beat_schedule_registers_scheduler_task() -> None:
    beat_entries = celery_app.conf.beat_schedule.values()

    assert SCHEDULE_CHECK_RUNS_TASK_NAME in {entry["task"] for entry in beat_entries}
