from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Token name must not be blank.")
        return normalized


class ProjectApiTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class ProjectApiTokenIssuedRead(ProjectApiTokenRead):
    # 생성 응답에서 1회만 노출된다. 이후에는 다시 조회할 수 없다.
    token: str


class DeployHookCheckRunCreate(BaseModel):
    deploy_ref: str | None = Field(default=None, max_length=255)

    @field_validator("deploy_ref")
    @classmethod
    def normalize_deploy_ref(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None
