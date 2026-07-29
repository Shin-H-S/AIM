from datetime import datetime
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class ProjectEnvironment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ScoringPreset(StrEnum):
    SERVICE = "service"
    CONTENT = "content"
    INTERNAL = "internal"


MAX_WEBHOOK_URL_LENGTH = 1024


def normalize_webhook_url_input(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > MAX_WEBHOOK_URL_LENGTH:
            raise ValueError("Webhook URL is too long.")
        return normalized

    return value


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    service_url: HttpUrl
    description: str | None = Field(default=None, max_length=1000)
    environment: ProjectEnvironment = ProjectEnvironment.DEVELOPMENT
    scoring_preset: ScoringPreset = ScoringPreset.SERVICE
    scan_interval_minutes: int = Field(default=60, ge=1, le=43_200)
    scheduled_scans_enabled: bool = False
    response_time_threshold_ms: int = Field(default=2_000, ge=1, le=600_000)
    quality_score_threshold: int = Field(default=80, ge=0, le=100)
    alert_email_enabled: bool = False
    alert_recipient_email: EmailStr | None = None
    alert_webhook_url: HttpUrl | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Project name must not be blank.")
        return normalized

    @field_validator("alert_webhook_url", mode="before")
    @classmethod
    def normalize_alert_webhook_url(cls, value: Any) -> Any:
        return normalize_webhook_url_input(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("alert_recipient_email", mode="before")
    @classmethod
    def normalize_alert_recipient_email(cls, value: Any) -> Any:
        if value is None:
            return None

        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or None

        return value


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    service_url: HttpUrl | None = None
    description: str | None = Field(default=None, max_length=1000)
    environment: ProjectEnvironment | None = None
    scoring_preset: ScoringPreset | None = None
    scan_interval_minutes: int | None = Field(default=None, ge=1, le=43_200)
    scheduled_scans_enabled: bool | None = None
    response_time_threshold_ms: int | None = Field(default=None, ge=1, le=600_000)
    quality_score_threshold: int | None = Field(default=None, ge=0, le=100)
    alert_email_enabled: bool | None = None
    alert_recipient_email: EmailStr | None = None
    alert_webhook_url: HttpUrl | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("Project name must not be blank.")
        return normalized

    @field_validator("alert_webhook_url", mode="before")
    @classmethod
    def normalize_alert_webhook_url(cls, value: Any) -> Any:
        return normalize_webhook_url_input(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("alert_recipient_email", mode="before")
    @classmethod
    def normalize_alert_recipient_email(cls, value: Any) -> Any:
        if value is None:
            return None

        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or None

        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one project field must be provided.")
        return self


class ProjectBaselineUpdate(BaseModel):
    check_run_id: UUID


class ProjectRead(BaseModel):
    """조회 응답 — ProjectBase를 상속하지 않는다.

    상속하면 Create용 기본값이 응답 스키마에 그대로 실려, OpenAPI에서 이
    필드들이 전부 "생략 가능"으로 표현되고 생성된 프런트 타입이 불필요한
    optional 투성이가 된다. ORM 행에는 모든 컬럼이 항상 있다 — 응답 필드는
    전부 required이고, nullable 여부만 컬럼을 따른다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    name: str
    service_url: HttpUrl
    description: str | None
    environment: ProjectEnvironment
    scoring_preset: ScoringPreset
    scan_interval_minutes: int
    scheduled_scans_enabled: bool
    response_time_threshold_ms: int
    quality_score_threshold: int
    alert_email_enabled: bool
    alert_recipient_email: EmailStr | None
    alert_webhook_url: HttpUrl | None
    is_verified: bool
    baseline_check_run_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ProjectVerificationRead(BaseModel):
    project_id: UUID
    verification_token: str
    meta_tag: str
    is_verified: bool
    verified_at: datetime | None


class ProjectVerificationResult(ProjectVerificationRead):
    status: str
