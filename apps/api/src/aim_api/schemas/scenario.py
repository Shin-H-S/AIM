from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TestStepAction(StrEnum):
    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    WAIT = "wait"
    ASSERT_ELEMENT_EXISTS = "assert_element_exists"
    ASSERT_TEXT_EXISTS = "assert_text_exists"
    ASSERT_URL = "assert_url"
    TAKE_SCREENSHOT = "take_screenshot"


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
