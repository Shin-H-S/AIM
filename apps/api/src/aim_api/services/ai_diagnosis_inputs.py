from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.check_run import CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import (
    Artifact,
    AvailabilityResult,
    LighthouseResult,
    RunComparison,
    ScoreResult,
    SslResult,
)
from aim_api.models.scenario import ScenarioRunStatus, StepResultStatus
from aim_api.schemas.ai_diagnosis import (
    AIDiagnosisEvidenceItem,
    AIDiagnosisEvidenceKind,
    AIDiagnosisInput,
    AIDiagnosisRunContext,
    AIDiagnosisScenarioEvidence,
    AIDiagnosisSeverity,
    AIDiagnosisStatement,
    AIDiagnosisStatementType,
)
from aim_api.schemas.check_run import (
    ArtifactRead,
    AvailabilityResultRead,
    CheckRunRead,
    LighthouseAuditRead,
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
from aim_api.services import artifacts as artifact_service
from aim_api.services import check_runs as check_run_service
from aim_api.services import run_comparisons as run_comparison_service
from aim_api.services import scanner_results as scanner_result_service
from aim_api.services import scenarios as scenario_service
from aim_api.services import score_results as score_result_service


def build_ai_diagnosis_input(session: Session, *, check_run_id: UUID) -> AIDiagnosisInput:
    check_run = check_run_service.get_check_run_by_id(session, check_run_id=check_run_id)
    project = session.get(Project, check_run.project_id)
    if project is None:
        raise check_run_service.CheckRunNotFoundError

    availability_result = scanner_result_service.get_availability_result(
        session,
        check_run_id=check_run.id,
    )
    ssl_result = scanner_result_service.get_ssl_result(
        session,
        check_run_id=check_run.id,
    )
    lighthouse_result = scanner_result_service.get_lighthouse_result(
        session,
        check_run_id=check_run.id,
    )
    score_result = score_result_service.get_score_result(
        session,
        check_run_id=check_run.id,
    )
    comparison_result = run_comparison_service.get_run_comparison(
        session,
        check_run_id=check_run.id,
    )
    scenario_runs = scenario_service.list_scenario_runs_for_check_run(
        session,
        check_run_id=check_run.id,
    )
    scenario_evidence = [
        AIDiagnosisScenarioEvidence(
            scenario_run=ScenarioRunRead.model_validate(scenario_run),
            step_results=[
                StepResultRead.model_validate(step_result)
                for step_result in scenario_service.list_step_results(
                    session,
                    scenario_run_id=scenario_run.id,
                )
            ],
            console_errors=[
                ConsoleErrorRead.model_validate(console_error)
                for console_error in scenario_service.list_console_errors(
                    session,
                    scenario_run_id=scenario_run.id,
                )
            ],
            network_failures=[
                NetworkFailureRead.model_validate(network_failure)
                for network_failure in scenario_service.list_network_failures(
                    session,
                    scenario_run_id=scenario_run.id,
                )
            ],
        )
        for scenario_run in scenario_runs
    ]
    artifacts = artifact_service.list_artifacts(session, check_run_id=check_run.id)
    artifacts.extend(
        list_scenario_artifacts(
            session,
            scenario_run_ids=[scenario_run.id for scenario_run in scenario_runs],
        )
    )

    evidence_items = build_evidence_items(
        check_run=CheckRunRead.model_validate(check_run),
        availability_result=AvailabilityResultRead.model_validate(availability_result)
        if availability_result is not None
        else None,
        ssl_result=SslResultRead.model_validate(ssl_result) if ssl_result is not None else None,
        lighthouse_result=LighthouseResultRead.model_validate(lighthouse_result)
        if lighthouse_result is not None
        else None,
        score_result=ScoreResultRead.model_validate(score_result)
        if score_result is not None
        else None,
        comparison_result=RunComparisonRead.model_validate(comparison_result)
        if comparison_result is not None
        else None,
        scenario_evidence=scenario_evidence,
        artifacts=[ArtifactRead.model_validate(artifact) for artifact in artifacts],
    )
    statements = build_statements(
        project=project,
        check_run=CheckRunRead.model_validate(check_run),
        availability_result=availability_result,
        ssl_result=ssl_result,
        lighthouse_result=lighthouse_result,
        score_result=score_result,
        comparison_result=comparison_result,
        scenario_evidence=scenario_evidence,
    )

    return AIDiagnosisInput(
        run_context=AIDiagnosisRunContext(
            project_id=project.id,
            check_run_id=check_run.id,
            generated_at=datetime.now(UTC),
            service_url=project.service_url,
            environment=project.environment,
        ),
        check_run=CheckRunRead.model_validate(check_run),
        availability_result=AvailabilityResultRead.model_validate(availability_result)
        if availability_result is not None
        else None,
        ssl_result=SslResultRead.model_validate(ssl_result) if ssl_result is not None else None,
        lighthouse_result=LighthouseResultRead.model_validate(lighthouse_result)
        if lighthouse_result is not None
        else None,
        score_result=ScoreResultRead.model_validate(score_result)
        if score_result is not None
        else None,
        comparison_result=RunComparisonRead.model_validate(comparison_result)
        if comparison_result is not None
        else None,
        artifacts=[ArtifactRead.model_validate(artifact) for artifact in artifacts],
        scenario_evidence=scenario_evidence,
        evidence_items=evidence_items,
        statements=statements,
    )


def list_scenario_artifacts(
    session: Session,
    *,
    scenario_run_ids: list[UUID],
) -> list[Artifact]:
    if not scenario_run_ids:
        return []

    return list(
        session.scalars(
            select(Artifact)
            .where(Artifact.scenario_run_id.in_(scenario_run_ids))
            .order_by(Artifact.created_at.asc(), Artifact.id.asc())
        )
    )


def build_evidence_items(
    *,
    check_run: CheckRunRead,
    availability_result: AvailabilityResultRead | None,
    ssl_result: SslResultRead | None,
    lighthouse_result: LighthouseResultRead | None,
    score_result: ScoreResultRead | None,
    comparison_result: RunComparisonRead | None,
    scenario_evidence: list[AIDiagnosisScenarioEvidence],
    artifacts: list[ArtifactRead],
) -> list[AIDiagnosisEvidenceItem]:
    evidence_items = [
        AIDiagnosisEvidenceItem(
            id="check-run-status",
            kind=AIDiagnosisEvidenceKind.CHECK_RUN,
            source_id=check_run.id,
            summary=f"CheckRun status is {check_run.status}.",
            details={
                "status": check_run.status,
                "failure_reason": check_run.failure_reason,
                "trigger_source": check_run.trigger_source,
            },
        )
    ]

    if availability_result is not None:
        evidence_items.append(
            AIDiagnosisEvidenceItem(
                id="availability-result",
                kind=AIDiagnosisEvidenceKind.AVAILABILITY_RESULT,
                summary=(
                    "Availability check reported service as "
                    f"{'available' if availability_result.is_available else 'unavailable'}."
                ),
                details={
                    "status_code": availability_result.status_code,
                    "response_time_ms": availability_result.response_time_ms,
                    "timed_out": availability_result.timed_out,
                    "failure_reason": availability_result.failure_reason,
                },
            )
        )

    if ssl_result is not None:
        evidence_items.append(
            AIDiagnosisEvidenceItem(
                id="ssl-result",
                kind=AIDiagnosisEvidenceKind.SSL_RESULT,
                summary="SSL inspection result was collected.",
                details={
                    "is_applicable": ssl_result.is_applicable,
                    "is_valid": ssl_result.is_valid,
                    "days_until_expiration": ssl_result.days_until_expiration,
                    "failure_reason": ssl_result.failure_reason,
                },
            )
        )

    if lighthouse_result is not None:
        evidence_items.append(
            AIDiagnosisEvidenceItem(
                id="lighthouse-result",
                kind=AIDiagnosisEvidenceKind.LIGHTHOUSE_RESULT,
                summary="Lighthouse mobile scan result was collected.",
                details={
                    "is_successful": lighthouse_result.is_successful,
                    "performance_score": lighthouse_result.performance_score,
                    "accessibility_score": lighthouse_result.accessibility_score,
                    "seo_score": lighthouse_result.seo_score,
                    "best_practices_score": lighthouse_result.best_practices_score,
                    "failure_reason": lighthouse_result.failure_reason,
                },
            )
        )

        for audit in lighthouse_result.top_audits or []:
            evidence_items.append(build_lighthouse_audit_evidence(audit))

    if score_result is not None:
        evidence_items.append(
            AIDiagnosisEvidenceItem(
                id="score-result",
                kind=AIDiagnosisEvidenceKind.SCORE_RESULT,
                summary=(
                    f"Deterministic score is {score_result.overall_score}/100 "
                    f"with deployment risk {score_result.deployment_risk}."
                ),
                details={
                    "overall_score": score_result.overall_score,
                    "grade": score_result.grade,
                    "deployment_risk": score_result.deployment_risk,
                    "gate_reason": score_result.gate_reason,
                    "scoring_version": score_result.scoring_version,
                },
            )
        )

    if comparison_result is not None:
        evidence_items.append(
            AIDiagnosisEvidenceItem(
                id="run-comparison",
                kind=AIDiagnosisEvidenceKind.RUN_COMPARISON,
                source_id=comparison_result.baseline_check_run_id,
                summary=comparison_result.summary,
                details={
                    "overall_score_delta": comparison_result.overall_score_delta,
                    "performance_score_delta": comparison_result.performance_score_delta,
                    "response_time_delta_ms": comparison_result.response_time_delta_ms,
                    "deployment_risk_changed": comparison_result.deployment_risk_changed,
                },
            )
        )

    for scenario in scenario_evidence:
        scenario_run = scenario.scenario_run
        evidence_items.append(
            AIDiagnosisEvidenceItem(
                id=f"scenario-run-{scenario_run.id}",
                kind=AIDiagnosisEvidenceKind.SCENARIO_RUN,
                source_id=scenario_run.id,
                summary=f"ScenarioRun status is {scenario_run.status}.",
                details={
                    "status": scenario_run.status,
                    "failure_reason": scenario_run.failure_reason,
                    "duration_ms": scenario_run.duration_ms,
                    "trigger_source": scenario_run.trigger_source,
                },
            )
        )
        for step_result in scenario.step_results:
            evidence_items.append(
                AIDiagnosisEvidenceItem(
                    id=f"step-result-{step_result.id}",
                    kind=AIDiagnosisEvidenceKind.STEP_RESULT,
                    source_id=step_result.id,
                    summary=(
                        f"Step #{step_result.step_order} {step_result.action} "
                        f"finished with {step_result.status}."
                    ),
                    details={
                        "step_order": step_result.step_order,
                        "action": step_result.action,
                        "status": step_result.status,
                        "duration_ms": step_result.duration_ms,
                        "error_message": step_result.error_message,
                    },
                )
            )
        for console_error in scenario.console_errors:
            evidence_items.append(
                AIDiagnosisEvidenceItem(
                    id=f"console-error-{console_error.id}",
                    kind=AIDiagnosisEvidenceKind.CONSOLE_ERROR,
                    source_id=console_error.id,
                    summary=console_error.message,
                    details={
                        "level": console_error.level,
                        "source_url": console_error.source_url,
                        "line_number": console_error.line_number,
                        "column_number": console_error.column_number,
                    },
                )
            )
        for network_failure in scenario.network_failures:
            evidence_items.append(
                AIDiagnosisEvidenceItem(
                    id=f"network-failure-{network_failure.id}",
                    kind=AIDiagnosisEvidenceKind.NETWORK_FAILURE,
                    source_id=network_failure.id,
                    summary=network_failure.request_url,
                    details={
                        "method": network_failure.method,
                        "resource_type": network_failure.resource_type,
                        "failure_text": network_failure.failure_text,
                    },
                )
            )

    for artifact in artifacts:
        evidence_items.append(
            AIDiagnosisEvidenceItem(
                id=f"artifact-{artifact.id}",
                kind=AIDiagnosisEvidenceKind.ARTIFACT,
                source_id=artifact.id,
                summary=f"{artifact.artifact_type} artifact is available.",
                details={
                    "storage_backend": artifact.storage_backend,
                    "content_type": artifact.content_type,
                    "size_bytes": artifact.size_bytes,
                },
            )
        )

    return evidence_items


def build_statements(
    *,
    project: Project,
    check_run: CheckRunRead,
    availability_result: AvailabilityResult | None,
    ssl_result: SslResult | None,
    lighthouse_result: LighthouseResult | None,
    score_result: ScoreResult | None,
    comparison_result: RunComparison | None,
    scenario_evidence: list[AIDiagnosisScenarioEvidence],
) -> list[AIDiagnosisStatement]:
    statements: list[AIDiagnosisStatement] = []

    if check_run.status == CheckRunStatus.FAILED:
        statements.append(
            AIDiagnosisStatement(
                id="check-run-failed",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.RISK,
                category="check_run",
                summary="검사가 FAILED 상태로 끝났습니다.",
                evidence_ids=["check-run-status"],
            )
        )
    elif check_run.status == CheckRunStatus.CANCELLED:
        statements.append(
            AIDiagnosisStatement(
                id="check-run-cancelled",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.WARNING,
                category="check_run",
                summary="검사가 완료 전에 취소되었습니다.",
                evidence_ids=["check-run-status"],
            )
        )

    if score_result is not None:
        deployment_risk = score_result.deployment_risk
        statements.append(
            AIDiagnosisStatement(
                id="score-result-deployment-risk",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=deployment_risk_to_severity(deployment_risk),
                category="deployment_risk",
                summary=(
                    f"결정론 스코어링이 이 검사를 {deployment_risk}"
                    f"(등급 {score_result.grade})로 판정했습니다."
                ),
                evidence_ids=["score-result"],
            )
        )

    if availability_result is not None:
        if not availability_result.is_available:
            statements.append(
                AIDiagnosisStatement(
                    id="availability-unavailable",
                    statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                    severity=AIDiagnosisSeverity.RISK,
                    category="availability",
                    summary="가용성 검사에서 서비스에 접속할 수 없었습니다.",
                    evidence_ids=["availability-result"],
                )
            )
        elif (
            availability_result.response_time_ms is not None
            and availability_result.response_time_ms > project.response_time_threshold_ms
        ):
            statements.append(
                AIDiagnosisStatement(
                    id="availability-response-time-threshold",
                    statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                    severity=AIDiagnosisSeverity.WARNING,
                    category="availability",
                    summary="응답 시간이 프로젝트에 설정한 임계값을 초과했습니다.",
                    evidence_ids=["availability-result"],
                )
            )

    if ssl_result is not None and ssl_result.is_applicable and ssl_result.is_valid is False:
        statements.append(
            AIDiagnosisStatement(
                id="ssl-invalid",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.RISK,
                category="ssl",
                summary="SSL 검사에서 유효하지 않은 인증서가 확인되었습니다.",
                evidence_ids=["ssl-result"],
            )
        )

    if lighthouse_result is not None and not lighthouse_result.is_successful:
        statements.append(
            AIDiagnosisStatement(
                id="lighthouse-failed",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.WARNING,
                category="web_quality",
                summary="Lighthouse 스캔이 정상적으로 완료되지 않았습니다.",
                evidence_ids=["lighthouse-result"],
            )
        )

    if (
        lighthouse_result is not None
        and lighthouse_result.is_successful
        and lighthouse_result.top_audits
        and has_lighthouse_score_below_threshold(
            lighthouse_result,
            threshold=project.quality_score_threshold,
        )
    ):
        statements.append(build_lighthouse_opportunity_statement(lighthouse_result))

    if (
        comparison_result is not None
        and comparison_result.overall_score_delta is not None
        and comparison_result.overall_score_delta < 0
    ):
        statements.append(
            AIDiagnosisStatement(
                id="comparison-overall-score-regression",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.WARNING,
                category="regression",
                summary=comparison_result.summary,
                evidence_ids=["run-comparison"],
            )
        )

    for scenario in scenario_evidence:
        scenario_run = scenario.scenario_run
        if scenario_run.status == ScenarioRunStatus.FAILED:
            statements.append(
                AIDiagnosisStatement(
                    id=f"scenario-run-failed-{scenario_run.id}",
                    statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                    severity=AIDiagnosisSeverity.RISK,
                    category="functional_stability",
                    summary="연결된 시나리오 실행이 실패했습니다.",
                    evidence_ids=[f"scenario-run-{scenario_run.id}"],
                )
            )
        if scenario_run.status in {ScenarioRunStatus.QUEUED, ScenarioRunStatus.RUNNING}:
            statements.append(
                AIDiagnosisStatement(
                    id=f"scenario-run-pending-{scenario_run.id}",
                    statement_type=AIDiagnosisStatementType.UNKNOWN_CAUSE,
                    severity=AIDiagnosisSeverity.WARNING,
                    category="functional_stability",
                    summary="연결된 시나리오 실행이 아직 종결되지 않았습니다.",
                    evidence_ids=[f"scenario-run-{scenario_run.id}"],
                    unknown_reason="브라우저 워커가 아직 최종 결과를 내지 않았습니다.",
                )
            )
        failed_step_evidence_ids = [
            f"step-result-{step_result.id}"
            for step_result in scenario.step_results
            if step_result.status == StepResultStatus.FAILED
        ]
        if failed_step_evidence_ids:
            statements.append(
                AIDiagnosisStatement(
                    id=f"failed-steps-{scenario_run.id}",
                    statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                    severity=AIDiagnosisSeverity.RISK,
                    category="functional_stability",
                    summary="하나 이상의 시나리오 스텝이 실패했습니다.",
                    evidence_ids=failed_step_evidence_ids[:20],
                )
            )
        if scenario.console_errors:
            statements.append(
                AIDiagnosisStatement(
                    id=f"console-errors-{scenario_run.id}",
                    statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                    severity=AIDiagnosisSeverity.WARNING,
                    category="browser_console",
                    summary="시나리오 실행 중 브라우저 콘솔 오류가 수집되었습니다.",
                    evidence_ids=[
                        f"console-error-{console_error.id}"
                        for console_error in scenario.console_errors[:20]
                    ],
                )
            )
        if scenario.network_failures:
            statements.append(
                AIDiagnosisStatement(
                    id=f"network-failures-{scenario_run.id}",
                    statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                    severity=AIDiagnosisSeverity.WARNING,
                    category="network",
                    summary="시나리오 실행 중 실패한 네트워크 요청이 수집되었습니다.",
                    evidence_ids=[
                        f"network-failure-{network_failure.id}"
                        for network_failure in scenario.network_failures[:20]
                    ],
                )
            )

    if not statements:
        statements.append(
            AIDiagnosisStatement(
                id="no-risk-evidence",
                statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
                severity=AIDiagnosisSeverity.INFO,
                category="summary",
                summary="아직 수집된 결정론 위험 근거가 없습니다.",
                evidence_ids=["check-run-status"],
            )
        )

    return statements


def build_lighthouse_audit_evidence(audit: LighthouseAuditRead) -> AIDiagnosisEvidenceItem:
    summary = f"Lighthouse improvement opportunity: {audit.title}"
    if audit.display_value:
        summary = f"{summary} ({audit.display_value})"

    return AIDiagnosisEvidenceItem(
        id=f"lighthouse-audit-{audit.id}"[:120],
        kind=AIDiagnosisEvidenceKind.LIGHTHOUSE_RESULT,
        summary=summary[:2000],
        details={
            "audit_id": audit.id,
            "category": audit.category,
            "title": audit.title,
            "display_value": audit.display_value,
            "score": audit.score,
            "savings_ms": audit.savings_ms,
            "savings_bytes": audit.savings_bytes,
        },
    )


def has_lighthouse_score_below_threshold(
    lighthouse_result: LighthouseResult,
    *,
    threshold: int,
) -> bool:
    scores = (
        lighthouse_result.performance_score,
        lighthouse_result.accessibility_score,
        lighthouse_result.seo_score,
        lighthouse_result.best_practices_score,
    )
    return any(score is not None and score < threshold for score in scores)


def build_lighthouse_opportunity_statement(
    lighthouse_result: LighthouseResult,
) -> AIDiagnosisStatement:
    top_audits = [audit for audit in lighthouse_result.top_audits or [] if isinstance(audit, dict)]
    titles = [str(audit["title"]) for audit in top_audits[:3] if audit.get("title")]
    evidence_ids = ["lighthouse-result"]
    evidence_ids.extend(
        f"lighthouse-audit-{audit['id']}"[:120] for audit in top_audits if audit.get("id")
    )

    summary = "Lighthouse가 이 페이지에서 구체적인 개선 기회를 발견했습니다."
    if titles:
        summary = f"Lighthouse 개선 기회: {', '.join(titles)}."

    return AIDiagnosisStatement(
        id="lighthouse-improvement-opportunities",
        statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
        severity=AIDiagnosisSeverity.WARNING,
        category="web_quality",
        summary=summary[:2000],
        evidence_ids=evidence_ids[:20],
    )


def deployment_risk_to_severity(deployment_risk: str) -> AIDiagnosisSeverity:
    if deployment_risk == "RISK":
        return AIDiagnosisSeverity.RISK
    if deployment_risk == "WARNING":
        return AIDiagnosisSeverity.WARNING
    return AIDiagnosisSeverity.INFO
