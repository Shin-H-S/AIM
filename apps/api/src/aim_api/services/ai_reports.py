from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.ai_report import AIReport
from aim_api.models.check_run import CheckRun
from aim_api.schemas.ai_diagnosis import AIDiagnosisDeploymentRisk, AIDiagnosisReport
from aim_api.services import ai_diagnosis_inputs, ai_diagnosis_reports, ai_report_narratives
from aim_api.services.ai_report_narratives import DETERMINISTIC_GENERATOR, NarrativeGenerator

SCHEDULED_TRIGGER_SOURCE = "scheduled"


class AIReportNotFoundError(Exception):
    """Raised when an AI report does not exist for the requested check run."""


def record_ai_report(
    session: Session,
    *,
    report: AIDiagnosisReport,
    generator: str = DETERMINISTIC_GENERATOR,
) -> AIReport:
    ai_report = get_ai_report_or_none(session, check_run_id=report.check_run_id)
    if ai_report is None:
        ai_report = AIReport(check_run_id=report.check_run_id)
        session.add(ai_report)

    ai_report.schema_version = report.schema_version
    ai_report.input_schema_version = report.input_schema_version
    ai_report.generator = generator
    ai_report.summary = report.summary
    ai_report.overall_score = report.score.overall_score
    ai_report.grade = report.score.grade
    ai_report.deployment_risk = report.score.deployment_risk.value
    ai_report.gate_reason = report.score.gate_reason
    ai_report.report_json = cast(dict[str, object], report.model_dump(mode="json"))
    ai_report.generated_at = report.generated_at

    session.commit()
    session.refresh(ai_report)
    return ai_report


def generate_and_record_ai_report(
    session: Session,
    *,
    check_run_id: UUID,
    generated_at: datetime | None = None,
    narrative_generator: NarrativeGenerator | None = None,
) -> AIReport:
    diagnosis_input = ai_diagnosis_inputs.build_ai_diagnosis_input(
        session,
        check_run_id=check_run_id,
    )
    report = ai_diagnosis_reports.build_ai_diagnosis_report(
        diagnosis_input,
        generated_at=generated_at,
    )
    if should_skip_llm_narrative(session, report=report):
        return record_ai_report(session, report=report)

    enhancement = ai_report_narratives.enhance_report_narrative(
        diagnosis_input,
        report,
        narrative_generator=narrative_generator,
    )
    return record_ai_report(
        session,
        report=enhancement.report,
        generator=enhancement.generator,
    )


def should_skip_llm_narrative(session: Session, *, report: AIDiagnosisReport) -> bool:
    """이상 신호가 없는 정기 검사는 LLM 서술 없이 결정론 리포트만 기록한다.

    정기 검사 대부분은 "변화 없음"이라 LLM 서술의 정보 가치가 낮고 호출 비용만 남는다.
    배포·수동 검사, 게이트에 걸렸거나 이슈가 있는 검사는 지금처럼 LLM 서술을 받는다.
    """
    if report.score.deployment_risk != AIDiagnosisDeploymentRisk.STABLE or report.top_issues:
        return False

    check_run = session.get(CheckRun, report.check_run_id)
    return check_run is not None and check_run.trigger_source == SCHEDULED_TRIGGER_SOURCE


def get_ai_report(session: Session, *, check_run_id: UUID) -> AIReport:
    ai_report = get_ai_report_or_none(session, check_run_id=check_run_id)
    if ai_report is None:
        raise AIReportNotFoundError

    return ai_report


def get_ai_report_or_none(session: Session, *, check_run_id: UUID) -> AIReport | None:
    return session.scalar(select(AIReport).where(AIReport.check_run_id == check_run_id))
