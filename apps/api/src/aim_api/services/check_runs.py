from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project


class CheckRunNotFoundError(Exception):
    """Raised when a check run does not exist for the requested project."""


class ProjectNotVerifiedError(Exception):
    """Raised when a check run is requested for an unverified project."""


def create_check_run(session: Session, *, project: Project, requested_by_id: UUID) -> CheckRun:
    if not project.is_verified:
        raise ProjectNotVerifiedError

    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=requested_by_id,
        status=CheckRunStatus.QUEUED.value,
        trigger_source="manual",
    )
    session.add(check_run)
    session.commit()
    session.refresh(check_run)
    return check_run


def list_check_runs(
    session: Session,
    *,
    project_id: UUID,
    limit: int,
    offset: int,
) -> list[CheckRun]:
    statement = (
        select(CheckRun)
        .where(CheckRun.project_id == project_id)
        .order_by(CheckRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(statement))


def get_check_run(session: Session, *, project_id: UUID, check_run_id: UUID) -> CheckRun:
    statement = select(CheckRun).where(
        CheckRun.id == check_run_id,
        CheckRun.project_id == project_id,
    )
    check_run = session.scalar(statement)
    if check_run is None:
        raise CheckRunNotFoundError

    return check_run


def get_check_run_by_id(session: Session, *, check_run_id: UUID) -> CheckRun:
    check_run = session.get(CheckRun, check_run_id)
    if check_run is None:
        raise CheckRunNotFoundError

    return check_run


def mark_check_run_running(session: Session, *, check_run_id: UUID) -> CheckRun:
    check_run = get_check_run_by_id(session, check_run_id=check_run_id)
    if check_run.status in {
        CheckRunStatus.COMPLETED.value,
        CheckRunStatus.FAILED.value,
        CheckRunStatus.CANCELLED.value,
    }:
        return check_run

    check_run.status = CheckRunStatus.RUNNING.value
    if check_run.started_at is None:
        check_run.started_at = datetime.now(UTC)
    session.commit()
    session.refresh(check_run)
    return check_run


def mark_check_run_failed(
    session: Session,
    *,
    check_run_id: UUID,
    failure_reason: str,
) -> CheckRun:
    check_run = get_check_run_by_id(session, check_run_id=check_run_id)
    if check_run.status in {
        CheckRunStatus.COMPLETED.value,
        CheckRunStatus.CANCELLED.value,
    }:
        return check_run

    check_run.status = CheckRunStatus.FAILED.value
    check_run.failure_reason = failure_reason
    check_run.finished_at = datetime.now(UTC)
    session.commit()
    session.refresh(check_run)
    return check_run


def mark_check_run_completed(session: Session, *, check_run_id: UUID) -> CheckRun:
    check_run = get_check_run_by_id(session, check_run_id=check_run_id)
    if check_run.status in {
        CheckRunStatus.FAILED.value,
        CheckRunStatus.CANCELLED.value,
    }:
        return check_run

    check_run.status = CheckRunStatus.COMPLETED.value
    check_run.failure_reason = None
    check_run.finished_at = datetime.now(UTC)
    session.commit()
    session.refresh(check_run)
    return check_run


def cancel_check_run(session: Session, *, project_id: UUID, check_run_id: UUID) -> CheckRun:
    check_run = get_check_run(session, project_id=project_id, check_run_id=check_run_id)
    if check_run.status in {
        CheckRunStatus.COMPLETED.value,
        CheckRunStatus.FAILED.value,
        CheckRunStatus.CANCELLED.value,
    }:
        return check_run

    check_run.status = CheckRunStatus.CANCELLED.value
    check_run.finished_at = datetime.now(UTC)
    session.commit()
    session.refresh(check_run)
    return check_run
