"""실패 스크린샷 판독 — W5에서 미뤄 둔 마지막 증거 채널.

판독을 별도 vision 전처리 호출로 두지 않고, 3자 판별 호출에 이미지를
동봉한다. 이유 셋:

1. 요약보다 원본이 낫다 — failing_page_rendered_ok 같은 불리언 요약은
   판독 호출을 한 번 더 쓰고도 정보를 깎는다. 판별자가 픽셀을 직접 보면
   "에러 배너가 떠 있다"와 "폼이 통째로 사라졌다"를 스스로 가른다.
2. 비용 계측이 공짜다 — 판별 호출의 usage에 이미지 토큰이 그대로 잡혀
   기존 예산 서킷브레이커(JudgeCall → llm_calls) 밖으로 새는 지출이 없다.
3. 규칙 전용 경로는 이미지가 필요 없다 — 로더는 LLM 정책에만 물리므로
   API 키가 없거나 예산이 소진된 조사는 여전히 비용 0으로 돈다.

로더는 증거를 '가능하면' 싣는다: 파일 소실·크기 초과·타입 불일치는 그
장만 건너뛰고 조사를 계속한다. 스크린샷이 없다고 조사가 죽으면 안 된다.
"""

import base64
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from aim_api.config import get_settings
from aim_api.models.scanner_result import Artifact
from aim_api.models.scenario import ScenarioRun, StepResult, StepResultStatus
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 실패 스텝은 보통 하나지만, 시나리오가 여럿이면 각자의 실패 장면이 있다.
# 두 장이면 판별에 충분하고, 그 이상은 토큰만 태운다.
MAX_SCREENSHOTS = 2
# base64 팽창(4/3) 후에도 API 이미지 한도(5MB) 아래로 남는 크기.
MAX_IMAGE_BYTES = 3 * 1024 * 1024
ALLOWED_MEDIA_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})


@dataclass(frozen=True)
class ScreenshotEvidence:
    """판별 호출에 동봉할 이미지 한 장."""

    label: str
    media_type: str
    data_base64: str


ScreenshotLoader = Callable[[], tuple[ScreenshotEvidence, ...]]


def load_failure_screenshots(
    session: Session, *, check_run_id: UUID
) -> tuple[ScreenshotEvidence, ...]:
    """이 검사의 실패 스텝들이 남긴 스크린샷을 읽는다(최대 MAX_SCREENSHOTS장)."""
    failed_steps = session.execute(
        select(StepResult, Artifact)
        .join(ScenarioRun, StepResult.scenario_run_id == ScenarioRun.id)
        .join(Artifact, StepResult.failure_screenshot_artifact_id == Artifact.id)
        .where(
            ScenarioRun.check_run_id == check_run_id,
            StepResult.status == StepResultStatus.FAILED.value,
        )
        .order_by(StepResult.step_order)
        .limit(MAX_SCREENSHOTS)
    ).all()

    evidence: list[ScreenshotEvidence] = []
    for step, artifact in failed_steps:
        image = read_screenshot(step, artifact)
        if image is not None:
            evidence.append(image)
    return tuple(evidence)


def read_screenshot(step: StepResult, artifact: Artifact) -> ScreenshotEvidence | None:
    if artifact.content_type not in ALLOWED_MEDIA_TYPES:
        logger.info(
            "Failure screenshot skipped: unsupported media type.",
            extra={"artifact_id": str(artifact.id), "content_type": artifact.content_type},
        )
        return None

    path = Path(get_settings().artifact_local_root) / artifact.storage_path
    try:
        payload = path.read_bytes()
    except OSError:
        # 보존 정리로 지워졌거나 디스크 문제 — 이 장 없이 조사를 계속한다.
        logger.warning(
            "Failure screenshot skipped: file unreadable.",
            extra={"artifact_id": str(artifact.id), "storage_path": artifact.storage_path},
        )
        return None

    if len(payload) > MAX_IMAGE_BYTES:
        logger.info(
            "Failure screenshot skipped: larger than the evidence limit.",
            extra={"artifact_id": str(artifact.id), "size_bytes": len(payload)},
        )
        return None

    target = step.target or step.action
    return ScreenshotEvidence(
        label=f"실패 스텝 {step.step_order}({target})의 실패 시점 스크린샷",
        media_type=artifact.content_type,
        data_base64=base64.b64encode(payload).decode("ascii"),
    )


def build_screenshot_loader(session: Session, *, check_run_id: UUID) -> ScreenshotLoader:
    """조사 한 건에 물릴 지연 로더 — LLM 경로에 실제로 들어갈 때만 파일을 읽는다."""

    def load() -> tuple[ScreenshotEvidence, ...]:
        return load_failure_screenshots(session, check_run_id=check_run_id)

    return load
