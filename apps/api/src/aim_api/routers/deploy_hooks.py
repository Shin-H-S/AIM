from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.models.project import Project
from aim_api.schemas.check_run import CheckRunRead
from aim_api.schemas.project_api_token import DeployHookCheckRunCreate
from aim_api.services import check_runs as check_run_service
from aim_api.services import project_api_tokens as token_service
from aim_api.services import scan_queue
from aim_api.services import scenarios as scenario_service
from aim_api.services.rate_limit import rate_limited

router = APIRouter(prefix="/hooks", tags=["deploy-hooks"])

# JWT 로그인과 분리된 프로젝트 토큰 전용 스킴. auto_error=False로 직접 401을 만든다.
bearer_scheme = HTTPBearer(auto_error=False)

# 토큰 브루트포스 방지. CI 재시도에는 여유가 있는 수준으로 잡는다.
deploy_hook_rate_limit = rate_limited("deploy-hook", limit=30)


def invalid_deploy_token() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing deploy token.",
    )


def project_not_verified() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Project domain is not verified.",
    )


def check_run_already_active() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A check run is already active for this project.",
    )


def scan_queue_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Scan queue is unavailable.",
    )


@router.post(
    "/projects/{project_id}/check-runs",
    response_model=CheckRunRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(deploy_hook_rate_limit)],
)
def trigger_deploy_check_run(
    project_id: UUID,
    payload: DeployHookCheckRunCreate,
    session: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CheckRunRead:
    if credentials is None:
        raise invalid_deploy_token()

    token = token_service.authenticate_token(
        session,
        project_id=project_id,
        plaintext=credentials.credentials,
    )
    if token is None:
        raise invalid_deploy_token()

    project = session.get(Project, project_id)
    if project is None or project.owner_id is None:
        raise invalid_deploy_token()

    # 배포 훅 반복 호출로 큐가 쌓이지 않도록 활성 검사가 있으면 거절한다.
    if check_run_service.has_active_check_run(session, project_id=project.id):
        raise check_run_already_active()

    try:
        check_run = check_run_service.create_check_run(
            session,
            project=project,
            requested_by_id=project.owner_id,
            trigger_source="deploy",
            deploy_ref=payload.deploy_ref,
        )
        scenario_runs = scenario_service.create_scenario_runs_for_check_run(
            session,
            project_id=project.id,
            check_run_id=check_run.id,
            requested_by_id=project.owner_id,
        )
        scan_queue.enqueue_check_run(check_run_id=check_run.id)
        for scenario_run in scenario_runs:
            scan_queue.enqueue_scenario_run(scenario_run_id=scenario_run.id)
    except check_run_service.ProjectNotVerifiedError as exc:
        raise project_not_verified() from exc
    except scan_queue.ScanQueueUnavailableError as exc:
        check_run_service.mark_check_run_failed(
            session,
            check_run_id=check_run.id,
            failure_reason="Scan queue is unavailable.",
        )
        for scenario_run in scenario_service.list_scenario_runs_for_check_run(
            session,
            check_run_id=check_run.id,
        ):
            scenario_service.mark_scenario_run_failed(
                session,
                scenario_run_id=scenario_run.id,
                failure_reason="Scan queue is unavailable.",
            )
        raise scan_queue_unavailable() from exc

    return CheckRunRead.model_validate(check_run)
