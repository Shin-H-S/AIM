from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from aim_api.models.project import Project
from aim_api.models.scanner_result import (
    AvailabilityResult,
    LighthouseResult,
    ScoreResult,
    SslResult,
)
from aim_api.models.scenario import (
    ConsoleError,
    ScenarioRun,
    ScenarioRunStatus,
    StepResult,
    StepResultStatus,
)

SCORING_VERSION = "2026-07-20.console-errors-v1"
SCORE_BREAKDOWN_VERSION = 1

# 서비스 성격별 카테고리 가중치 프리셋 (각 합 100).
# 가중치 0인 카테고리는 수집돼도 종합 점수에 반영되지 않는다.
DEFAULT_SCORING_PRESET = "service"

SCORING_PRESETS: dict[str, dict[str, int]] = {
    # 로그인·거래 등 핵심 흐름이 있는 웹 서비스 — 기능 > 접속 > 속도.
    "service": {
        "availability_score": 25,
        "functional_stability_score": 30,
        "web_performance_score": 20,
        "accessibility_score": 10,
        "seo_basic_quality_score": 5,
        "regression_stability_score": 10,
    },
    # 블로그·문서·마케팅 — 검색 유입과 로딩 속도가 핵심.
    "content": {
        "availability_score": 25,
        "functional_stability_score": 15,
        "web_performance_score": 30,
        "accessibility_score": 10,
        "seo_basic_quality_score": 15,
        "regression_stability_score": 5,
    },
    # 어드민·백오피스 — 검색엔진 무관, 동작이 전부.
    "internal": {
        "availability_score": 30,
        "functional_stability_score": 40,
        "web_performance_score": 15,
        "accessibility_score": 10,
        "seo_basic_quality_score": 0,
        "regression_stability_score": 5,
    },
}

# 하위 호환용 별칭 — 기본(서비스형) 가중치.
WEIGHTS = SCORING_PRESETS[DEFAULT_SCORING_PRESET]


def get_preset_weights(preset: str) -> dict[str, int]:
    """알 수 없는 프리셋 값은 기본 프리셋으로 처리해 점수 계산이 멈추지 않게 한다."""
    return SCORING_PRESETS.get(preset, SCORING_PRESETS[DEFAULT_SCORING_PRESET])


GRADE_ORDER = {
    "A": 5,
    "B": 4,
    "C": 3,
    "D": 2,
    "F": 1,
}


ScoreReasons = list[dict[str, Any]]


@dataclass(frozen=True)
class CalculatedScore:
    availability_score: int | None
    functional_stability_score: int | None
    web_performance_score: int | None
    accessibility_score: int | None
    seo_basic_quality_score: int | None
    regression_stability_score: int | None
    overall_score: int
    evaluated_weight: int
    grade: str
    deployment_risk: str
    gate_reason: str | None
    score_breakdown: dict[str, Any]
    scoring_version: str = SCORING_VERSION


def calculate_score(
    *,
    project: Project,
    availability_result: AvailabilityResult | None,
    ssl_result: SslResult | None,
    lighthouse_result: LighthouseResult | None,
    scenario_runs: list[ScenarioRun] | None = None,
    step_results_by_run_id: dict[UUID, list[StepResult]] | None = None,
    console_error_counts_by_run_id: dict[UUID, int] | None = None,
    previous_score_result: ScoreResult | None = None,
) -> CalculatedScore:
    scenario_runs = scenario_runs or []
    step_results_by_run_id = step_results_by_run_id or {}
    console_error_counts_by_run_id = console_error_counts_by_run_id or {}
    availability_score, availability_reasons = availability_score_with_reasons(
        availability_result=availability_result,
        response_time_threshold_ms=project.response_time_threshold_ms,
    )
    functional_stability_score, functional_reasons = functional_stability_score_with_reasons(
        scenario_runs=scenario_runs,
        step_results_by_run_id=step_results_by_run_id,
        console_error_counts_by_run_id=console_error_counts_by_run_id,
    )
    web_performance_score, web_performance_reasons = lighthouse_category_score_with_reasons(
        lighthouse_result,
        lighthouse_result.performance_score if lighthouse_result is not None else None,
    )
    accessibility_score, accessibility_reasons = lighthouse_category_score_with_reasons(
        lighthouse_result,
        lighthouse_result.accessibility_score if lighthouse_result is not None else None,
    )
    seo_basic_quality_score, seo_reasons = seo_basic_quality_score_with_reasons(lighthouse_result)

    current_scores: dict[str, int | None] = {
        "availability_score": availability_score,
        "functional_stability_score": functional_stability_score,
        "web_performance_score": web_performance_score,
        "accessibility_score": accessibility_score,
        "seo_basic_quality_score": seo_basic_quality_score,
    }
    regression_stability_score, regression_reasons = regression_stability_score_with_reasons(
        current_scores=current_scores,
        previous_score_result=previous_score_result,
    )

    category_scores = {
        **current_scores,
        "regression_stability_score": regression_stability_score,
    }
    scoring_preset = project.scoring_preset if project.scoring_preset else DEFAULT_SCORING_PRESET
    weights = get_preset_weights(scoring_preset)
    overall_score, evaluated_weight = calculate_weighted_score(category_scores, weights=weights)
    grade_before_gate = grade_for_score(overall_score)
    grade = grade_before_gate
    deployment_risk = "STABLE"
    gate_reason = None
    gate_breakdown: dict[str, Any] | None = None

    gate = evaluate_gate_with_code(
        project=project,
        availability_result=availability_result,
        ssl_result=ssl_result,
        lighthouse_result=lighthouse_result,
        scenario_runs=scenario_runs,
    )
    if gate is not None:
        deployment_risk, grade_cap, gate_reason, gate_code = gate
        grade = cap_grade(grade, grade_cap)
        gate_breakdown = {
            "code": gate_code,
            "deployment_risk": deployment_risk,
            "grade_cap": grade_cap,
            "detail": gate_reason,
        }

    score_breakdown = {
        "version": SCORE_BREAKDOWN_VERSION,
        "preset": scoring_preset,
        "categories": [
            {
                "key": "availability",
                "weight": weights["availability_score"],
                "score": availability_score,
                "reasons": availability_reasons,
            },
            {
                "key": "functional_stability",
                "weight": weights["functional_stability_score"],
                "score": functional_stability_score,
                "reasons": functional_reasons,
            },
            {
                "key": "web_performance",
                "weight": weights["web_performance_score"],
                "score": web_performance_score,
                "reasons": web_performance_reasons,
            },
            {
                "key": "accessibility",
                "weight": weights["accessibility_score"],
                "score": accessibility_score,
                "reasons": accessibility_reasons,
            },
            {
                "key": "seo_basic_quality",
                "weight": weights["seo_basic_quality_score"],
                "score": seo_basic_quality_score,
                "reasons": seo_reasons,
            },
            {
                "key": "regression_stability",
                "weight": weights["regression_stability_score"],
                "score": regression_stability_score,
                "reasons": regression_reasons,
            },
        ],
        "gate": gate_breakdown,
        "overall": {
            "score": overall_score,
            "evaluated_weight": evaluated_weight,
            "grade_before_gate": grade_before_gate,
        },
    }

    return CalculatedScore(
        availability_score=availability_score,
        functional_stability_score=functional_stability_score,
        web_performance_score=web_performance_score,
        accessibility_score=accessibility_score,
        seo_basic_quality_score=seo_basic_quality_score,
        regression_stability_score=regression_stability_score,
        overall_score=overall_score,
        evaluated_weight=evaluated_weight,
        grade=grade,
        deployment_risk=deployment_risk,
        gate_reason=gate_reason,
        score_breakdown=score_breakdown,
    )


def availability_score_with_reasons(
    *,
    availability_result: AvailabilityResult | None,
    response_time_threshold_ms: int,
) -> tuple[int | None, ScoreReasons]:
    if availability_result is None:
        return None, [{"code": "not_collected"}]

    if not availability_result.is_available:
        return 0, [{"code": "service_unavailable"}]

    score = 100
    reasons: ScoreReasons = []
    if not availability_result.uses_https:
        score -= 10
        reasons.append({"code": "no_https", "points": -10})

    if availability_result.redirect_count > 3:
        score -= 5
        reasons.append(
            {"code": "redirect_chain", "points": -5, "value": availability_result.redirect_count}
        )

    if availability_result.response_time_ms is not None:
        if availability_result.response_time_ms > response_time_threshold_ms * 2:
            score -= 40
            reasons.append(
                {
                    "code": "response_time_over_double_threshold",
                    "points": -40,
                    "value": availability_result.response_time_ms,
                    "threshold": response_time_threshold_ms,
                }
            )
        elif availability_result.response_time_ms > response_time_threshold_ms:
            score -= 20
            reasons.append(
                {
                    "code": "response_time_over_threshold",
                    "points": -20,
                    "value": availability_result.response_time_ms,
                    "threshold": response_time_threshold_ms,
                }
            )

    if not reasons:
        reasons.append({"code": "all_checks_passed"})

    return max(score, 0), reasons


def calculate_availability_score(
    *,
    availability_result: AvailabilityResult | None,
    response_time_threshold_ms: int,
) -> int | None:
    return availability_score_with_reasons(
        availability_result=availability_result,
        response_time_threshold_ms=response_time_threshold_ms,
    )[0]


def lighthouse_category_score_with_reasons(
    lighthouse_result: LighthouseResult | None,
    score: int | None,
) -> tuple[int | None, ScoreReasons]:
    if lighthouse_result is None:
        return None, [{"code": "not_collected"}]

    if not lighthouse_result.is_successful:
        return 0, [{"code": "lighthouse_failed"}]

    if score is None:
        return None, [{"code": "score_not_reported"}]

    return score, [{"code": "lighthouse_score"}]


def calculate_lighthouse_category_score(
    lighthouse_result: LighthouseResult | None,
    score: int | None,
) -> int | None:
    return lighthouse_category_score_with_reasons(lighthouse_result, score)[0]


def seo_basic_quality_score_with_reasons(
    lighthouse_result: LighthouseResult | None,
) -> tuple[int | None, ScoreReasons]:
    if lighthouse_result is None:
        return None, [{"code": "not_collected"}]

    if not lighthouse_result.is_successful:
        return 0, [{"code": "lighthouse_failed"}]

    scores = [
        score
        for score in [lighthouse_result.seo_score, lighthouse_result.best_practices_score]
        if score is not None
    ]
    if not scores:
        return None, [{"code": "score_not_reported"}]

    return round(sum(scores) / len(scores)), [
        {
            "code": "average_of_seo_and_best_practices",
            "seo": lighthouse_result.seo_score,
            "best_practices": lighthouse_result.best_practices_score,
        }
    ]


def calculate_seo_basic_quality_score(lighthouse_result: LighthouseResult | None) -> int | None:
    return seo_basic_quality_score_with_reasons(lighthouse_result)[0]


# 콘솔 에러 감점: 시나리오가 통과했어도 브라우저 콘솔 error는 사용자 흐름의 품질 신호다.
# 실행별로 1건당 5점, 실행당 최대 20점까지 감점한다(반복 에러가 점수를 지배하지 않도록 상한).
CONSOLE_ERROR_PENALTY = 5
CONSOLE_ERROR_PENALTY_CAP = 20


def functional_stability_score_with_reasons(
    *,
    scenario_runs: list[ScenarioRun],
    step_results_by_run_id: dict[UUID, list[StepResult]],
    console_error_counts_by_run_id: dict[UUID, int],
) -> tuple[int | None, ScoreReasons]:
    if not scenario_runs:
        return None, [{"code": "no_scenario_runs"}]

    run_scores: list[int] = []
    failed_runs = 0
    runs_with_failed_steps = 0
    clean_runs = 0
    total_console_errors = 0
    total_console_error_points = 0
    for scenario_run in scenario_runs:
        if scenario_run.status == ScenarioRunStatus.FAILED.value:
            run_scores.append(0)
            failed_runs += 1
            continue

        if scenario_run.status != ScenarioRunStatus.COMPLETED.value:
            continue

        step_results = step_results_by_run_id.get(scenario_run.id, [])
        has_failed_step = any(
            step_result.status == StepResultStatus.FAILED.value for step_result in step_results
        )
        if has_failed_step:
            runs_with_failed_steps += 1
        else:
            clean_runs += 1
        run_score = 80 if has_failed_step else 100

        console_error_count = console_error_counts_by_run_id.get(scenario_run.id, 0)
        if console_error_count > 0:
            deduction = min(CONSOLE_ERROR_PENALTY_CAP, CONSOLE_ERROR_PENALTY * console_error_count)
            run_score = max(0, run_score - deduction)
            total_console_errors += console_error_count
            total_console_error_points += deduction
        run_scores.append(run_score)

    if not run_scores:
        return None, [{"code": "no_scored_scenario_runs"}]

    reasons: ScoreReasons = [
        {
            "code": "scenario_runs_scored",
            "failed": failed_runs,
            "with_failed_steps": runs_with_failed_steps,
            "clean": clean_runs,
        }
    ]
    if total_console_errors > 0:
        reasons.append(
            {
                "code": "console_errors_deducted",
                "errors": total_console_errors,
                "points": total_console_error_points,
            }
        )
    return round(sum(run_scores) / len(run_scores)), reasons


def calculate_functional_stability_score(
    *,
    scenario_runs: list[ScenarioRun],
    step_results_by_run_id: dict[UUID, list[StepResult]],
    console_error_counts_by_run_id: dict[UUID, int],
) -> int | None:
    return functional_stability_score_with_reasons(
        scenario_runs=scenario_runs,
        step_results_by_run_id=step_results_by_run_id,
        console_error_counts_by_run_id=console_error_counts_by_run_id,
    )[0]


# 회귀 안정성: 직전 검사의 카테고리 원점수 대비 하락 폭 합계에 배수를 곱해 감점한다.
# 최종 종합 점수가 아니라 카테고리 원점수를 비교하므로 점수 계산에 순환이 생기지 않는다.
REGRESSION_PENALTY_MULTIPLIER = 2

REGRESSION_COMPARED_CATEGORY_KEYS = (
    "availability_score",
    "functional_stability_score",
    "web_performance_score",
    "accessibility_score",
    "seo_basic_quality_score",
)


def regression_stability_score_with_reasons(
    *,
    current_scores: dict[str, int | None],
    previous_score_result: ScoreResult | None,
) -> tuple[int | None, ScoreReasons]:
    if previous_score_result is None:
        return None, [{"code": "no_previous_run"}]

    compared = 0
    regressions: list[dict[str, Any]] = []
    for key in REGRESSION_COMPARED_CATEGORY_KEYS:
        current = current_scores.get(key)
        previous = getattr(previous_score_result, key)
        if current is None or previous is None:
            continue

        compared += 1
        drop = previous - current
        if drop > 0:
            regressions.append({"category": key.removesuffix("_score"), "drop": drop})

    if compared == 0:
        return None, [{"code": "no_comparable_categories"}]

    if not regressions:
        return 100, [{"code": "no_regressions", "compared": compared}]

    total_drop = sum(int(regression["drop"]) for regression in regressions)
    penalty = min(100, REGRESSION_PENALTY_MULTIPLIER * total_drop)
    return 100 - penalty, [
        {
            "code": "category_regressions",
            "points": -penalty,
            "total_drop": total_drop,
            "regressed": regressions,
        }
    ]


def calculate_regression_stability_score(
    *,
    current_scores: dict[str, int | None],
    previous_score_result: ScoreResult | None,
) -> int | None:
    return regression_stability_score_with_reasons(
        current_scores=current_scores,
        previous_score_result=previous_score_result,
    )[0]


def calculate_weighted_score(
    category_scores: dict[str, int | None],
    *,
    weights: dict[str, int] | None = None,
) -> tuple[int, int]:
    weights = weights if weights is not None else WEIGHTS
    weighted_total = 0
    evaluated_weight = 0
    for category, score in category_scores.items():
        if score is None:
            continue

        weight = weights[category]
        if weight == 0:
            continue

        weighted_total += score * weight
        evaluated_weight += weight

    if evaluated_weight == 0:
        return 0, 0

    return round(weighted_total / evaluated_weight), evaluated_weight


def evaluate_gate_with_code(
    *,
    project: Project,
    availability_result: AvailabilityResult | None,
    ssl_result: SslResult | None,
    lighthouse_result: LighthouseResult | None,
    scenario_runs: list[ScenarioRun],
) -> tuple[str, str, str, str] | None:
    if availability_result is None:
        return "WARNING", "C", "Availability result is missing.", "availability_missing"

    if not availability_result.is_available:
        return (
            "RISK",
            "F",
            availability_result.failure_reason or "Service is unavailable.",
            "service_unavailable",
        )

    if (
        availability_result.response_time_ms is not None
        and availability_result.response_time_ms > project.response_time_threshold_ms * 2
    ):
        return (
            "WARNING",
            "C",
            "Response time is over twice the configured threshold.",
            "response_time_over_double_threshold",
        )

    if ssl_result is not None and ssl_result.is_applicable and ssl_result.is_valid is False:
        return (
            "RISK",
            "D",
            ssl_result.failure_reason or "SSL certificate is invalid.",
            "ssl_invalid",
        )

    failed_scenario_run = next(
        (
            scenario_run
            for scenario_run in scenario_runs
            if scenario_run.status == ScenarioRunStatus.FAILED.value
        ),
        None,
    )
    if failed_scenario_run is not None:
        return (
            "RISK",
            "F",
            failed_scenario_run.failure_reason or "Critical scenario failed.",
            "scenario_failed",
        )

    if lighthouse_result is not None and not lighthouse_result.is_successful:
        return (
            "RISK",
            "D",
            lighthouse_result.failure_reason or "Lighthouse scan failed.",
            "lighthouse_failed",
        )

    if (
        lighthouse_result is not None
        and lighthouse_result.performance_score is not None
        and lighthouse_result.performance_score < project.quality_score_threshold
    ):
        return (
            "WARNING",
            "C",
            "Performance score is below the configured quality threshold.",
            "performance_below_threshold",
        )

    return None


def grade_for_score(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def cap_grade(grade: str, cap: str) -> str:
    return grade if GRADE_ORDER[grade] <= GRADE_ORDER[cap] else cap


def record_score_result(
    session: Session,
    *,
    check_run_id: UUID,
    project: Project,
    availability_result: AvailabilityResult | None,
    ssl_result: SslResult | None,
    lighthouse_result: LighthouseResult | None,
) -> ScoreResult:
    scenario_runs = list_latest_terminal_scenario_runs(
        session,
        project_id=project.id,
        check_run_id=check_run_id,
    )
    step_results_by_run_id = list_step_results_by_scenario_run_id(
        session,
        scenario_run_ids=[scenario_run.id for scenario_run in scenario_runs],
    )
    console_error_counts_by_run_id = count_console_errors_by_scenario_run_id(
        session,
        scenario_run_ids=[scenario_run.id for scenario_run in scenario_runs],
    )
    calculated_score = calculate_score(
        project=project,
        availability_result=availability_result,
        ssl_result=ssl_result,
        lighthouse_result=lighthouse_result,
        scenario_runs=scenario_runs,
        step_results_by_run_id=step_results_by_run_id,
        console_error_counts_by_run_id=console_error_counts_by_run_id,
        previous_score_result=get_previous_score_result(
            session,
            project_id=project.id,
            check_run_id=check_run_id,
        ),
    )
    result = get_score_result(session, check_run_id=check_run_id)
    if result is None:
        result = ScoreResult(check_run_id=check_run_id)
        session.add(result)

    result.availability_score = calculated_score.availability_score
    result.functional_stability_score = calculated_score.functional_stability_score
    result.web_performance_score = calculated_score.web_performance_score
    result.accessibility_score = calculated_score.accessibility_score
    result.seo_basic_quality_score = calculated_score.seo_basic_quality_score
    result.regression_stability_score = calculated_score.regression_stability_score
    result.overall_score = calculated_score.overall_score
    result.evaluated_weight = calculated_score.evaluated_weight
    result.grade = calculated_score.grade
    result.deployment_risk = calculated_score.deployment_risk
    result.gate_reason = calculated_score.gate_reason
    result.score_breakdown = calculated_score.score_breakdown
    result.scoring_version = calculated_score.scoring_version
    session.commit()
    session.refresh(result)
    return result


def get_score_result(
    session: Session,
    *,
    check_run_id: UUID,
) -> ScoreResult | None:
    return session.scalar(select(ScoreResult).where(ScoreResult.check_run_id == check_run_id))


def get_previous_score_result(
    session: Session,
    *,
    project_id: UUID,
    check_run_id: UUID,
) -> ScoreResult | None:
    """직전 검사의 점수 — '직전'의 정의는 직전 비교 기능과 동일한 조회를 재사용한다."""
    from aim_api.services.run_comparisons import get_previous_comparable_check_run

    previous_check_run = get_previous_comparable_check_run(
        session,
        project_id=project_id,
        check_run_id=check_run_id,
    )
    if previous_check_run is None:
        return None

    return get_score_result(session, check_run_id=previous_check_run.id)


def list_score_results_for_check_runs(
    session: Session,
    *,
    check_run_ids: list[UUID],
) -> dict[UUID, ScoreResult]:
    if not check_run_ids:
        return {}

    results = session.scalars(
        select(ScoreResult).where(ScoreResult.check_run_id.in_(check_run_ids))
    )
    return {result.check_run_id: result for result in results}


def list_latest_terminal_scenario_runs(
    session: Session,
    *,
    project_id: UUID,
    check_run_id: UUID | None = None,
) -> list[ScenarioRun]:
    terminal_statuses = {
        ScenarioRunStatus.COMPLETED.value,
        ScenarioRunStatus.FAILED.value,
    }
    if check_run_id is not None:
        linked_scenario_runs = list(
            session.scalars(
                select(ScenarioRun)
                .where(ScenarioRun.check_run_id == check_run_id)
                .order_by(ScenarioRun.created_at.asc(), ScenarioRun.id.asc())
            )
        )
        if linked_scenario_runs:
            return [
                scenario_run
                for scenario_run in linked_scenario_runs
                if scenario_run.status in terminal_statuses
            ]

    scenario_runs = list(
        session.scalars(
            select(ScenarioRun)
            .where(
                ScenarioRun.project_id == project_id,
                ScenarioRun.status.in_(terminal_statuses),
            )
            .order_by(
                ScenarioRun.scenario_id.asc(),
                ScenarioRun.created_at.desc(),
                ScenarioRun.id.desc(),
            )
        )
    )

    latest_runs: list[ScenarioRun] = []
    seen_scenario_ids: set[UUID] = set()
    for scenario_run in scenario_runs:
        if scenario_run.scenario_id in seen_scenario_ids:
            continue

        latest_runs.append(scenario_run)
        seen_scenario_ids.add(scenario_run.scenario_id)

    return latest_runs


def list_step_results_by_scenario_run_id(
    session: Session,
    *,
    scenario_run_ids: list[UUID],
) -> dict[UUID, list[StepResult]]:
    if not scenario_run_ids:
        return {}

    step_results = list(
        session.scalars(
            select(StepResult)
            .where(StepResult.scenario_run_id.in_(scenario_run_ids))
            .order_by(StepResult.scenario_run_id.asc(), StepResult.step_order.asc())
        )
    )
    grouped_results: dict[UUID, list[StepResult]] = {
        scenario_run_id: [] for scenario_run_id in scenario_run_ids
    }
    for step_result in step_results:
        grouped_results.setdefault(step_result.scenario_run_id, []).append(step_result)

    return grouped_results


def count_console_errors_by_scenario_run_id(
    session: Session,
    *,
    scenario_run_ids: list[UUID],
) -> dict[UUID, int]:
    if not scenario_run_ids:
        return {}

    rows = session.execute(
        select(ConsoleError.scenario_run_id, func.count())
        .where(ConsoleError.scenario_run_id.in_(scenario_run_ids))
        .group_by(ConsoleError.scenario_run_id)
    ).all()
    return {scenario_run_id: count for scenario_run_id, count in rows}
