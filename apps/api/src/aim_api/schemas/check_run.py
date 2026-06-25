from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from aim_api.models.check_run import CheckRunStatus


class CheckRunCreate(BaseModel):
    pass


class CheckRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    requested_by_id: UUID
    status: CheckRunStatus
    trigger_source: str
    failure_reason: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
