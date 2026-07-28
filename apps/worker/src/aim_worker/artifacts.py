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


def delete_local_artifact(storage_path: str) -> bool:
    """보존 기간이 지난 아티팩트 파일을 지운다. 이미 없으면 False.

    storage_path는 DB에 저장된 값이라 신뢰 대상이 아니다. 정규화 후 루트 밖을
    가리키면 삭제하지 않는다 — 조회 경로(routers/artifacts.py)와 같은 방어다.
    삭제 자체는 멱등해야 한다: 파일이 이미 없어도 예외를 던지지 않고 레코드
    정리가 이어지게 한다.
    """
    settings = get_settings()
    artifact_root = Path(settings.artifact_local_root).resolve()
    artifact_path = (artifact_root / storage_path).resolve()

    if not artifact_path.is_relative_to(artifact_root):
        raise ValueError("Artifact path escapes the artifact root.")

    if not artifact_path.is_file():
        return False

    artifact_path.unlink()
    prune_empty_parents(artifact_path.parent, artifact_root)
    return True


def prune_empty_parents(directory: Path, root: Path) -> None:
    """비워진 검사별 디렉토리를 루트까지 거슬러 정리한다.

    파일만 지우면 check-runs/<uuid>/ 빈 디렉토리가 영구히 남아 inode를 먹는다.
    """
    current = directory
    while current != root and current.is_relative_to(root):
        try:
            current.rmdir()
        except OSError:
            # 비어 있지 않거나 이미 사라졌다 — 더 올라갈 이유가 없다.
            return
        current = current.parent
