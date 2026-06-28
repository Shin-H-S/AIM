import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from aim_api.config import get_settings


@dataclass(frozen=True)
class StoredArtifact:
    artifact_type: str
    storage_backend: str
    storage_path: str
    content_type: str
    size_bytes: int
    checksum_sha256: str


def store_json_artifact(
    *,
    check_run_id: UUID,
    artifact_type: str,
    payload: dict[str, Any],
    relative_path: str,
) -> StoredArtifact:
    encoded_payload = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    storage_path = f"check-runs/{check_run_id}/{relative_path}"
    return store_binary_artifact(
        artifact_type=artifact_type,
        storage_path=storage_path,
        content_type="application/json",
        payload=encoded_payload,
    )


def store_binary_artifact(
    *,
    artifact_type: str,
    storage_path: str,
    content_type: str,
    payload: bytes,
) -> StoredArtifact:
    settings = get_settings()
    if settings.artifact_storage_backend != "local":
        raise ValueError("Only local artifact storage is implemented.")

    destination_path = Path(settings.artifact_local_root) / storage_path
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(payload)

    return StoredArtifact(
        artifact_type=artifact_type,
        storage_backend=settings.artifact_storage_backend,
        storage_path=storage_path,
        content_type=content_type,
        size_bytes=len(payload),
        checksum_sha256=hashlib.sha256(payload).hexdigest(),
    )
