from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.user import User
from aim_api.schemas.alert import AlertRead, IncidentRead
from aim_api.services import incidents as incident_service
from aim_api.services import projects as project_service

router = APIRouter(prefix="/projects/{project_id}", tags=["alerts"])


def project_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found.",
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
    return [IncidentRead.model_validate(incident) for incident in incidents]


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
