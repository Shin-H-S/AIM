from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.scenario import ScenarioRun, TestScenario
from aim_api.models.user import User
from aim_api.schemas.scenario import (
    ScenarioRunCreate,
    ScenarioRunDetailRead,
    ScenarioRunRead,
    TestScenarioCreate,
    TestScenarioRead,
    TestScenarioUpdate,
)
from aim_api.services import projects as project_service
from aim_api.services import scan_queue
from aim_api.services import scenarios as scenario_service

router = APIRouter(prefix="/projects/{project_id}/scenarios", tags=["scenarios"])


def project_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Project not found.",
    )


def scenario_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Scenario not found.",
    )


def scenario_run_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Scenario run not found.",
    )


def scenario_inactive() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Scenario must be active before creating a scenario run.",
    )


def scan_queue_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Scan queue is unavailable.",
    )


def build_scenario_response(session: Session, scenario: TestScenario) -> TestScenarioRead:
    steps = scenario_service.list_steps(session, scenario_id=scenario.id)
    return TestScenarioRead(
        id=scenario.id,
        project_id=scenario.project_id,
        name=scenario.name,
        description=scenario.description,
        is_active=scenario.is_active,
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
        steps=steps,
    )


def build_scenario_run_response(
    session: Session,
    scenario_run: ScenarioRun,
) -> ScenarioRunDetailRead:
    step_results = scenario_service.list_step_results(session, scenario_run_id=scenario_run.id)
    scenario_run_body = ScenarioRunRead.model_validate(scenario_run).model_dump()
    return ScenarioRunDetailRead(**scenario_run_body, step_results=step_results)


def require_project_for_user(
    session: Session,
    *,
    owner_id: UUID,
    project_id: UUID,
) -> None:
    try:
        project_service.get_project(session, owner_id=owner_id, project_id=project_id)
    except project_service.ProjectNotFoundError as exc:
        raise project_not_found() from exc


@router.post("", response_model=TestScenarioRead, status_code=status.HTTP_201_CREATED)
def create_scenario(
    project_id: UUID,
    payload: TestScenarioCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TestScenarioRead:
    require_project_for_user(session, owner_id=current_user.id, project_id=project_id)
    scenario = scenario_service.create_scenario(session, project_id=project_id, payload=payload)
    return build_scenario_response(session, scenario)


@router.get("", response_model=list[TestScenarioRead])
def list_scenarios(
    project_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TestScenarioRead]:
    require_project_for_user(session, owner_id=current_user.id, project_id=project_id)
    scenarios = scenario_service.list_scenarios(
        session,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    return [build_scenario_response(session, scenario) for scenario in scenarios]


@router.get("/{scenario_id}", response_model=TestScenarioRead)
def get_scenario(
    project_id: UUID,
    scenario_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TestScenarioRead:
    try:
        require_project_for_user(session, owner_id=current_user.id, project_id=project_id)
        scenario = scenario_service.get_scenario(
            session,
            project_id=project_id,
            scenario_id=scenario_id,
        )
    except scenario_service.ScenarioNotFoundError as exc:
        raise scenario_not_found() from exc

    return build_scenario_response(session, scenario)


@router.patch("/{scenario_id}", response_model=TestScenarioRead)
def update_scenario(
    project_id: UUID,
    scenario_id: UUID,
    payload: TestScenarioUpdate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TestScenarioRead:
    try:
        require_project_for_user(session, owner_id=current_user.id, project_id=project_id)
        scenario = scenario_service.update_scenario(
            session,
            project_id=project_id,
            scenario_id=scenario_id,
            payload=payload,
        )
    except scenario_service.ScenarioNotFoundError as exc:
        raise scenario_not_found() from exc

    return build_scenario_response(session, scenario)


@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scenario(
    project_id: UUID,
    scenario_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    try:
        require_project_for_user(session, owner_id=current_user.id, project_id=project_id)
        scenario_service.delete_scenario(
            session,
            project_id=project_id,
            scenario_id=scenario_id,
        )
    except scenario_service.ScenarioNotFoundError as exc:
        raise scenario_not_found() from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{scenario_id}/runs",
    response_model=ScenarioRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_scenario_run(
    project_id: UUID,
    scenario_id: UUID,
    payload: ScenarioRunCreate,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScenarioRunRead:
    _ = payload
    try:
        require_project_for_user(session, owner_id=current_user.id, project_id=project_id)
        scenario_run = scenario_service.create_scenario_run(
            session,
            project_id=project_id,
            scenario_id=scenario_id,
            requested_by_id=current_user.id,
        )
        scan_queue.enqueue_scenario_run(scenario_run_id=scenario_run.id)
    except scenario_service.ScenarioNotFoundError as exc:
        raise scenario_not_found() from exc
    except scenario_service.ScenarioInactiveError as exc:
        raise scenario_inactive() from exc
    except scan_queue.ScanQueueUnavailableError as exc:
        scenario_service.mark_scenario_run_failed(
            session,
            scenario_run_id=scenario_run.id,
            failure_reason="Scan queue is unavailable.",
        )
        raise scan_queue_unavailable() from exc

    return ScenarioRunRead.model_validate(scenario_run)


@router.get("/{scenario_id}/runs", response_model=list[ScenarioRunRead])
def list_scenario_runs(
    project_id: UUID,
    scenario_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ScenarioRunRead]:
    try:
        require_project_for_user(session, owner_id=current_user.id, project_id=project_id)
        scenario_service.get_scenario(session, project_id=project_id, scenario_id=scenario_id)
    except scenario_service.ScenarioNotFoundError as exc:
        raise scenario_not_found() from exc

    scenario_runs = scenario_service.list_scenario_runs(
        session,
        project_id=project_id,
        scenario_id=scenario_id,
        limit=limit,
        offset=offset,
    )
    return [ScenarioRunRead.model_validate(scenario_run) for scenario_run in scenario_runs]


@router.get("/{scenario_id}/runs/{scenario_run_id}", response_model=ScenarioRunDetailRead)
def get_scenario_run(
    project_id: UUID,
    scenario_id: UUID,
    scenario_run_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ScenarioRunDetailRead:
    try:
        require_project_for_user(session, owner_id=current_user.id, project_id=project_id)
        scenario_run = scenario_service.get_scenario_run(
            session,
            project_id=project_id,
            scenario_id=scenario_id,
            scenario_run_id=scenario_run_id,
        )
    except scenario_service.ScenarioRunNotFoundError as exc:
        raise scenario_run_not_found() from exc

    return build_scenario_run_response(session, scenario_run)
