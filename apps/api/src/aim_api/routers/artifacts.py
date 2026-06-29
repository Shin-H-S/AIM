from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from aim_api.config import get_settings
from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.scanner_result import Artifact
from aim_api.models.user import User
from aim_api.services import artifacts as artifact_service

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


def artifact_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Artifact not found.",
    )


def artifact_not_downloadable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Artifact storage backend is not downloadable.",
    )


def resolve_local_artifact_path(artifact: Artifact) -> Path:
    settings = get_settings()
    if artifact.storage_backend != "local":
        raise ValueError("Unsupported artifact storage backend.")

    artifact_root = Path(settings.artifact_local_root).resolve()
    artifact_path = (artifact_root / artifact.storage_path).resolve()
    if not artifact_path.is_relative_to(artifact_root):
        raise FileNotFoundError

    if not artifact_path.is_file():
        raise FileNotFoundError

    return artifact_path


@router.get("/{artifact_id}/download", response_class=FileResponse)
def download_artifact(
    artifact_id: UUID,
    session: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    try:
        artifact = artifact_service.get_accessible_artifact(
            session,
            artifact_id=artifact_id,
            owner_id=current_user.id,
        )
    except artifact_service.ArtifactNotFoundError as exc:
        raise artifact_not_found() from exc

    if artifact.storage_backend != "local":
        raise artifact_not_downloadable()

    try:
        artifact_path = resolve_local_artifact_path(artifact)
    except FileNotFoundError as exc:
        raise artifact_not_found() from exc

    return FileResponse(
        path=artifact_path,
        media_type=artifact.content_type,
        filename=Path(artifact.storage_path).name,
    )
