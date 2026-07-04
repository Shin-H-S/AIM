import json
import logging
from dataclasses import dataclass
from typing import Protocol

from anthropic import Anthropic
from pydantic import BaseModel, ConfigDict

from aim_api.config import Settings, get_settings
from aim_api.schemas.ai_diagnosis import AIDiagnosisInput, AIDiagnosisReport

DETERMINISTIC_GENERATOR = "deterministic"
NARRATIVE_TEXT_MAX_LENGTH = 2000

NARRATIVE_SYSTEM_PROMPT = (
    "You write the narrative text for AIM's web-service diagnosis reports.\n"
    "\n"
    "You receive one JSON payload with two parts:\n"
    '- "diagnosis_input": structured scan evidence collected from the target service.\n'
    '- "deterministic_report": the authoritative report produced by deterministic '
    "application logic.\n"
    "\n"
    "The deterministic report's scores, grade, deployment risk, issue list, severities, "
    "statement types, and evidence references are final and must not change. Your only "
    "job is to write clearer narrative text:\n"
    '- "summary": a short plain-language summary of this run for a developer deciding '
    "whether the deployment is safe. Mention the deployment risk and the most important "
    "issues.\n"
    '- "issue_narratives": one entry per issue id in deterministic_report.top_issues, '
    "with expected_user_impact (how the issue affects real users) and "
    "recommended_next_action (the most useful next step for the developer).\n"
    "\n"
    "Hard rules:\n"
    "- Base every statement only on the provided evidence. Never invent source-code "
    "locations, server internals, logs, metrics, or checks that are not in the payload.\n"
    "- Respect each issue's statement_type: describe confirmed_observation as fact, "
    'evidence_based_inference as likely ("likely", "appears"), and unknown_cause as '
    "unknown while noting what evidence is missing.\n"
    "- Use the issue ids exactly as given. Do not add or remove issues.\n"
    "- Keep every text field under 1500 characters. Write in clear English."
)

logger = logging.getLogger(__name__)


class NarrativeGenerationError(Exception):
    """Raised when the LLM response does not contain a usable narrative."""


class AIReportIssueNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    expected_user_impact: str
    recommended_next_action: str


class AIReportNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    issue_narratives: list[AIReportIssueNarrative]


class NarrativeGenerator(Protocol):
    @property
    def generator_name(self) -> str:
        """Identifier recorded on the stored AI report (e.g. the model id)."""
        ...

    def generate(
        self,
        *,
        diagnosis_input: AIDiagnosisInput,
        report: AIDiagnosisReport,
    ) -> AIReportNarrative:
        """Produce narrative text for the given deterministic report."""
        ...


def build_narrative_request_payload(
    *,
    diagnosis_input: AIDiagnosisInput,
    report: AIDiagnosisReport,
) -> str:
    payload = {
        "diagnosis_input": diagnosis_input.model_dump(mode="json"),
        "deterministic_report": report.model_dump(mode="json"),
    }
    return json.dumps(payload, ensure_ascii=False)


class AnthropicNarrativeGenerator:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        max_tokens: int,
    ) -> None:
        self.generator_name = model
        self.model = model
        self.max_tokens = max_tokens
        self.client = Anthropic(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    def generate(
        self,
        *,
        diagnosis_input: AIDiagnosisInput,
        report: AIDiagnosisReport,
    ) -> AIReportNarrative:
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=self.max_tokens,
            thinking={"type": "adaptive"},
            system=NARRATIVE_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": build_narrative_request_payload(
                        diagnosis_input=diagnosis_input,
                        report=report,
                    ),
                }
            ],
            output_format=AIReportNarrative,
        )
        narrative = response.parsed_output
        if narrative is None:
            raise NarrativeGenerationError("LLM response did not include a parsed narrative.")

        return narrative


def build_anthropic_narrative_generator(
    settings: Settings | None = None,
) -> AnthropicNarrativeGenerator | None:
    runtime_settings = settings or get_settings()
    if not runtime_settings.anthropic_api_key:
        return None

    return AnthropicNarrativeGenerator(
        api_key=runtime_settings.anthropic_api_key,
        model=runtime_settings.ai_report_model,
        timeout_seconds=runtime_settings.ai_report_llm_timeout_seconds,
        max_retries=runtime_settings.ai_report_llm_max_retries,
        max_tokens=runtime_settings.ai_report_llm_max_tokens,
    )


def clip_narrative_text(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned:
        return None

    return cleaned[:NARRATIVE_TEXT_MAX_LENGTH]


def apply_narrative_to_report(
    report: AIDiagnosisReport,
    narrative: AIReportNarrative,
) -> AIDiagnosisReport:
    """Merge LLM narrative text into the deterministic report.

    Only the report summary and per-issue impact/action texts are replaced. Scores,
    risk, issue structure, and evidence references stay authoritative; narrative
    entries that do not match an existing issue id are ignored.
    """
    narratives_by_issue_id = {item.issue_id: item for item in narrative.issue_narratives}
    updated_issues = []
    for issue in report.top_issues:
        issue_narrative = narratives_by_issue_id.get(issue.id)
        if issue_narrative is None:
            updated_issues.append(issue)
            continue

        updated_issues.append(
            issue.model_copy(
                update={
                    "expected_user_impact": (
                        clip_narrative_text(issue_narrative.expected_user_impact)
                        or issue.expected_user_impact
                    ),
                    "recommended_next_action": (
                        clip_narrative_text(issue_narrative.recommended_next_action)
                        or issue.recommended_next_action
                    ),
                }
            )
        )

    updated_report = report.model_copy(
        update={
            "summary": clip_narrative_text(narrative.summary) or report.summary,
            "top_issues": updated_issues,
        }
    )
    return AIDiagnosisReport.model_validate(updated_report.model_dump())


@dataclass(frozen=True)
class NarrativeEnhancementResult:
    report: AIDiagnosisReport
    generator: str


def enhance_report_narrative(
    diagnosis_input: AIDiagnosisInput,
    report: AIDiagnosisReport,
    *,
    narrative_generator: NarrativeGenerator | None = None,
) -> NarrativeEnhancementResult:
    """Enhance the deterministic report with LLM narrative text when configured.

    Any failure falls back to the unchanged deterministic report so that AI report
    generation never blocks on the LLM.
    """
    generator = narrative_generator or build_anthropic_narrative_generator()
    if generator is None:
        return NarrativeEnhancementResult(report=report, generator=DETERMINISTIC_GENERATOR)

    try:
        narrative = generator.generate(diagnosis_input=diagnosis_input, report=report)
        enhanced_report = apply_narrative_to_report(report, narrative)
    except Exception:
        logger.exception(
            "Failed to apply LLM narrative to AI report; keeping deterministic narrative.",
            extra={"check_run_id": str(report.check_run_id)},
        )
        return NarrativeEnhancementResult(report=report, generator=DETERMINISTIC_GENERATOR)

    return NarrativeEnhancementResult(report=enhanced_report, generator=generator.generator_name)
