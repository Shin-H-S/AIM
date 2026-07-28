from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.agent_investigation import AgentInvestigation
from aim_api.models.check_run import CheckRunStatus
from aim_api.models.user import User
from aim_api.schemas.agent_investigation import (
    AgentInvestigationEnqueueRead,
    AgentInvestigationFeedbackWrite,
    AgentInvestigationRead,
)
from aim_api.services import agent_feedback as agent_feedback_service
from aim_api.services import check_runs as check_run_service
from aim_api.services import projects as project_service
from aim_api.services import scan_queue

router = APIRouter(
    prefix="/projects/{project_id}/check-runs/{check_run_id}/investigation",
    tags=["agent-investigations"],
)

TERMINAL_STATUSES = {
    CheckRunStatus.COMPLETED.value,
    CheckRunStatus.FAILED.value,
    CheckRunStatus.CANCELLED.value,
}


def investigation_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Agent investigation not found.",
    )


def check_run_not_terminal() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Check run must be finished before it can be investigated.",
    )


def investigation_already_exists() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Agent investigation already exists for this check run.",
    )


def scan_queue_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Scan queue is unavailable.",
    )


def require_owned_check_run(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
    check_run_id: UUID,
) -> str:
    """소유권 확인 후 검사 상태를 돌려준다 — 404는 소유권 누출 방지 겸용."""
    try:
        project = project_service.get_project(
            session,
            owner_id=owner_id,
            project_id=project_id,
        )
        check_run = check_run_service.get_check_run(
            session,
            project_id=project.id,
            check_run_id=check_run_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        ) from exc
    except check_run_service.CheckRunNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Check run not found."
        ) from exc
    return check_run.status


def find_investigation(session: Session, *, check_run_id: UUID) -> AgentInvestigation | None:
    return session.scalars(
        select(AgentInvestigation).where(AgentInvestigation.check_run_id == check_run_id)
    ).first()


@router.get("", response_model=AgentInvestigationRead)
def get_agent_investigation(
    project_id: UUID,
    check_run_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentInvestigationRead:
    require_owned_check_run(
        session,
        owner_id=current_user.id,
        project_id=project_id,
        check_run_id=check_run_id,
    )
    investigation = find_investigation(session, check_run_id=check_run_id)
    if investigation is None:
        raise investigation_not_found()
    return AgentInvestigationRead.model_validate(investigation)


@router.post(
    "",
    response_model=AgentInvestigationEnqueueRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_agent_investigation(
    project_id: UUID,
    check_run_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentInvestigationEnqueueRead:
    """수동 조사 트리거 — 종결된 검사에 한해, 검사당 1회."""
    check_run_status = require_owned_check_run(
        session,
        owner_id=current_user.id,
        project_id=project_id,
        check_run_id=check_run_id,
    )
    if check_run_status not in TERMINAL_STATUSES:
        raise check_run_not_terminal()
    if find_investigation(session, check_run_id=check_run_id) is not None:
        raise investigation_already_exists()
    try:
        task_id = scan_queue.enqueue_agent_investigation(
            check_run_id=check_run_id,
            trigger="manual",
        )
    except scan_queue.ScanQueueUnavailableError as exc:
        raise scan_queue_unavailable() from exc
    return AgentInvestigationEnqueueRead(task_id=task_id)


@router.put("/feedback", response_model=AgentInvestigationRead)
def submit_agent_investigation_feedback(
    project_id: UUID,
    check_run_id: UUID,
    payload: AgentInvestigationFeedbackWrite,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentInvestigationRead:
    """조사가 맞았는지 남긴다. 다시 보내면 덮어쓴다 — 사람은 마음을 바꾼다.

    여기 쌓이는 값이 조사 정확도를 합성이 아닌 실데이터로 재는 유일한 원자료다.
    """
    require_owned_check_run(
        session,
        owner_id=current_user.id,
        project_id=project_id,
        check_run_id=check_run_id,
    )
    try:
        investigation = agent_feedback_service.record_feedback(
            session,
            check_run_id=check_run_id,
            user_id=current_user.id,
            verdict=payload.verdict,
            root_cause=payload.root_cause,
            note=payload.note,
        )
    except agent_feedback_service.InvestigationNotFoundError as exc:
        raise investigation_not_found() from exc
    except agent_feedback_service.InvalidFeedbackError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return AgentInvestigationRead.model_validate(investigation)


@router.delete("/feedback", response_model=AgentInvestigationRead)
def clear_agent_investigation_feedback(
    project_id: UUID,
    check_run_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AgentInvestigationRead:
    """잘못 누른 피드백을 되돌린다 — 오입력이 라벨로 굳으면 안 된다."""
    require_owned_check_run(
        session,
        owner_id=current_user.id,
        project_id=project_id,
        check_run_id=check_run_id,
    )
    try:
        investigation = agent_feedback_service.clear_feedback(session, check_run_id=check_run_id)
    except agent_feedback_service.InvestigationNotFoundError as exc:
        raise investigation_not_found() from exc
    return AgentInvestigationRead.model_validate(investigation)
