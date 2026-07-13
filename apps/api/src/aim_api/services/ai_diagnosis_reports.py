from datetime import UTC, datetime
from typing import Final, Literal, cast

from aim_api.schemas.ai_diagnosis import (
    AIDiagnosisDeploymentRisk,
    AIDiagnosisEvidenceKind,
    AIDiagnosisInput,
    AIDiagnosisReport,
    AIDiagnosisReportChange,
    AIDiagnosisReportIssue,
    AIDiagnosisReportScore,
    AIDiagnosisSeverity,
    AIDiagnosisStatement,
    AIDiagnosisStatementType,
)
from aim_api.schemas.check_run import ScoreResultRead

ReportGrade = Literal["A", "B", "C", "D", "F"]

SEVERITY_PRIORITY: Final[dict[AIDiagnosisSeverity, int]] = {
    AIDiagnosisSeverity.RISK: 0,
    AIDiagnosisSeverity.WARNING: 1,
    AIDiagnosisSeverity.INFO: 2,
}

ISSUE_IMPACT_BY_CATEGORY: Final[dict[str, str]] = {
    "availability": "사용자가 서비스에 접속하지 못하거나 접속이 불안정할 수 있습니다.",
    "browser_console": "테스트한 브라우저 흐름에서 사용자가 클라이언트 오류를 겪을 수 있습니다.",
    "check_run": "검사가 정상적으로 끝나지 않아 릴리스 신뢰도가 낮아집니다.",
    "deployment_risk": "결정론 스코어링 기준으로 이번 배포는 위험할 수 있습니다.",
    "functional_stability": "핵심 브라우저 흐름에서 사용자가 막힐 수 있습니다.",
    "network": "브라우저 요청이 완료되지 않아 테스트한 흐름이 실패할 수 있습니다.",
    "regression": "최신 검사가 기준보다 나빠져 검토가 필요합니다.",
    "ssl": "사용자에게 브라우저 보안 경고가 표시되거나 보안 연결이 실패할 수 있습니다.",
    "unknown_cause": "드러난 증상은 확인됐지만 근본 원인은 확정되지 않았습니다.",
    "web_quality": "로딩 품질이 저하되거나 품질 검사가 불완전할 수 있습니다.",
}

ISSUE_ACTION_BY_CATEGORY: Final[dict[str, str]] = {
    "availability": "가용성 근거와 최근 배포, 외부 의존성 상태를 확인하세요.",
    "browser_console": "수집된 콘솔 오류를 확인하고 해당 브라우저 흐름을 로컬에서 재현해 보세요.",
    "check_run": "검사 실패 원인을 조사하고 수정 후 검사를 다시 실행하세요.",
    "deployment_risk": "결정론 게이트 사유를 해소하기 전에는 이 배포를 안전하다고 판단하지 마세요.",
    "functional_stability": "시나리오를 다시 실행하고 실패한 스텝 근거부터 확인하세요.",
    "network": "실패한 브라우저 요청을 확인하고 관련 엔드포인트 동작을 점검하세요.",
    "regression": "이번 검사를 기준과 비교해 회귀를 수용할지 판단하세요.",
    "ssl": "인증서 유효성과 만료일, HTTPS 설정을 점검하세요.",
    "unknown_cause": "같은 시간대의 서버 로그나 텔레메트리를 확인해 근거와 대조하세요.",
    "web_quality": "Lighthouse 산출물을 확인하고 영향이 큰 진단부터 수정하세요.",
}


class AIDiagnosisReportGenerationError(Exception):
    """Raised when a report cannot be generated without inventing evidence."""


def build_ai_diagnosis_report(
    diagnosis_input: AIDiagnosisInput,
    *,
    generated_at: datetime | None = None,
) -> AIDiagnosisReport:
    report_score = build_report_score(diagnosis_input)
    top_issues = build_top_issues(diagnosis_input)
    generation_warnings = build_generation_warnings(diagnosis_input)

    if report_score.deployment_risk != AIDiagnosisDeploymentRisk.STABLE and not top_issues:
        top_issues = [build_score_based_issue(report_score)]
        generation_warnings.append("위험/경고 서술이 없어 점수 근거로 이슈를 구성했습니다.")

    improved_areas, regressed_areas = build_report_changes(diagnosis_input)

    return AIDiagnosisReport(
        input_schema_version=diagnosis_input.schema_version,
        project_id=diagnosis_input.run_context.project_id,
        check_run_id=diagnosis_input.run_context.check_run_id,
        generated_at=generated_at or datetime.now(UTC),
        summary=build_report_summary(report_score, top_issues),
        score=report_score,
        top_issues=top_issues,
        improved_areas=improved_areas,
        regressed_areas=regressed_areas,
        generation_warnings=generation_warnings,
    )


def build_report_score(diagnosis_input: AIDiagnosisInput) -> AIDiagnosisReportScore:
    score_result = diagnosis_input.score_result
    if score_result is None:
        raise AIDiagnosisReportGenerationError(
            "score_result is required to generate an AI diagnosis report."
        )

    evidence_ids = find_evidence_ids(
        diagnosis_input,
        kind=AIDiagnosisEvidenceKind.SCORE_RESULT,
    )
    if not evidence_ids:
        raise AIDiagnosisReportGenerationError(
            "score_result evidence is required to generate an AI diagnosis report."
        )

    return AIDiagnosisReportScore(
        overall_score=score_result.overall_score,
        grade=normalize_grade(score_result.grade),
        deployment_risk=normalize_deployment_risk(score_result),
        gate_reason=score_result.gate_reason,
        evidence_ids=evidence_ids,
    )


def build_top_issues(diagnosis_input: AIDiagnosisInput) -> list[AIDiagnosisReportIssue]:
    issue_statements = [
        statement
        for statement in diagnosis_input.statements
        if statement.severity in {AIDiagnosisSeverity.RISK, AIDiagnosisSeverity.WARNING}
    ]
    issue_statements.sort(key=lambda statement: SEVERITY_PRIORITY[statement.severity])

    return [
        build_report_issue(statement, priority=index)
        for index, statement in enumerate(issue_statements[:20], start=1)
    ]


def build_report_issue(
    statement: AIDiagnosisStatement,
    *,
    priority: int,
) -> AIDiagnosisReportIssue:
    return AIDiagnosisReportIssue(
        id=truncate_text(statement.id, max_length=120),
        priority=priority,
        title=truncate_text(statement.summary.rstrip("."), max_length=200),
        statement_type=statement.statement_type,
        severity=statement.severity,
        category=statement.category,
        summary=statement.summary,
        evidence_ids=statement.evidence_ids,
        expected_user_impact=expected_user_impact_for(statement.category),
        recommended_next_action=recommended_next_action_for(statement.category),
        unknown_reason=statement.unknown_reason,
    )


def build_score_based_issue(report_score: AIDiagnosisReportScore) -> AIDiagnosisReportIssue:
    severity = (
        AIDiagnosisSeverity.RISK
        if report_score.deployment_risk == AIDiagnosisDeploymentRisk.RISK
        else AIDiagnosisSeverity.WARNING
    )
    summary = (
        f"결정론 스코어링이 이 검사를 {report_score.deployment_risk.value}"
        f"(등급 {report_score.grade})로 판정했습니다."
    )
    return AIDiagnosisReportIssue(
        id="deployment-risk-score-result",
        priority=1,
        title="결정론 점수 기준 배포 위험",
        statement_type=AIDiagnosisStatementType.CONFIRMED_OBSERVATION,
        severity=severity,
        category="deployment_risk",
        summary=summary,
        evidence_ids=report_score.evidence_ids,
        expected_user_impact=expected_user_impact_for("deployment_risk"),
        recommended_next_action=recommended_next_action_for("deployment_risk"),
    )


def build_report_changes(
    diagnosis_input: AIDiagnosisInput,
) -> tuple[list[AIDiagnosisReportChange], list[AIDiagnosisReportChange]]:
    comparison = diagnosis_input.comparison_result
    if comparison is None:
        return [], []

    evidence_ids = find_evidence_ids(
        diagnosis_input,
        kind=AIDiagnosisEvidenceKind.RUN_COMPARISON,
    )
    if not evidence_ids:
        return [], []

    metrics: tuple[tuple[str, str, int | None, bool], ...] = (
        ("overall_score", "종합 점수", comparison.overall_score_delta, True),
        ("availability_score", "가용성 점수", comparison.availability_score_delta, True),
        ("web_performance_score", "웹 성능 점수", comparison.web_performance_score_delta, True),
        ("accessibility_score", "접근성 점수", comparison.accessibility_score_delta, True),
        (
            "seo_basic_quality_score",
            "SEO/기본 품질 점수",
            comparison.seo_basic_quality_score_delta,
            True,
        ),
        ("response_time_ms", "응답 시간", comparison.response_time_delta_ms, False),
        (
            "performance_score",
            "Lighthouse 성능 점수",
            comparison.performance_score_delta,
            True,
        ),
    )

    improved_areas: list[AIDiagnosisReportChange] = []
    regressed_areas: list[AIDiagnosisReportChange] = []
    for metric_name, label, delta, higher_is_better in metrics:
        if delta is None or delta == 0:
            continue

        is_improvement = delta > 0 if higher_is_better else delta < 0
        change = build_report_change(
            metric_name=metric_name,
            label=label,
            delta=delta,
            evidence_ids=evidence_ids,
            is_improvement=is_improvement,
        )
        if is_improvement:
            improved_areas.append(change)
        else:
            regressed_areas.append(change)

    return improved_areas[:20], regressed_areas[:20]


def build_report_change(
    *,
    metric_name: str,
    label: str,
    delta: int,
    evidence_ids: list[str],
    is_improvement: bool,
) -> AIDiagnosisReportChange:
    direction = "improved" if is_improvement else "regressed"
    if metric_name == "response_time_ms":
        amount = f"{abs(delta)}ms"
        verb = "빨라졌습니다" if is_improvement else "느려졌습니다"
    else:
        amount = f"{abs(delta)}점"
        verb = "개선되었습니다" if is_improvement else "하락했습니다"
    return AIDiagnosisReportChange(
        id=f"{metric_name}-{direction}",
        category="regression",
        summary=f"{label}{korean_subject_particle(label)} 기준 대비 {amount} {verb}.",
        evidence_ids=evidence_ids,
        metric_name=metric_name,
        delta=delta,
    )


def korean_subject_particle(word: str) -> str:
    """마지막 글자의 받침 유무로 주격 조사(이/가)를 고른다."""
    last = word[-1]
    if "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 > 0:
        return "이"
    return "가"


def build_generation_warnings(diagnosis_input: AIDiagnosisInput) -> list[str]:
    warnings: list[str] = []
    if diagnosis_input.comparison_result is None:
        warnings.append("실행 비교가 없어 개선/회귀 영역이 비어 있습니다.")
    elif not find_evidence_ids(diagnosis_input, kind=AIDiagnosisEvidenceKind.RUN_COMPARISON):
        warnings.append("실행 비교는 있었지만 비교 근거 항목이 제공되지 않았습니다.")

    return warnings


def build_report_summary(
    report_score: AIDiagnosisReportScore,
    top_issues: list[AIDiagnosisReportIssue],
) -> str:
    score_summary = (
        f"이 검사는 배포 위험도 {report_score.deployment_risk.value}, "
        f"등급 {report_score.grade}, 점수 {report_score.overall_score}/100으로 판정되었습니다."
    )
    if report_score.deployment_risk == AIDiagnosisDeploymentRisk.STABLE:
        return f"{score_summary} 근거에서 확인된 주요 배포 이슈는 없습니다."

    if top_issues:
        return f"{score_summary} 최우선 이슈: {top_issues[0].title}."

    return f"{score_summary} 주요 이슈 서술이 제공되지 않았습니다."


def find_evidence_ids(
    diagnosis_input: AIDiagnosisInput,
    *,
    kind: AIDiagnosisEvidenceKind,
) -> list[str]:
    return [item.id for item in diagnosis_input.evidence_items if item.kind == kind][:20]


def normalize_deployment_risk(score_result: ScoreResultRead) -> AIDiagnosisDeploymentRisk:
    try:
        return AIDiagnosisDeploymentRisk(score_result.deployment_risk)
    except ValueError as exc:
        raise AIDiagnosisReportGenerationError(
            f"Unsupported deployment risk: {score_result.deployment_risk}"
        ) from exc


def normalize_grade(grade: str) -> ReportGrade:
    if grade not in {"A", "B", "C", "D", "F"}:
        raise AIDiagnosisReportGenerationError(f"Unsupported report grade: {grade}")

    return cast(ReportGrade, grade)


def expected_user_impact_for(category: str) -> str:
    return ISSUE_IMPACT_BY_CATEGORY.get(
        category,
        "The affected user experience should be reviewed before deployment.",
    )


def recommended_next_action_for(category: str) -> str:
    return ISSUE_ACTION_BY_CATEGORY.get(
        category,
        "Review the referenced evidence and address the highest-impact issue first.",
    )


def truncate_text(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value

    return f"{value[: max_length - 3]}..."
