import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from aim_api.config import get_settings
from aim_worker.artifacts import store_binary_artifact, store_json_artifact


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
