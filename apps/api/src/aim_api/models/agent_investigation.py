from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from aim_api.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class AgentInvestigation(Base):
    """조사 에이전트의 조사 1건 — 결론 + 도구 호출 trace 전체.

    trace(tool_calls)가 UI 근거 타임라인·디버깅·포트폴리오 증거를 겸하고,
    generator가 결론 주체(rule / llm:<model> / rule-fallback)를 추적한다.
    """

    __tablename__ = "agent_investigations"
    __table_args__ = (
        CheckConstraint(
            (
                "root_cause IN ("
                "'service_down', 'ssl_invalid', 'server_slow', "
                "'frontend_regression', 'ui_regression', 'scenario_stale', "
                "'measurement_noise')"
            ),
            name="ck_agent_investigations_root_cause",
        ),
        CheckConstraint(
            "trigger IN ('incident', 'manual')",
            name="ck_agent_investigations_trigger",
        ),
        CheckConstraint(
            "feedback_verdict IS NULL OR feedback_verdict IN ('accurate', 'inaccurate')",
            name="ck_agent_investigations_feedback_verdict",
        ),
        CheckConstraint(
            (
                "feedback_root_cause IS NULL OR feedback_root_cause IN ("
                "'service_down', 'ssl_invalid', 'server_slow', "
                "'frontend_regression', 'ui_regression', 'scenario_stale', "
                "'measurement_noise')"
            ),
            name="ck_agent_investigations_feedback_root_cause",
        ),
        CheckConstraint(
            "duration_ms >= 0",
            name="ck_agent_investigations_duration_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 검사당 조사 1건 — 재조사는 새 검사(재검사 run)에 대한 조사로 남는다.
    check_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("check_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    incident_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("incidents.id", ondelete="SET NULL"),
        index=True,
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    root_cause: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[str] = mapped_column(String(8), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    # 결론 주체: "rule" | "llm:<model>" | "<이름>-fallback" (G4 추적)
    generator: Mapped[str] = mapped_column(String(64), nullable=False)
    recheck_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 재검사(ACT 도구)가 실제로 만든 검사 — 근거 링크용
    recheck_check_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("check_runs.id", ondelete="SET NULL"),
        index=True,
    )
    # 도구 호출 체인 [{step, tool, result_summary}] — UI 타임라인의 원천
    tool_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    # 미허용 도구 호출 시도(도구명 목록) — "무단 변경 시도 0건" 지표의 근거
    violations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # LLM 호출 실측 [{model, input_tokens, output_tokens, latency_ms}] — 비용 추적
    llm_calls: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # 사용자 피드백 — 이 조사가 맞았는지에 대한 실운영 라벨.
    #
    # ADR 0002가 스스로 밝혔듯 게이트를 통과시킨 test 83건은 전부 합성이고,
    # 그 100%는 "합성 분포 안에서의 상한"이지 실운영 정확도가 아니다. 문제는
    # 지금 구조로는 실운영 정확도를 **앞으로도 알 수 없다**는 점이었다 —
    # 사용자가 맞았다/틀렸다를 남길 채널이 아예 없었기 때문이다.
    # 여기 쌓이는 값이 다음 게이트를 실데이터로 칠 수 있게 하는 원자료다.
    feedback_verdict: Mapped[str | None] = mapped_column(String(16), index=True)
    # 틀렸다고 했을 때 사용자가 지목한 진짜 원인. 라벨로서 가장 값어치 있는 값이다.
    feedback_root_cause: Mapped[str | None] = mapped_column(String(32))
    feedback_note: Mapped[str | None] = mapped_column(Text)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    feedback_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )
