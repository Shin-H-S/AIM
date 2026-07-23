from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
    created_at: datetime


class AgentInvestigationEnqueueRead(BaseModel):
    task_id: str
