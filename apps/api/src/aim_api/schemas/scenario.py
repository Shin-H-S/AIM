import re
from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aim_api.models.scenario import ScenarioRunStatus, StepResultStatus


class TestStepAction(StrEnum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    WAIT = "wait"
    ASSERT_ELEMENT_EXISTS = "assert_element_exists"
    ASSERT_TEXT_EXISTS = "assert_text_exists"
    ASSERT_URL = "assert_url"
    TAKE_SCREENSHOT = "take_screenshot"


# fill 값의 시크릿 참조 문법. DB에는 참조만 저장되고 실제 값은 워커가 실행 시점에
# SCENARIO_SECRET_<NAME> 환경변수(또는 시크릿 파일)에서 주입한다.
SECRET_REFERENCE_PATTERN = re.compile(r"\{\{\s*secret:([A-Z][A-Z0-9_]*)\s*\}\}")
SECRET_REFERENCE_HINT = "{{secret:NAME}} (NAME은 대문자·숫자·밑줄, 대문자로 시작)"


def validate_secret_references(value: str) -> None:
    """secret 참조처럼 보이는 조각이 있으면 문법이 정확한지 검사한다."""
    remaining = SECRET_REFERENCE_PATTERN.sub("", value)
    if "{{" in remaining and "secret" in remaining.lower():
        raise ValueError(f"시크릿 참조 문법이 잘못되었습니다. 올바른 형식: {SECRET_REFERENCE_HINT}")


class TestStepBase(BaseModel):
    action: TestStepAction
    target: str | None = Field(default=None, min_length=1, max_length=2048)
    value: str | None = Field(default=None, min_length=1, max_length=10_000)
    timeout_ms: int | None = Field(default=None, ge=1, le=120_000)
    is_critical: bool = True

    @field_validator("target", "value")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_action_fields(self) -> Self:
        if (
            self.action
            in {
                TestStepAction.NAVIGATE,
                TestStepAction.CLICK,
                TestStepAction.ASSERT_ELEMENT_EXISTS,
            }
            and self.target is None
        ):
            raise ValueError(f"{self.action.value} step requires target.")

        if self.action == TestStepAction.FILL and (self.target is None or self.value is None):
            raise ValueError("fill step requires target and value.")

        if self.action == TestStepAction.FILL and self.value is not None:
            validate_secret_references(self.value)

        if (
            self.action
            in {
                TestStepAction.ASSERT_TEXT_EXISTS,
                TestStepAction.ASSERT_URL,
            }
            and self.value is None
        ):
            raise ValueError(f"{self.action.value} step requires value.")

        if self.action == TestStepAction.WAIT and self.timeout_ms is None:
            raise ValueError("wait step requires timeout_ms.")

        return self


class TestStepCreate(TestStepBase):
    pass


class TestStepRead(TestStepBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scenario_id: UUID
    step_order: int
    created_at: datetime
    updated_at: datetime


class TestScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool = True
    steps: list[TestStepCreate] = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Scenario name must not be blank.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None


class TestScenarioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None
    steps: list[TestStepCreate] | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("Scenario name must not be blank.")
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
            raise ValueError("At least one scenario field must be provided.")
        return self


class TestScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    steps: list[TestStepRead]


class ScenarioRunCreate(BaseModel):
    pass


class StepResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scenario_run_id: UUID
    test_step_id: UUID | None
    step_order: int
    action: TestStepAction
    target: str | None
    status: StepResultStatus
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error_message: str | None
    failure_screenshot_artifact_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ConsoleErrorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scenario_run_id: UUID
    level: str
    message: str
    source_url: str | None
    line_number: int | None
    column_number: int | None
    created_at: datetime


class NetworkFailureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scenario_run_id: UUID
    request_url: str
    method: str
    resource_type: str | None
    failure_text: str | None
    created_at: datetime


class ScenarioRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    scenario_id: UUID
    check_run_id: UUID | None
    requested_by_id: UUID
    status: ScenarioRunStatus
    trigger_source: str
    failure_reason: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime


class ScenarioRunDetailRead(ScenarioRunRead):
    step_results: list[StepResultRead]
    console_errors: list[ConsoleErrorRead]
    network_failures: list[NetworkFailureRead]
