from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.scanner_result import Artifact


def record_artifact(
    session: Session,
    *,
    check_run_id: UUID | None = None,
    scenario_run_id: UUID | None = None,
    artifact_type: str,
    storage_backend: str,
    storage_path: str,
    content_type: str,
    size_bytes: int,
    checksum_sha256: str,
) -> Artifact:
    if check_run_id is None and scenario_run_id is None:
        raise ValueError("Artifact must belong to a check run or scenario run.")

    artifact = get_artifact_by_path(
        session,
        check_run_id=check_run_id,
        scenario_run_id=scenario_run_id,
        storage_path=storage_path,
    )
    if artifact is None:
        artifact = Artifact(check_run_id=check_run_id, scenario_run_id=scenario_run_id)
        session.add(artifact)

    artifact.artifact_type = artifact_type
    artifact.storage_backend = storage_backend
    artifact.storage_path = storage_path
    artifact.content_type = content_type
    artifact.size_bytes = size_bytes
    artifact.checksum_sha256 = checksum_sha256
    session.commit()
    session.refresh(artifact)
    return artifact


def get_artifact_by_path(
    session: Session,
    *,
    check_run_id: UUID | None = None,
    scenario_run_id: UUID | None = None,
    storage_path: str,
) -> Artifact | None:
    if check_run_id is None and scenario_run_id is None:
        raise ValueError("Artifact lookup must be scoped to a check run or scenario run.")

    return session.scalar(
        select(Artifact).where(
            Artifact.check_run_id == check_run_id
            if check_run_id is not None
            else Artifact.check_run_id.is_(None),
            Artifact.scenario_run_id == scenario_run_id
            if scenario_run_id is not None
            else Artifact.scenario_run_id.is_(None),
            Artifact.storage_path == storage_path,
        )
    )


def list_artifacts(
    session: Session,
    *,
    check_run_id: UUID,
) -> list[Artifact]:
    return list(
        session.scalars(
            select(Artifact)
            .where(Artifact.check_run_id == check_run_id)
            .order_by(Artifact.created_at.asc(), Artifact.id.asc())
        )
    )
