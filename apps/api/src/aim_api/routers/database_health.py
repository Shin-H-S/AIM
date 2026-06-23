from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from aim_api.database import get_db

router = APIRouter(tags=["health"])


class DatabaseHealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["available"]


@router.get("/health/database", response_model=DatabaseHealthResponse)
def database_health_check(
    session: Annotated[Session, Depends(get_db)],
) -> DatabaseHealthResponse:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable.",
        ) from exc

    return DatabaseHealthResponse(status="ok", database="available")
