from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from aim_api.models.check_run import CheckRunStatus
from aim_api.schemas.scenario import ScenarioRunRead


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


class LighthouseAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: str
    title: str
    display_value: str | None = None
    score: float | None = None
    savings_ms: int | None = None
    savings_bytes: int | None = None


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
    top_audits: list[LighthouseAuditRead] | None = None
    raw_json_artifact_id: UUID | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class ArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artifact_type: str
    storage_backend: str
    storage_path: str
    content_type: str
    size_bytes: int
    checksum_sha256: str
    created_at: datetime


class ScoreResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    availability_score: int | None
    functional_stability_score: int | None
    web_performance_score: int | None
    accessibility_score: int | None
    seo_basic_quality_score: int | None
    regression_stability_score: int | None
    overall_score: int
    evaluated_weight: int
    grade: str
    deployment_risk: str
    gate_reason: str | None
    score_breakdown: dict[str, Any] | None = None
    scoring_version: str
    created_at: datetime
    updated_at: datetime


class RunComparisonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    baseline_check_run_id: UUID
    comparison_type: str
    overall_score_delta: int | None
    availability_score_delta: int | None
    web_performance_score_delta: int | None
    accessibility_score_delta: int | None
    seo_basic_quality_score_delta: int | None
    response_time_delta_ms: int | None
    performance_score_delta: int | None
    deployment_risk_changed: bool
    summary: str
    created_at: datetime
    updated_at: datetime


class BaselineComparisonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_run_id: UUID
    baseline_check_run_id: UUID
    comparison_type: str
    overall_score_delta: int
    availability_score_delta: int | None
    web_performance_score_delta: int | None
    accessibility_score_delta: int | None
    seo_basic_quality_score_delta: int | None
    response_time_delta_ms: int | None
    performance_score_delta: int | None
    current_deployment_risk: str
    baseline_deployment_risk: str
    deployment_risk_changed: bool
    summary: str


class AIReportSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    check_run_id: UUID
    summary: str
    overall_score: int
    grade: str
    deployment_risk: str
    gate_reason: str | None
    generated_at: datetime
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


class CheckRunScoreSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overall_score: int
    grade: str
    deployment_risk: str


class CheckRunListItemRead(CheckRunRead):
    score: CheckRunScoreSummaryRead | None = None


class CheckRunDetailRead(CheckRunRead):
    availability_result: AvailabilityResultRead | None
    ssl_result: SslResultRead | None
    lighthouse_result: LighthouseResultRead | None
    score_result: ScoreResultRead | None
    comparison_result: RunComparisonRead | None
    ai_report: AIReportSummaryRead | None
    artifacts: list[ArtifactRead]
    linked_scenario_runs: list[ScenarioRunRead]
