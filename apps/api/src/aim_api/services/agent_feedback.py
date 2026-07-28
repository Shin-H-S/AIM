"""조사 결과에 대한 사용자 피드백 — 실운영 라벨 수집.

**왜 필요한가**: ADR 0002는 게이트를 통과시킨 test 83건이 전부 합성 케이스이고
그 100%가 "합성 분포 안에서의 상한이지 실운영 정확도가 아니다"라고 스스로
못 박았다. 그런데 사용자가 "이 진단 맞았나요"에 답할 채널이 없어서, **실운영
정확도는 앞으로도 영원히 알 수 없는 구조**였다.

여기 쌓이는 값이 다음 게이트를 합성이 아닌 실데이터로 칠 수 있게 하는 원자료다.
특히 `feedback_root_cause`(틀렸을 때 사용자가 지목한 진짜 원인)가 라벨로서
가장 값어치 있다 — 그것 없이는 "틀렸다"는 사실만 알고 무엇이 맞는지는 모른다.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.agent_investigation import AgentInvestigation

ACCURATE_VERDICT = "accurate"
INACCURATE_VERDICT = "inaccurate"
FEEDBACK_VERDICTS = frozenset({ACCURATE_VERDICT, INACCURATE_VERDICT})

ROOT_CAUSES = frozenset(
    {
        "service_down",
        "ssl_invalid",
        "server_slow",
        "frontend_regression",
        "ui_regression",
        "scenario_stale",
        "measurement_noise",
    }
)

MAX_FEEDBACK_NOTE_LENGTH = 2_000


class InvestigationNotFoundError(Exception):
    """Raised when the investigation being rated does not exist."""


class InvalidFeedbackError(Exception):
    """Raised when the submitted feedback is not a usable label."""


def validate_feedback(*, verdict: str, root_cause: str | None, note: str | None) -> None:
    if verdict not in FEEDBACK_VERDICTS:
        raise InvalidFeedbackError(f"Unknown verdict: {verdict!r}")

    if root_cause is not None and root_cause not in ROOT_CAUSES:
        raise InvalidFeedbackError(f"Unknown root cause: {root_cause!r}")

    # "틀렸다"면서 무엇이 맞는지 말하지 않으면 라벨이 되지 못한다. 다만 사용자가
    # 원인을 모를 수도 있으므로 강제하지는 않고, 그 경우 집계에서 제외된다.
    if verdict == ACCURATE_VERDICT and root_cause is not None:
        raise InvalidFeedbackError("An accurate verdict cannot also correct the root cause.")

    if note is not None and len(note) > MAX_FEEDBACK_NOTE_LENGTH:
        raise InvalidFeedbackError("Feedback note is too long.")


def record_feedback(
    session: Session,
    *,
    check_run_id: UUID,
    user_id: UUID,
    verdict: str,
    root_cause: str | None = None,
    note: str | None = None,
    now: datetime | None = None,
) -> AgentInvestigation:
    """피드백을 남긴다. 같은 조사에 다시 남기면 덮어쓴다 — 사람은 마음을 바꾼다."""
    validate_feedback(verdict=verdict, root_cause=root_cause, note=note)

    investigation = session.scalars(
        select(AgentInvestigation).where(AgentInvestigation.check_run_id == check_run_id)
    ).first()
    if investigation is None:
        raise InvestigationNotFoundError

    investigation.feedback_verdict = verdict
    investigation.feedback_root_cause = root_cause
    investigation.feedback_note = note
    investigation.feedback_by_id = user_id
    investigation.feedback_at = now or datetime.now(UTC)

    session.commit()
    session.refresh(investigation)
    return investigation


def clear_feedback(session: Session, *, check_run_id: UUID) -> AgentInvestigation:
    """피드백을 되돌린다 — 잘못 누른 값이 라벨로 굳으면 안 된다."""
    investigation = session.scalars(
        select(AgentInvestigation).where(AgentInvestigation.check_run_id == check_run_id)
    ).first()
    if investigation is None:
        raise InvestigationNotFoundError

    investigation.feedback_verdict = None
    investigation.feedback_root_cause = None
    investigation.feedback_note = None
    investigation.feedback_by_id = None
    investigation.feedback_at = None

    session.commit()
    session.refresh(investigation)
    return investigation
