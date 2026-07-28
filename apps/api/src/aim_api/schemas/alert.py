from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    opened_check_run_id: UUID
    resolved_check_run_id: UUID | None
    trigger_type: str
    severity: str
    status: str
    title: str
    summary: str
    evidence_json: dict[str, Any]
    started_at: datetime
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # 이 인시던트가 마지막으로 확인된 시점 — 해당 프로젝트의 최근 검사 시각.
    # 해소는 다음 검사가 돌아야 평가되므로, 이 값이 오래됐으면 인시던트는
    # 현재 상태가 아니라 과거를 말하고 있다.
    project_last_checked_at: datetime | None = None
    is_stale: bool = False


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    incident_id: UUID | None
    check_run_id: UUID | None
    alert_type: str
    trigger_type: str
    channel: str
    status: str
    recipient_email: str | None
    subject: str
    body: str
    delivery_attempts: int
    last_error: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
