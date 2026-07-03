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


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    incident_id: UUID
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
