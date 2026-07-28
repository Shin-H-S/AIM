import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from aim_api.config import get_settings
from aim_worker.artifacts import (
    delete_local_artifact,
    store_binary_artifact,
    store_json_artifact,
)


def test_store_json_artifact_writes_local_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_run_id = uuid4()
    payload = {"categories": {"performance": {"score": 0.9}}}
    monkeypatch.setenv("ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ARTIFACT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()

    try:
        artifact = store_json_artifact(
            check_run_id=check_run_id,
            artifact_type="lighthouse_raw_json",
            payload=payload,
            relative_path="lighthouse/raw.json",
        )
    finally:
        get_settings.cache_clear()

    expected_storage_path = f"check-runs/{check_run_id}/lighthouse/raw.json"
    expected_bytes = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")

    assert artifact.artifact_type == "lighthouse_raw_json"
    assert artifact.storage_backend == "local"
    assert artifact.storage_path == expected_storage_path
    assert artifact.content_type == "application/json"
    assert artifact.size_bytes == len(expected_bytes)
    assert artifact.checksum_sha256 == hashlib.sha256(expected_bytes).hexdigest()
    assert (tmp_path / expected_storage_path).read_bytes() == expected_bytes


def test_store_binary_artifact_writes_local_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_run_id = uuid4()
    payload = b"fake-png"
    storage_path = f"scenario-runs/{scenario_run_id}/steps/1/failure.png"
    monkeypatch.setenv("ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ARTIFACT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()

    try:
        artifact = store_binary_artifact(
            artifact_type="scenario_failure_screenshot",
            storage_path=storage_path,
            content_type="image/png",
            payload=payload,
        )
    finally:
        get_settings.cache_clear()

    assert artifact.artifact_type == "scenario_failure_screenshot"
    assert artifact.storage_backend == "local"
    assert artifact.storage_path == storage_path
    assert artifact.content_type == "image/png"
    assert artifact.size_bytes == len(payload)
    assert artifact.checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert (tmp_path / storage_path).read_bytes() == payload


def test_delete_local_artifact_removes_the_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_path = f"check-runs/{uuid4()}/lighthouse/raw.json"
    monkeypatch.setenv("ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ARTIFACT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()

    try:
        store_binary_artifact(
            artifact_type="lighthouse_raw_json",
            storage_path=storage_path,
            content_type="application/json",
            payload=b"{}",
        )

        assert delete_local_artifact(storage_path) is True
    finally:
        get_settings.cache_clear()

    assert not (tmp_path / storage_path).exists()


def test_delete_local_artifact_prunes_the_emptied_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """파일만 지우면 검사별 빈 디렉토리가 영구히 남는다."""
    check_run_id = uuid4()
    storage_path = f"check-runs/{check_run_id}/lighthouse/raw.json"
    monkeypatch.setenv("ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ARTIFACT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()

    try:
        store_binary_artifact(
            artifact_type="lighthouse_raw_json",
            storage_path=storage_path,
            content_type="application/json",
            payload=b"{}",
        )
        delete_local_artifact(storage_path)
    finally:
        get_settings.cache_clear()

    assert not (tmp_path / "check-runs" / str(check_run_id)).exists()
    assert tmp_path.exists()


def test_delete_local_artifact_keeps_directories_that_still_hold_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_run_id = uuid4()
    deleted_path = f"check-runs/{check_run_id}/lighthouse/raw.json"
    kept_path = f"check-runs/{check_run_id}/availability.json"
    monkeypatch.setenv("ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ARTIFACT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()

    try:
        for storage_path in (deleted_path, kept_path):
            store_binary_artifact(
                artifact_type="lighthouse_raw_json",
                storage_path=storage_path,
                content_type="application/json",
                payload=b"{}",
            )
        delete_local_artifact(deleted_path)
    finally:
        get_settings.cache_clear()

    assert (tmp_path / kept_path).exists()


def test_delete_local_artifact_reports_a_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이미 지워진 파일이어도 예외 없이 False — 레코드 정리는 이어져야 한다."""
    monkeypatch.setenv("ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ARTIFACT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()

    try:
        assert delete_local_artifact("check-runs/gone/raw.json") is False
    finally:
        get_settings.cache_clear()


def test_delete_local_artifact_refuses_to_escape_the_artifact_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """storage_path는 DB 값이라 신뢰 대상이 아니다 — 루트 밖은 지우지 않는다."""
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("keep me")
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    monkeypatch.setenv("ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ARTIFACT_LOCAL_ROOT", str(artifact_root))
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match="escapes the artifact root"):
            delete_local_artifact("../outside.txt")
    finally:
        get_settings.cache_clear()

    assert outside_file.exists()
