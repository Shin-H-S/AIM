from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentToolCallRead(BaseModel):
    step: int
    tool: str
    result_summary: str


class AgentLlmCallRead(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class AgentInvestigationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    check_run_id: UUID
    incident_id: UUID | None
    trigger: str
    root_cause: str
    confidence: str
    summary: str
    recommendation: str
    generator: str
    recheck_used: bool
    recheck_check_run_id: UUID | None
    tool_calls: list[AgentToolCallRead]
    violations: list[str]
    llm_calls: list[AgentLlmCallRead]
    duration_ms: int
    feedback_verdict: str | None
    feedback_root_cause: str | None
    feedback_note: str | None
    feedback_at: datetime | None
    created_at: datetime


class AgentInvestigationEnqueueRead(BaseModel):
    task_id: str


class AgentInvestigationFeedbackWrite(BaseModel):
    """조사가 맞았는지에 대한 사용자 판정.

    verdict가 "inaccurate"일 때 root_cause를 함께 주면 그것이 실운영 라벨이 된다.
    원인을 모르면 비워도 되지만, 그 경우 정확도 집계의 분모에만 들어간다.
    """

    verdict: Literal["accurate", "inaccurate"]
    root_cause: (
        Literal[
            "service_down",
            "ssl_invalid",
            "server_slow",
            "frontend_regression",
            "ui_regression",
            "scenario_stale",
            "measurement_noise",
        ]
        | None
    ) = None
    note: str | None = Field(default=None, max_length=2_000)
