from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.alert import IncidentStatus
from aim_api.models.user import User
from aim_api.schemas.alert import AlertRead, IncidentRead
from aim_api.services import alert_delivery, scan_queue
from aim_api.services import incidents as incident_service
from aim_api.services import projects as project_service

router = APIRouter(prefix="/projects/{project_id}", tags=["alerts"])


def project_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found.",
    )


def alert_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Alert not found.",
    )


def alert_retry_not_allowed() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Only failed alerts can be retried.",
    )


def alert_delivery_queue_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Alert delivery queue is unavailable.",
    )


@router.get("/incidents", response_model=list[IncidentRead])
def list_project_incidents(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[IncidentRead]:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    incidents = incident_service.list_incidents(
        session,
        project_id=project.id,
        limit=limit,
        offset=offset,
    )
    # 열린 인시던트는 그 프로젝트가 마지막으로 검사된 시점까지만 사실이다.
    # 해소 판정이 다음 검사에서만 일어나기 때문이다.
    last_checked_at = incident_service.latest_check_run_at_by_project(
        session, project_ids=[project.id]
    ).get(project.id)

    items: list[IncidentRead] = []
    for incident in incidents:
        item = IncidentRead.model_validate(incident)
        item.project_last_checked_at = last_checked_at
        item.is_stale = incident.status == IncidentStatus.OPEN.value and incident_service.is_stale(
            last_checked_at
        )
        items.append(item)
    return items


@router.get("/alerts", response_model=list[AlertRead])
def list_project_alerts(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AlertRead]:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    alerts = incident_service.list_alerts(
        session,
        project_id=project.id,
        limit=limit,
        offset=offset,
    )
    return [AlertRead.model_validate(alert) for alert in alerts]


@router.post("/alerts/{alert_id}/retry", response_model=AlertRead)
def retry_project_alert(
    project_id: UUID,
    alert_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> AlertRead:
    try:
        project = project_service.get_project(
            session,
            owner_id=current_user.id,
            project_id=project_id,
        )
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc

    try:
        alert = alert_delivery.retry_failed_alert(
            session,
            project_id=project.id,
            alert_id=alert_id,
        )
    except alert_delivery.AlertNotFoundError as exc:
        raise alert_not_found() from exc
    except alert_delivery.AlertRetryNotAllowedError as exc:
        raise alert_retry_not_allowed() from exc

    try:
        scan_queue.enqueue_email_alert_retry(alert_id=alert.id)
    except scan_queue.ScanQueueUnavailableError as exc:
        alert_delivery.mark_alert_retry_enqueue_failed(
            session,
            alert=alert,
            error_message="Alert delivery queue is unavailable.",
        )
        raise alert_delivery_queue_unavailable() from exc

    return AlertRead.model_validate(alert)
