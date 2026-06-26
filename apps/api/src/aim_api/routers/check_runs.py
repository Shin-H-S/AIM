from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.user import User
from aim_api.schemas.check_run import CheckRunCreate, CheckRunRead
from aim_api.services import check_runs as check_run_service
from aim_api.services import projects as project_service
from aim_api.services import scan_queue

router = APIRouter(prefix="/projects/{project_id}/check-runs", tags=["check-runs"])


def check_run_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Check run not found.",
    )


def project_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found.",
    )


def project_not_verified() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Project must be verified before creating a check run.",
    )


def scan_queue_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Scan queue is unavailable.",
    )


@router.post("", response_model=CheckRunRead, status_code=status.HTTP_201_CREATED)
def create_check_run(
    project_id: UUID,
    payload: CheckRunCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CheckRunRead:
    _ = payload
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        check_run = check_run_service.create_check_run(
            session,
            project=project,
            requested_by_id=current_user.id,
        )
        scan_queue.enqueue_check_run(check_run_id=check_run.id)
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except check_run_service.ProjectNotVerifiedError as exc:
        raise project_not_verified() from exc
    except scan_queue.ScanQueueUnavailableError as exc:
        check_run_service.mark_check_run_failed(
            session,
            check_run_id=check_run.id,
            failure_reason="Scan queue is unavailable.",
        )
        raise scan_queue_unavailable() from exc

    return CheckRunRead.model_validate(check_run)


@router.get("", response_model=list[CheckRunRead])
def list_check_runs(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CheckRunRead]:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    check_runs = check_run_service.list_check_runs(
        session,
        project_id=project.id,
        limit=limit,
        offset=offset,
    )
    return [CheckRunRead.model_validate(check_run) for check_run in check_runs]


@router.get("/{check_run_id}", response_model=CheckRunRead)
def get_check_run(
    project_id: UUID,
    check_run_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CheckRunRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        check_run = check_run_service.get_check_run(
            session,
            project_id=project.id,
            check_run_id=check_run_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except check_run_service.CheckRunNotFoundError as exc:
        raise check_run_not_found() from exc

    return CheckRunRead.model_validate(check_run)


@router.post("/{check_run_id}/cancel", response_model=CheckRunRead)
def cancel_check_run(
    project_id: UUID,
    check_run_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> CheckRunRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
        check_run = check_run_service.cancel_check_run(
            session,
            project_id=project.id,
            check_run_id=check_run_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc
    except check_run_service.CheckRunNotFoundError as exc:
        raise check_run_not_found() from exc

    return CheckRunRead.model_validate(check_run)
