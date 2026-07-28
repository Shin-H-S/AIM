import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aim_api.config import get_settings
from aim_api.observability import (
    REQUEST_ID_HEADER,
    configure_logging,
    new_request_id,
    request_id_context,
    request_id_var,
)
from aim_api.routers.agent_investigations import router as agent_investigations_router
from aim_api.routers.alerts import router as alerts_router
from aim_api.routers.artifacts import router as artifacts_router
from aim_api.routers.auth import router as auth_router
from aim_api.routers.check_runs import router as check_runs_router
from aim_api.routers.database_health import router as database_health_router
from aim_api.routers.deploy_hooks import router as deploy_hooks_router
from aim_api.routers.health import router as health_router
from aim_api.routers.project_api_tokens import router as project_api_tokens_router
from aim_api.routers.projects import router as projects_router
from aim_api.routers.scenarios import router as scenarios_router
from aim_api.services.ops_alerts import notify_ops

logger = logging.getLogger(__name__)

UNHANDLED_EXCEPTION_MESSAGE = "Unhandled exception while serving a request."

RequestHandler = Callable[[Request], Awaitable[Response]]


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    app = FastAPI(
        title="AIM API",
        version="0.1.0",
        debug=settings.app_env == "development",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next: RequestHandler) -> Response:
        """요청 하나를 상관관계 id로 묶는다.

        프록시나 CI가 넘긴 X-Request-ID가 있으면 이어받아, 클라이언트 쪽 로그와
        서버 로그를 같은 키로 맞출 수 있게 한다.
        """
        incoming_request_id = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming_request_id or new_request_id()

        with request_id_context(request_id):
            response = await call_next(request)

        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        """미처리 예외를 남기고 운영자에게 알린다.

        지금까지 미처리 예외는 stdout으로 흘러가고 끝이라 아무도 몰랐다.
        사용자에게는 내부 정보를 노출하지 않고 request_id만 돌려줘, 문의가 오면
        그 키로 로그를 바로 찾을 수 있게 한다.
        """
        request_id = request_id_var.get()
        logger.exception(
            UNHANDLED_EXCEPTION_MESSAGE,
            extra={"path": request.url.path, "method": request.method},
        )
        notify_ops(
            title="API unhandled exception",
            detail=f"{request.method} {request.url.path}\n{type(exc).__name__}: {exc}",
            request_id=request_id,
            settings=settings,
        )

        headers = {REQUEST_ID_HEADER: request_id} if request_id else None
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error.", "request_id": request_id},
            headers=headers,
        )

    app.include_router(health_router)
    app.include_router(database_health_router)
    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(project_api_tokens_router)
    app.include_router(check_runs_router)
    app.include_router(agent_investigations_router)
    app.include_router(deploy_hooks_router)
    app.include_router(scenarios_router)
    app.include_router(alerts_router)
    app.include_router(artifacts_router)
    return app


app = create_app()
