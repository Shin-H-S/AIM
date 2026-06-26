from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from aim_api.models.check_run import CheckRunStatus


class CheckRunCreate(BaseModel):
    pass


class AvailabilityResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_url: str
    final_url: str | None
    is_available: bool
    status_code: int | None
    response_time_ms: int | None
    redirect_count: int
    uses_https: bool
    timed_out: bool
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class SslResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_url: str
    is_applicable: bool
    is_valid: bool | None
    expires_at: datetime | None
    days_until_expiration: int | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class LighthouseResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    service_url: str
    is_successful: bool
    performance_score: int | None
    accessibility_score: int | None
    seo_score: int | None
    best_practices_score: int | None
    largest_contentful_paint_ms: int | None
    cumulative_layout_shift: float | None
    total_blocking_time_ms: int | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


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


class CheckRunDetailRead(CheckRunRead):
    availability_result: AvailabilityResultRead | None
    ssl_result: SslResultRead | None
    lighthouse_result: LighthouseResultRead | None
