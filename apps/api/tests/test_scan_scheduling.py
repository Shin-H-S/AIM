from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from aim_api.database import Base
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.user import User
from aim_api.services import scan_scheduling
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=UTC)


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


def create_user(session: Session) -> User:
    user = User(email=f"{uuid4()}@example.com", password_hash="hashed-password")
    session.add(user)
    session.flush()
    return user


def create_project(
    session: Session,
    *,
    is_verified: bool = True,
    has_owner: bool = True,
    scan_interval_minutes: int = 60,
    scheduled_scans_enabled: bool = True,
) -> Project:
    owner_id = create_user(session).id if has_owner else None
    project = Project(
        owner_id=owner_id,
        name="AIM Website",
        service_url="https://example.com",
        verified_at=NOW - timedelta(days=1) if is_verified else None,
        environment="production",
        scan_interval_minutes=scan_interval_minutes,
        scheduled_scans_enabled=scheduled_scans_enabled,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def create_check_run(
    session: Session,
    *,
    project: Project,
    status: CheckRunStatus,
    created_at: datetime,
) -> CheckRun:
    requested_by_id = project.owner_id or create_user(session).id
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=requested_by_id,
        status=status.value,
        trigger_source="manual",
        queued_at=created_at,
        created_at=created_at,
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)
    return check_run


def list_due_project_ids(session: Session) -> list[object]:
    return [project.id for project in scan_scheduling.list_due_projects(session, now=NOW)]


def test_verified_project_without_check_runs_is_due(session: Session) -> None:
    project = create_project(session)

    assert list_due_project_ids(session) == [project.id]


def test_project_without_opt_in_is_not_due(session: Session) -> None:
    create_project(session, scheduled_scans_enabled=False)

    assert list_due_project_ids(session) == []


def test_unverified_project_is_not_due(session: Session) -> None:
    create_project(session, is_verified=False)

    assert list_due_project_ids(session) == []


def test_project_without_owner_is_not_due(session: Session) -> None:
    create_project(session, has_owner=False)

    assert list_due_project_ids(session) == []


def test_project_with_recent_check_run_is_not_due(session: Session) -> None:
    project = create_project(session, scan_interval_minutes=60)
    create_check_run(
        session,
        project=project,
        status=CheckRunStatus.COMPLETED,
        created_at=NOW - timedelta(minutes=30),
    )

    assert list_due_project_ids(session) == []


def test_project_with_elapsed_interval_is_due(session: Session) -> None:
    project = create_project(session, scan_interval_minutes=60)
    create_check_run(
        session,
        project=project,
        status=CheckRunStatus.COMPLETED,
        created_at=NOW - timedelta(minutes=60),
    )

    assert list_due_project_ids(session) == [project.id]


def test_failed_check_run_also_counts_as_last_scan(session: Session) -> None:
    project = create_project(session, scan_interval_minutes=60)
    create_check_run(
        session,
        project=project,
        status=CheckRunStatus.FAILED,
        created_at=NOW - timedelta(minutes=30),
    )

    assert list_due_project_ids(session) == []


@pytest.mark.parametrize(
    "active_status",
    [CheckRunStatus.QUEUED, CheckRunStatus.RUNNING, CheckRunStatus.ANALYZING],
)
def test_project_with_active_check_run_is_not_due(
    session: Session,
    active_status: CheckRunStatus,
) -> None:
    project = create_project(session, scan_interval_minutes=60)
    create_check_run(
        session,
        project=project,
        status=active_status,
        created_at=NOW - timedelta(hours=5),
    )

    assert list_due_project_ids(session) == []


def test_due_check_uses_latest_check_run(session: Session) -> None:
    project = create_project(session, scan_interval_minutes=60)
    create_check_run(
        session,
        project=project,
        status=CheckRunStatus.COMPLETED,
        created_at=NOW - timedelta(hours=5),
    )
    create_check_run(
        session,
        project=project,
        status=CheckRunStatus.COMPLETED,
        created_at=NOW - timedelta(minutes=10),
    )

    assert list_due_project_ids(session) == []


def test_due_check_respects_per_project_interval(session: Session) -> None:
    frequent_project = create_project(session, scan_interval_minutes=30)
    infrequent_project = create_project(session, scan_interval_minutes=240)
    for project in (frequent_project, infrequent_project):
        create_check_run(
            session,
            project=project,
            status=CheckRunStatus.COMPLETED,
            created_at=NOW - timedelta(minutes=60),
        )

    assert list_due_project_ids(session) == [frequent_project.id]


def test_create_scheduled_check_run_records_trigger_source(session: Session) -> None:
    project = create_project(session)

    check_run = scan_scheduling.create_scheduled_check_run(session, project=project)

    assert check_run.project_id == project.id
    assert check_run.requested_by_id == project.owner_id
    assert check_run.status == CheckRunStatus.QUEUED.value
    assert check_run.trigger_source == scan_scheduling.SCHEDULED_TRIGGER_SOURCE


def test_create_scheduled_check_run_requires_owner(session: Session) -> None:
    project = create_project(session, has_owner=False)

    with pytest.raises(ValueError, match="project owner"):
        scan_scheduling.create_scheduled_check_run(session, project=project)
