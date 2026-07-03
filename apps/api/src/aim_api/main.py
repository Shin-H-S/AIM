from fastapi import FastAPI

from aim_api.config import get_settings
from aim_api.routers.alerts import router as alerts_router
from aim_api.routers.artifacts import router as artifacts_router
from aim_api.routers.auth import router as auth_router
from aim_api.routers.check_runs import router as check_runs_router
from aim_api.routers.database_health import router as database_health_router
from aim_api.routers.health import router as health_router
from aim_api.routers.projects import router as projects_router
from aim_api.routers.scenarios import router as scenarios_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AIM API",
        version="0.1.0",
        debug=settings.app_env == "development",
    )
    app.include_router(health_router)
    app.include_router(database_health_router)
    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(check_runs_router)
    app.include_router(scenarios_router)
    app.include_router(alerts_router)
    app.include_router(artifacts_router)
    return app


app = create_app()
