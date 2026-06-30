from datetime import datetime
from enum import StrEnum
from typing import Final, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aim_api.schemas.check_run import (
    ArtifactRead,
    AvailabilityResultRead,
    CheckRunRead,
    LighthouseResultRead,
    RunComparisonRead,
    ScoreResultRead,
    SslResultRead,
)
from aim_api.schemas.scenario import (
    ConsoleErrorRead,
    NetworkFailureRead,
    ScenarioRunRead,
    StepResultRead,
)

AI_DIAGNOSIS_INPUT_SCHEMA_VERSION: Final = "2026-06-29.ai-diagnosis-input.v1"
AI_DIAGNOSIS_REPORT_SCHEMA_VERSION: Final = "2026-06-30.ai-diagnosis-report.v1"

DEFAULT_GENERATION_RULES: Final[tuple[str, ...]] = (
    "Use deterministic score_result as the authoritative score and deployment risk.",
    "Do not invent source-code locations, internal logs, or server-side causes.",
    "Distinguish confirmed observations, evidence-based inferences, and unknown causes.",
    "Every recommendation must reference provided evidence or explicitly mark the cause as "
    "unknown.",
    "A failed AI report generation must not change the CheckRun or ScenarioRun status.",
)


class AIDiagnosisBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AIDiagnosisEvidenceKind(StrEnum):
    CHECK_RUN = "check_run"
    AVAILABILITY_RESULT = "availability_result"
    SSL_RESULT = "ssl_result"
    LIGHTHOUSE_RESULT = "lighthouse_result"
    SCORE_RESULT = "score_result"
    RUN_COMPARISON = "run_comparison"
    SCENARIO_RUN = "scenario_run"
    STEP_RESULT = "step_result"
    CONSOLE_ERROR = "console_error"
    NETWORK_FAILURE = "network_failure"
    ARTIFACT = "artifact"


class AIDiagnosisSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    RISK = "risk"


class AIDiagnosisDeploymentRisk(StrEnum):
    STABLE = "STABLE"
    WARNING = "WARNING"
    RISK = "RISK"


class AIDiagnosisStatementType(StrEnum):
    CONFIRMED_OBSERVATION = "confirmed_observation"
    EVIDENCE_BASED_INFERENCE = "evidence_based_inference"
    UNKNOWN_CAUSE = "unknown_cause"


class AIDiagnosisRunContext(AIDiagnosisBaseModel):
    project_id: UUID
    check_run_id: UUID
    generated_at: datetime
    service_url: str | None = Field(default=None, max_length=2048)
    environment: str | None = Field(default=None, max_length=32)


class AIDiagnosisEvidenceItem(AIDiagnosisBaseModel):
    id: str = Field(min_length=1, max_length=120)
    kind: AIDiagnosisEvidenceKind
    source_id: UUID | None = None
    summary: str = Field(min_length=1, max_length=2000)
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class AIDiagnosisStatement(AIDiagnosisBaseModel):
    id: str = Field(min_length=1, max_length=120)
    statement_type: AIDiagnosisStatementType
    severity: AIDiagnosisSeverity
    category: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    unknown_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_evidence_and_unknown_reason(self) -> Self:
        if self.statement_type != AIDiagnosisStatementType.UNKNOWN_CAUSE and not self.evidence_ids:
            raise ValueError("Confirmed observations and inferences must reference evidence.")

        if (
            self.statement_type == AIDiagnosisStatementType.UNKNOWN_CAUSE
            and self.unknown_reason is None
        ):
            raise ValueError("Unknown-cause statements must explain why the cause is unknown.")

        return self


class AIDiagnosisScenarioEvidence(AIDiagnosisBaseModel):
    scenario_run: ScenarioRunRead
    step_results: list[StepResultRead] = Field(default_factory=list)
    console_errors: list[ConsoleErrorRead] = Field(default_factory=list)
    network_failures: list[NetworkFailureRead] = Field(default_factory=list)


class AIDiagnosisInput(AIDiagnosisBaseModel):
    schema_version: Literal["2026-06-29.ai-diagnosis-input.v1"] = AI_DIAGNOSIS_INPUT_SCHEMA_VERSION
    run_context: AIDiagnosisRunContext
    check_run: CheckRunRead
    availability_result: AvailabilityResultRead | None = None
    ssl_result: SslResultRead | None = None
    lighthouse_result: LighthouseResultRead | None = None
    score_result: ScoreResultRead | None = None
    comparison_result: RunComparisonRead | None = None
    artifacts: list[ArtifactRead] = Field(default_factory=list)
    scenario_evidence: list[AIDiagnosisScenarioEvidence] = Field(default_factory=list)
    evidence_items: list[AIDiagnosisEvidenceItem] = Field(default_factory=list)
    statements: list[AIDiagnosisStatement] = Field(default_factory=list)
    generation_rules: list[str] = Field(default_factory=lambda: list(DEFAULT_GENERATION_RULES))


class AIDiagnosisReportScore(AIDiagnosisBaseModel):
    overall_score: int = Field(ge=0, le=100)
    grade: Literal["A", "B", "C", "D", "F"]
    deployment_risk: AIDiagnosisDeploymentRisk
    gate_reason: str | None = Field(default=None, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class AIDiagnosisReportIssue(AIDiagnosisBaseModel):
    id: str = Field(min_length=1, max_length=120)
    priority: int = Field(ge=1, le=20)
    title: str = Field(min_length=1, max_length=200)
    statement_type: AIDiagnosisStatementType
    severity: AIDiagnosisSeverity
    category: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    expected_user_impact: str = Field(min_length=1, max_length=2000)
    recommended_next_action: str = Field(min_length=1, max_length=2000)
    unknown_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_evidence_and_unknown_reason(self) -> Self:
        if self.statement_type != AIDiagnosisStatementType.UNKNOWN_CAUSE and not self.evidence_ids:
            raise ValueError(
                "Report issues based on observations or inferences must reference evidence."
            )

        if (
            self.statement_type == AIDiagnosisStatementType.UNKNOWN_CAUSE
            and self.unknown_reason is None
        ):
            raise ValueError("Unknown-cause report issues must explain why the cause is unknown.")

        return self


class AIDiagnosisReportChange(AIDiagnosisBaseModel):
    id: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    metric_name: str | None = Field(default=None, max_length=120)
    previous_value: str | int | float | bool | None = None
    current_value: str | int | float | bool | None = None
    delta: str | int | float | bool | None = None


class AIDiagnosisReport(AIDiagnosisBaseModel):
    schema_version: Literal["2026-06-30.ai-diagnosis-report.v1"] = (
        AI_DIAGNOSIS_REPORT_SCHEMA_VERSION
    )
    input_schema_version: str = Field(default=AI_DIAGNOSIS_INPUT_SCHEMA_VERSION, max_length=80)
    project_id: UUID
    check_run_id: UUID
    generated_at: datetime
    summary: str = Field(min_length=1, max_length=2000)
    score: AIDiagnosisReportScore
    top_issues: list[AIDiagnosisReportIssue] = Field(default_factory=list, max_length=20)
    improved_areas: list[AIDiagnosisReportChange] = Field(default_factory=list, max_length=20)
    regressed_areas: list[AIDiagnosisReportChange] = Field(default_factory=list, max_length=20)
    generation_warnings: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_report_consistency(self) -> Self:
        priorities = [issue.priority for issue in self.top_issues]
        if len(priorities) != len(set(priorities)):
            raise ValueError("Top issue priorities must be unique.")

        if priorities != sorted(priorities):
            raise ValueError("Top issues must be ordered by priority.")

        if self.score.deployment_risk != AIDiagnosisDeploymentRisk.STABLE and not self.top_issues:
            raise ValueError("WARNING or RISK reports must include at least one top issue.")

        return self


class AIReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    check_run_id: UUID
    schema_version: str
    input_schema_version: str
    summary: str
    overall_score: int
    grade: str
    deployment_risk: str
    gate_reason: str | None
    report_json: dict[str, object]
    generated_at: datetime
    created_at: datetime
    updated_at: datetime
