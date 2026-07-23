"""관찰 렌더러 — 도구 응답을 사람이 읽는 증거 카드 한 줄로.

LLM 프롬프트·trace 요약·UI 타임라인이 같은 문장을 쓴다. 원시 repr 덤프는
토큰 낭비이고 파이썬 표현 형식에 결합되므로 여기서 끊는다. 판별에 쓰이는
계산(응답시간/임계 배율 등)은 렌더러가 미리 해서 넣는다 — 정책(특히 LLM)의
일을 "특징 읽고 판단"으로 줄이는 것이 목적이다.
"""

from collections.abc import Callable
from typing import cast

from aim_worker.agent.cases import (
    ArtifactsSnapshot,
    BaselineComparison,
    CheckRunSnapshot,
    ProjectConfigSnapshot,
    RecentRunSummary,
    RecheckResult,
    ScenarioStepResult,
)
from aim_worker.agent.trace import summarize_result


def render_check_run(check: CheckRunSnapshot) -> str:
    parts = [f"점수 {check.overall_score}({check.grade}) 위험 {check.deployment_risk}"]
    if check.availability_ok:
        parts.append("가용성 정상")
    else:
        parts.append(f"가용성 실패({check.availability_failure})")
    if check.response_time_ms is None:
        parts.append("응답시간 측정 불가")
    else:
        ratio = check.response_time_ms / check.response_time_threshold_ms
        parts.append(
            f"응답 {check.response_time_ms}ms = 임계 {check.response_time_threshold_ms}ms의"
            f" {ratio:.1f}배"
        )
    if check.ssl_valid is True:
        parts.append("SSL 정상")
    elif check.ssl_valid is False:
        parts.append(f"SSL 무효({check.ssl_failure})")
    else:
        parts.append("SSL 판단 불가")
    if check.lighthouse_performance is None:
        parts.append("성능 측정 불가")
    else:
        parts.append(f"Lighthouse 성능 {check.lighthouse_performance}")
    trigger = f"트리거 {check.trigger_source}"
    if check.deploy_ref:
        trigger += f"@{check.deploy_ref}"
    parts.append(trigger)
    if check.gate_reason:
        parts.append(f"게이트 사유: {check.gate_reason}")
    return " · ".join(parts)


def render_scenario_results(steps: tuple[ScenarioStepResult, ...]) -> str:
    if not steps:
        return "시나리오 결과 없음"
    failed = sum(1 for step in steps if step.status == "FAILED")
    lines = [f"{len(steps)}스텝 중 실패 {failed}"]
    for step in steps:
        target = f" {step.target}" if step.target else ""
        line = f"{step.step_order} {step.action}{target} {step.status}"
        if step.error:
            line += f"({step.error})"
        lines.append(line)
    return " · ".join(lines)


def render_artifacts(artifacts: ArtifactsSnapshot) -> str:
    parts = []
    if artifacts.console_errors:
        parts.append(f"콘솔 에러 {len(artifacts.console_errors)}건({artifacts.console_errors[0]})")
    else:
        parts.append("콘솔 깨끗")
    if artifacts.network_failures:
        parts.append(
            f"네트워크 실패 {len(artifacts.network_failures)}건({artifacts.network_failures[0]})"
        )
    else:
        parts.append("네트워크 깨끗")
    if artifacts.failing_page_rendered_ok is True:
        parts.append("실패 지점 페이지는 정상 렌더")
    elif artifacts.failing_page_rendered_ok is False:
        parts.append("실패 지점 페이지 렌더 파손")
    if artifacts.redirect_detected_to is not None:
        parts.append(f"리다이렉트 감지 → {artifacts.redirect_detected_to}")
    if artifacts.relocation_hint is not None:
        parts.append(f"이동 흔적: {artifacts.relocation_hint}")
    else:
        parts.append("기대 요소의 이동 흔적 없음")
    return " · ".join(parts)


def render_baseline(baseline: BaselineComparison) -> str:
    if (
        baseline.overall_delta is None
        and baseline.performance_delta is None
        and baseline.response_time_delta_ms is None
    ):
        return "기준점 비교 불가"
    parts = []
    if baseline.overall_delta is not None:
        parts.append(f"종합 {baseline.overall_delta:+.1f}")
    if baseline.performance_delta is not None:
        parts.append(f"성능 {baseline.performance_delta:+d}")
    if baseline.response_time_delta_ms is not None:
        parts.append(f"응답 {baseline.response_time_delta_ms:+d}ms")
    return "기준점 대비 " + ", ".join(parts)


def render_recent_runs(runs: tuple[RecentRunSummary, ...]) -> str:
    if not runs:
        return "과거 실행 없음"
    scores = ", ".join(f"{run.overall_score:.0f}" for run in runs)
    responses = ", ".join(
        "-" if run.response_time_ms is None else str(run.response_time_ms) for run in runs
    )
    performances = ", ".join(
        "-" if run.lighthouse_performance is None else str(run.lighthouse_performance)
        for run in runs
    )
    return (
        f"최근 {len(runs)}회(최신순) — 점수 [{scores}] · 응답 [{responses}]ms"
        f" · 성능 [{performances}]"
    )


def render_project_config(config: ProjectConfigSnapshot) -> str:
    targets = ", ".join(config.scenario_targets) if config.scenario_targets else "없음"
    return (
        f"대상 {config.service_url} · 응답 임계 {config.response_time_threshold_ms}ms"
        f" · 점수 임계 {config.quality_score_threshold} · 시나리오 타깃 {targets}"
    )


def render_recheck(recheck: RecheckResult) -> str:
    verdict = "재현됨" if recheck.reproduced else "미재현"
    return f"재검사: {verdict}(점수 {recheck.overall_score})"


_RENDER_BY_TOOL: dict[str, Callable[[object], str]] = {
    "get_check_run": lambda result: render_check_run(cast(CheckRunSnapshot, result)),
    "get_scenario_results": lambda result: render_scenario_results(
        cast(tuple[ScenarioStepResult, ...], result)
    ),
    "get_artifacts": lambda result: render_artifacts(cast(ArtifactsSnapshot, result)),
    "compare_with_baseline": lambda result: render_baseline(cast(BaselineComparison, result)),
    "get_recent_runs": lambda result: render_recent_runs(
        cast(tuple[RecentRunSummary, ...], result)
    ),
    "get_project_config": lambda result: render_project_config(cast(ProjectConfigSnapshot, result)),
    "trigger_recheck": lambda result: render_recheck(cast(RecheckResult, result)),
}


def render_observation(tool: str, result: object) -> str:
    """도구 이름으로 렌더러를 고른다 — 모르는 도구·타입은 repr 요약 폴백."""
    renderer = _RENDER_BY_TOOL.get(tool)
    if renderer is None:
        return summarize_result(result)
    return renderer(result)
