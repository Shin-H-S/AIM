from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.ai_report import AIReport
from aim_api.schemas.ai_diagnosis import AIDiagnosisReport
from aim_api.services import ai_diagnosis_inputs, ai_diagnosis_reports


class AIReportNotFoundError(Exception):
    """Raised when an AI report does not exist for the requested check run."""


def record_ai_report(
    session: Session,
    *,
    report: AIDiagnosisReport,
) -> AIReport:
    ai_report = get_ai_report_or_none(session, check_run_id=report.check_run_id)
    if ai_report is None:
        ai_report = AIReport(check_run_id=report.check_run_id)
        session.add(ai_report)

    ai_report.schema_version = report.schema_version
    ai_report.input_schema_version = report.input_schema_version
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
) -> AIReport:
    diagnosis_input = ai_diagnosis_inputs.build_ai_diagnosis_input(
        session,
        check_run_id=check_run_id,
    )
    report = ai_diagnosis_reports.build_ai_diagnosis_report(
        diagnosis_input,
        generated_at=generated_at,
    )
    return record_ai_report(session, report=report)


def get_ai_report(session: Session, *, check_run_id: UUID) -> AIReport:
    ai_report = get_ai_report_or_none(session, check_run_id=check_run_id)
    if ai_report is None:
        raise AIReportNotFoundError

    return ai_report


def get_ai_report_or_none(session: Session, *, check_run_id: UUID) -> AIReport | None:
    return session.scalar(select(AIReport).where(AIReport.check_run_id == check_run_id))
