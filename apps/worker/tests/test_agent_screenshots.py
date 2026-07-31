"""실패 스크린샷 로더 — 판별 호출에 실을 시각 증거의 수집 규칙.

계약: 실패 스텝의 스크린샷만, 스텝 순서대로 최대 2장, 읽을 수 없거나
규격 밖인 장은 건너뛴다. 스크린샷 부재가 조사를 죽여서는 안 된다.
"""

import base64
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from aim_api.config import get_settings
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import Artifact
from aim_api.models.scenario import ScenarioRun, ScenarioRunStatus, StepResult, TestScenario
from aim_api.models.user import User
from aim_worker.agent import screenshots
from aim_worker.agent.screenshots import build_screenshot_loader, load_failure_screenshots
from sqlalchemy.orm import Session

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-image-payload"


@pytest.fixture(autouse=True)
def artifact_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("ARTIFACT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("ARTIFACT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()
    try:
        yield tmp_path
    finally:
        get_settings.cache_clear()


def seed_check_run(session: Session) -> CheckRun:
    user = User(email=f"owner-{uuid4().hex[:8]}@example.com", password_hash="x")
    session.add(user)
    session.flush()
    project = Project(owner_id=user.id, name="svc", service_url="https://svc.example")
    session.add(project)
    session.flush()
    check_run = CheckRun(
        project_id=project.id,
        requested_by_id=user.id,
        status=CheckRunStatus.FAILED.value,
        trigger_source="manual",
    )
    session.add(check_run)
    session.commit()
    return check_run


def seed_failed_step_with_screenshot(
    session: Session,
    check_run: CheckRun,
    artifact_root: Path,
    *,
    step_order: int = 2,
    target: str | None = "#email",
    status: str = "FAILED",
    content_type: str = "image/png",
    payload: bytes | None = PNG_BYTES,
) -> StepResult:
    """실패 스텝 + 스크린샷 아티팩트 한 쌍을 심는다. payload=None이면 파일은 만들지 않는다."""
    scenario = TestScenario(project_id=check_run.project_id, name=f"s-{uuid4().hex[:6]}")
    session.add(scenario)
    session.flush()
    scenario_run = ScenarioRun(
        project_id=check_run.project_id,
        scenario_id=scenario.id,
        check_run_id=check_run.id,
        requested_by_id=check_run.requested_by_id,
        status=ScenarioRunStatus.FAILED.value,
    )
    session.add(scenario_run)
    session.flush()

    storage_path = f"scenario-runs/{scenario_run.id}/steps/{step_order}/failure.png"
    if payload is not None:
        destination = artifact_root / storage_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    artifact = Artifact(
        scenario_run_id=scenario_run.id,
        artifact_type="scenario_failure_screenshot",
        storage_backend="local",
        storage_path=storage_path,
        content_type=content_type,
        size_bytes=len(payload or b""),
        checksum_sha256="x" * 64,
    )
    session.add(artifact)
    session.flush()
    step = StepResult(
        scenario_run_id=scenario_run.id,
        step_order=step_order,
        action="fill",
        target=target,
        status=status,
        error_message="no element matches selector",
        failure_screenshot_artifact_id=artifact.id,
    )
    session.add(step)
    session.commit()
    return step


def test_loads_the_failed_step_screenshot(session: Session, artifact_root: Path) -> None:
    check_run = seed_check_run(session)
    seed_failed_step_with_screenshot(session, check_run, artifact_root)

    evidence = load_failure_screenshots(session, check_run_id=check_run.id)

    assert len(evidence) == 1
    assert evidence[0].media_type == "image/png"
    assert base64.b64decode(evidence[0].data_base64) == PNG_BYTES
    # 라벨만 보고도 어느 스텝의 장면인지 알 수 있어야 한다.
    assert "스텝 2" in evidence[0].label
    assert "#email" in evidence[0].label


def test_caps_the_evidence_at_two_screenshots(session: Session, artifact_root: Path) -> None:
    check_run = seed_check_run(session)
    for order in (3, 1, 2):
        seed_failed_step_with_screenshot(session, check_run, artifact_root, step_order=order)

    evidence = load_failure_screenshots(session, check_run_id=check_run.id)

    assert len(evidence) == screenshots.MAX_SCREENSHOTS
    # 스텝 순서대로 — 먼저 실패한 지점이 원인에 더 가깝다.
    assert "스텝 1" in evidence[0].label
    assert "스텝 2" in evidence[1].label


def test_skips_a_missing_file_instead_of_failing(session: Session, artifact_root: Path) -> None:
    """보존 정리가 파일을 먼저 지웠어도 조사는 이미지 없이 계속돼야 한다."""
    check_run = seed_check_run(session)
    seed_failed_step_with_screenshot(session, check_run, artifact_root, payload=None)

    assert load_failure_screenshots(session, check_run_id=check_run.id) == ()


def test_skips_oversized_and_non_image_artifacts(
    session: Session, artifact_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check_run = seed_check_run(session)
    seed_failed_step_with_screenshot(session, check_run, artifact_root, step_order=1)
    seed_failed_step_with_screenshot(
        session, check_run, artifact_root, step_order=2, content_type="application/json"
    )

    monkeypatch.setattr(screenshots, "MAX_IMAGE_BYTES", len(PNG_BYTES) - 1)
    assert load_failure_screenshots(session, check_run_id=check_run.id) == ()

    monkeypatch.setattr(screenshots, "MAX_IMAGE_BYTES", len(PNG_BYTES))
    evidence = load_failure_screenshots(session, check_run_id=check_run.id)
    assert len(evidence) == 1
    assert "스텝 1" in evidence[0].label


def test_passed_steps_contribute_no_screenshots(session: Session, artifact_root: Path) -> None:
    check_run = seed_check_run(session)
    seed_failed_step_with_screenshot(session, check_run, artifact_root, status="PASSED")

    assert load_failure_screenshots(session, check_run_id=check_run.id) == ()


def test_the_loader_is_bound_to_its_check_run(session: Session, artifact_root: Path) -> None:
    ours = seed_check_run(session)
    theirs = seed_check_run(session)
    seed_failed_step_with_screenshot(session, theirs, artifact_root)

    assert build_screenshot_loader(session, check_run_id=ours.id)() == ()
    assert len(build_screenshot_loader(session, check_run_id=theirs.id)()) == 1
