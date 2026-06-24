from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


class ProjectEnvironment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    service_url: HttpUrl
    description: str | None = Field(default=None, max_length=1000)
    environment: ProjectEnvironment = ProjectEnvironment.DEVELOPMENT
    scan_interval_minutes: int = Field(default=60, ge=1, le=43_200)
    response_time_threshold_ms: int = Field(default=2_000, ge=1, le=600_000)
    quality_score_threshold: int = Field(default=80, ge=0, le=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Project name must not be blank.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    service_url: HttpUrl | None = None
    description: str | None = Field(default=None, max_length=1000)
    environment: ProjectEnvironment | None = None
    scan_interval_minutes: int | None = Field(default=None, ge=1, le=43_200)
    response_time_threshold_ms: int | None = Field(default=None, ge=1, le=600_000)
    quality_score_threshold: int | None = Field(default=None, ge=0, le=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("Project name must not be blank.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one project field must be provided.")
        return self


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
