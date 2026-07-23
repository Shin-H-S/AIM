"""평가셋 v1 생성기 — 유형당 15건 × 7유형 = 105건, 시드 고정으로 결정적 생성.

원칙:
- 정답 라벨은 fixtures에 담긴 증거로 판별 가능해야 한다(공정한 채점).
- 단, 경계 사례(약한·혼합 신호)를 섞어 단순 규칙이 만점을 내지 못하게 한다 —
  규칙 베이스라인이 목표선(LLM이 넘어야 할 선)이 되게 하는 설계다.
- 실측 사고 3건(GCP VM 정지·다운사이징 성능 하락·로그인 이사 스테일)은
  수제 케이스로 재현하고 curated로 표기한다.
"""

import random
from collections.abc import Callable

from aim_worker.agent.cases import (
    ArtifactsSnapshot,
    BaselineComparison,
    CheckRunSnapshot,
    EvalCase,
    ProjectConfigSnapshot,
    RecentRunSummary,
    RecheckResult,
    ScenarioStepResult,
    ToolFixtures,
)
from aim_worker.agent.root_causes import RootCause

DATASET_SEED = 20260720
CASES_PER_CAUSE = 15

SERVICE_URL = "https://myservice.example"
DEFAULT_THRESHOLD_MS = 500


def healthy_recent_runs(rng: random.Random, count: int = 5) -> tuple[RecentRunSummary, ...]:
    return tuple(
        RecentRunSummary(
            overall_score=round(rng.uniform(94.0, 100.0), 1),
            all_scenarios_passed=True,
            response_time_ms=rng.randint(80, 240),
        )
        for _ in range(count)
    )


def passing_steps(rng: random.Random) -> tuple[ScenarioStepResult, ...]:
    return (
        ScenarioStepResult(1, "navigate", f"{SERVICE_URL}/login", "PASSED", None),
        ScenarioStepResult(2, "fill", "#email", "PASSED", None),
        ScenarioStepResult(3, "click", 'button[type="submit"]', "PASSED", None),
        ScenarioStepResult(4, "assert_url", None, "PASSED", None),
    )


def default_config(targets: tuple[str, ...] = (f"{SERVICE_URL}/login",)) -> ProjectConfigSnapshot:
    return ProjectConfigSnapshot(
        service_url=SERVICE_URL,
        scenario_targets=targets,
        response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
        quality_score_threshold=80,
    )


def build_service_down(rng: random.Random, index: int) -> EvalCase:
    failure = rng.choice(["connect timeout", "connection refused", "dns resolution failed"])
    steps = tuple(
        ScenarioStepResult(
            order,
            action,
            target,
            "FAILED" if order == 1 else "SKIPPED",
            failure if order == 1 else None,
        )
        for order, action, target in (
            (1, "navigate", f"{SERVICE_URL}/login"),
            (2, "fill", "#email"),
            (3, "click", 'button[type="submit"]'),
        )
    )
    fixtures = ToolFixtures(
        check_run=CheckRunSnapshot(
            overall_score=round(rng.uniform(5.0, 25.0), 1),
            grade="F",
            deployment_risk="RISK",
            gate_reason=f"Service is unavailable: {failure}",
            availability_ok=False,
            availability_failure=failure,
            response_time_ms=None,
            response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
            ssl_valid=None,
            ssl_failure=None,
            lighthouse_performance=None,
            trigger_source=rng.choice(["scheduled", "deploy"]),
            deploy_ref=None,
        ),
        scenario_results=steps,
        artifacts=ArtifactsSnapshot(network_failures=(failure,)),
        baseline=BaselineComparison(None, None, None),
        recent_runs=healthy_recent_runs(rng),
        project_config=default_config(),
        recheck=RecheckResult(reproduced=True, overall_score=round(rng.uniform(5.0, 25.0), 1)),
    )
    return EvalCase(
        f"service_down-{index:02d}", RootCause.SERVICE_DOWN, f"가용성 실패({failure})", fixtures
    )


def build_ssl_invalid(rng: random.Random, index: int) -> EvalCase:
    days = rng.randint(1, 30)
    failure = rng.choice(
        [f"certificate expired {days} days ago", "self-signed certificate in chain"]
    )
    fixtures = ToolFixtures(
        check_run=CheckRunSnapshot(
            overall_score=round(rng.uniform(55.0, 75.0), 1),
            grade="D",
            deployment_risk="RISK",
            gate_reason=failure,
            availability_ok=True,
            availability_failure=None,
            response_time_ms=rng.randint(90, 280),
            response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
            ssl_valid=False,
            ssl_failure=failure,
            lighthouse_performance=rng.randint(85, 99),
            trigger_source="scheduled",
            deploy_ref=None,
        ),
        scenario_results=passing_steps(rng),
        artifacts=ArtifactsSnapshot(),
        baseline=BaselineComparison(round(rng.uniform(-40.0, -20.0), 1), 0, rng.randint(-20, 20)),
        recent_runs=healthy_recent_runs(rng),
        project_config=default_config(),
        recheck=RecheckResult(reproduced=True, overall_score=round(rng.uniform(55.0, 75.0), 1)),
    )
    return EvalCase(
        f"ssl_invalid-{index:02d}", RootCause.SSL_INVALID, f"SSL 무효({failure})", fixtures
    )


def build_server_slow(rng: random.Random, index: int) -> EvalCase:
    multiplier = rng.uniform(2.2, 6.0)
    response_ms = int(DEFAULT_THRESHOLD_MS * multiplier)
    # 경계 사례(약 1/3): 지연 때문에 wait 스텝 하나가 타임아웃으로 실패
    slow_breaks_step = index % 3 == 0
    steps: tuple[ScenarioStepResult, ...]
    if slow_breaks_step:
        steps = (
            ScenarioStepResult(1, "navigate", f"{SERVICE_URL}/login", "PASSED", None),
            ScenarioStepResult(2, "wait", None, "FAILED", "timeout waiting for selector"),
            ScenarioStepResult(3, "click", 'button[type="submit"]', "SKIPPED", None),
        )
    else:
        steps = passing_steps(rng)
    creeping = tuple(
        RecentRunSummary(
            overall_score=round(rng.uniform(88.0, 97.0), 1),
            all_scenarios_passed=True,
            response_time_ms=int(DEFAULT_THRESHOLD_MS * (1.0 + 0.35 * offset)),
        )
        for offset in range(4, 0, -1)
    )
    fixtures = ToolFixtures(
        check_run=CheckRunSnapshot(
            overall_score=round(rng.uniform(55.0, 78.0), 1),
            grade=rng.choice(["C", "D"]),
            deployment_risk="WARNING",
            gate_reason="Response time is over twice the configured threshold.",
            availability_ok=True,
            availability_failure=None,
            response_time_ms=response_ms,
            response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
            ssl_valid=True,
            ssl_failure=None,
            lighthouse_performance=rng.randint(78, 92),
            trigger_source=rng.choice(["scheduled", "deploy"]),
            deploy_ref=rng.choice([None, "b1c2d3e"]),
        ),
        scenario_results=steps,
        artifacts=ArtifactsSnapshot(failing_page_rendered_ok=True if slow_breaks_step else None),
        baseline=BaselineComparison(
            round(rng.uniform(-25.0, -8.0), 1),
            rng.randint(-8, 0),
            response_ms - rng.randint(100, 240),
        ),
        recent_runs=creeping,
        project_config=default_config(),
        recheck=RecheckResult(reproduced=True, overall_score=round(rng.uniform(55.0, 78.0), 1)),
    )
    return EvalCase(
        f"server_slow-{index:02d}",
        RootCause.SERVER_SLOW,
        f"응답 지연 {response_ms}ms (임계 {DEFAULT_THRESHOLD_MS}ms)",
        fixtures,
    )


def build_frontend_regression(rng: random.Random, index: int) -> EvalCase:
    drop = rng.randint(12, 40)
    performance = max(30, 95 - drop)
    fixtures = ToolFixtures(
        check_run=CheckRunSnapshot(
            overall_score=round(rng.uniform(70.0, 88.0), 1),
            grade=rng.choice(["B", "C"]),
            deployment_risk="WARNING",
            gate_reason=None,
            availability_ok=True,
            availability_failure=None,
            response_time_ms=rng.randint(90, 280),
            response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
            ssl_valid=True,
            ssl_failure=None,
            lighthouse_performance=performance,
            trigger_source="deploy",
            deploy_ref=f"{rng.randrange(16**7):07x}",
        ),
        scenario_results=passing_steps(rng),
        artifacts=ArtifactsSnapshot(),
        baseline=BaselineComparison(
            round(rng.uniform(-18.0, -6.0), 1), -drop, rng.randint(-30, 30)
        ),
        recent_runs=healthy_recent_runs(rng),
        project_config=default_config(),
        recheck=RecheckResult(reproduced=True, overall_score=round(rng.uniform(70.0, 88.0), 1)),
    )
    return EvalCase(
        f"frontend_regression-{index:02d}",
        RootCause.FRONTEND_REGRESSION,
        f"Lighthouse 성능 -{drop}",
        fixtures,
    )


def build_ui_regression(rng: random.Random, index: int) -> EvalCase:
    broken_step = rng.choice(
        [
            (2, "fill", "#email", 'no element matches selector "#email"'),
            (3, "click", 'button[type="submit"]', "element is not clickable"),
            (4, "assert_text_exists", None, 'expected text "대시보드" not found'),
        ]
    )
    order, action, target, error = broken_step
    steps = tuple(
        ScenarioStepResult(
            step,
            step_action,
            step_target,
            "PASSED" if step < order else ("FAILED" if step == order else "SKIPPED"),
            error if step == order else None,
        )
        for step, step_action, step_target in (
            (1, "navigate", f"{SERVICE_URL}/login"),
            (2, "fill", "#email"),
            (3, "click", 'button[type="submit"]'),
            (4, "assert_text_exists", None),
        )
    )
    # 경계 사례(약 1/3): 콘솔 에러 없이 요소만 깨진 조용한 파손
    silent = index % 3 == 2
    artifacts = ArtifactsSnapshot(
        console_errors=() if silent else ("TypeError: cannot read properties of undefined",),
        network_failures=() if silent or index % 2 == 0 else ("POST /api/session 500",),
        failing_page_rendered_ok=silent,
        redirect_detected_to=None,
    )
    fixtures = ToolFixtures(
        check_run=CheckRunSnapshot(
            overall_score=round(rng.uniform(45.0, 65.0), 1),
            grade="F",
            deployment_risk="RISK",
            gate_reason=error,
            availability_ok=True,
            availability_failure=None,
            response_time_ms=rng.randint(90, 300),
            response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
            ssl_valid=True,
            ssl_failure=None,
            lighthouse_performance=rng.randint(85, 99),
            trigger_source="deploy",
            deploy_ref=f"{rng.randrange(16**7):07x}",
        ),
        scenario_results=steps,
        artifacts=artifacts,
        baseline=BaselineComparison(
            round(rng.uniform(-45.0, -25.0), 1), rng.randint(-5, 3), rng.randint(-30, 30)
        ),
        recent_runs=healthy_recent_runs(rng),
        project_config=default_config(),
        recheck=RecheckResult(reproduced=True, overall_score=round(rng.uniform(45.0, 65.0), 1)),
    )
    return EvalCase(
        f"ui_regression-{index:02d}",
        RootCause.UI_REGRESSION,
        f"스텝 {order} 파손({action})",
        fixtures,
    )


def build_scenario_stale(rng: random.Random, index: int) -> EvalCase:
    # 서비스 개편으로 시나리오 전제가 낡음 — 페이지는 정상 렌더, 콘솔은 조용함.
    moved_to = rng.choice([f"{SERVICE_URL}/login", f"{SERVICE_URL}/auth/signin"])
    old_target = f"{SERVICE_URL}/"
    with_redirect = index % 5 != 4  # 일부는 리다이렉트 흔적 없이(더 어려운 케이스)
    steps = (
        ScenarioStepResult(1, "navigate", old_target, "PASSED", None),
        ScenarioStepResult(2, "fill", "#email", "FAILED", 'no element matches selector "#email"'),
        ScenarioStepResult(3, "click", 'button[type="submit"]', "SKIPPED", None),
    )
    fixtures = ToolFixtures(
        check_run=CheckRunSnapshot(
            overall_score=round(rng.uniform(50.0, 68.0), 1),
            grade="F",
            deployment_risk="RISK",
            gate_reason='no element matches selector "#email"',
            availability_ok=True,
            availability_failure=None,
            response_time_ms=rng.randint(90, 260),
            response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
            ssl_valid=True,
            ssl_failure=None,
            lighthouse_performance=rng.randint(90, 99),
            trigger_source="deploy",
            deploy_ref=f"{rng.randrange(16**7):07x}",
        ),
        scenario_results=steps,
        artifacts=ArtifactsSnapshot(
            console_errors=(),
            network_failures=(),
            failing_page_rendered_ok=True,
            redirect_detected_to=moved_to if with_redirect else None,
        ),
        baseline=BaselineComparison(
            round(rng.uniform(-45.0, -28.0), 1), rng.randint(-3, 5), rng.randint(-30, 30)
        ),
        recent_runs=healthy_recent_runs(rng),
        project_config=default_config(targets=(old_target,)),
        recheck=RecheckResult(reproduced=True, overall_score=round(rng.uniform(50.0, 68.0), 1)),
    )
    return EvalCase(
        f"scenario_stale-{index:02d}",
        RootCause.SCENARIO_STALE,
        "요소 이사 후 시나리오 낡음",
        fixtures,
    )


def build_measurement_noise(rng: random.Random, index: int) -> EvalCase:
    flavor = rng.choice(["timeout-blip", "lighthouse-dip"])
    if flavor == "timeout-blip":
        check = CheckRunSnapshot(
            overall_score=round(rng.uniform(60.0, 80.0), 1),
            grade="C",
            deployment_risk="WARNING",
            gate_reason="Response time is over twice the configured threshold.",
            availability_ok=True,
            availability_failure=None,
            response_time_ms=int(DEFAULT_THRESHOLD_MS * rng.uniform(2.1, 3.0)),
            response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
            ssl_valid=True,
            ssl_failure=None,
            lighthouse_performance=rng.randint(88, 99),
            trigger_source="scheduled",
            deploy_ref=None,
        )
        title = "일시적 응답 지연 — 재검사 시 정상"
    else:
        check = CheckRunSnapshot(
            overall_score=round(rng.uniform(74.0, 86.0), 1),
            grade="B",
            deployment_risk="WARNING",
            gate_reason=None,
            availability_ok=True,
            availability_failure=None,
            response_time_ms=rng.randint(90, 260),
            response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
            ssl_valid=True,
            ssl_failure=None,
            lighthouse_performance=rng.randint(60, 74),
            trigger_source="scheduled",
            deploy_ref=None,
        )
        title = "일시적 성능 점수 하락 — 재검사 시 정상"
    fixtures = ToolFixtures(
        check_run=check,
        scenario_results=passing_steps(rng),
        artifacts=ArtifactsSnapshot(),
        baseline=BaselineComparison(
            round(rng.uniform(-20.0, -8.0), 1), rng.randint(-20, 0), rng.randint(0, 900)
        ),
        recent_runs=healthy_recent_runs(rng),
        project_config=default_config(),
        recheck=RecheckResult(reproduced=False, overall_score=round(rng.uniform(95.0, 100.0), 1)),
    )
    return EvalCase(f"measurement_noise-{index:02d}", RootCause.MEASUREMENT_NOISE, title, fixtures)


def curated_cases() -> tuple[EvalCase, ...]:
    """실측 사고 3건의 재현 — 합성 케이스와 구분해 curated로 표기."""
    gcp_down = EvalCase(
        "curated-gcp-vm-stopped",
        RootCause.SERVICE_DOWN,
        "실측 2026-07-17: VM 정지로 전면 불달",
        ToolFixtures(
            check_run=CheckRunSnapshot(
                overall_score=8.0,
                grade="F",
                deployment_risk="RISK",
                gate_reason="Service is unavailable: connect timeout",
                availability_ok=False,
                availability_failure="connect timeout",
                response_time_ms=None,
                response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
                ssl_valid=None,
                ssl_failure=None,
                lighthouse_performance=None,
                trigger_source="scheduled",
                deploy_ref=None,
            ),
            scenario_results=(
                ScenarioStepResult(1, "navigate", f"{SERVICE_URL}/", "FAILED", "connect timeout"),
                ScenarioStepResult(2, "fill", "#email", "SKIPPED", None),
            ),
            artifacts=ArtifactsSnapshot(network_failures=("connect timeout",)),
            baseline=BaselineComparison(None, None, None),
            recent_runs=(
                RecentRunSummary(97.0, True, 150),
                RecentRunSummary(99.0, True, 140),
            ),
            project_config=default_config(),
            recheck=RecheckResult(reproduced=True, overall_score=8.0),
        ),
        curated=True,
    )
    downsize_perf = EvalCase(
        "curated-e2-downsize-perf",
        RootCause.FRONTEND_REGRESSION,
        "실측 2026-07-14: 다운사이징 후 성능 99→86 체계적 하락",
        ToolFixtures(
            check_run=CheckRunSnapshot(
                overall_score=97.0,
                grade="A",
                deployment_risk="WARNING",
                gate_reason=None,
                availability_ok=True,
                availability_failure=None,
                response_time_ms=150,
                response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
                ssl_valid=True,
                ssl_failure=None,
                lighthouse_performance=86,
                trigger_source="scheduled",
                deploy_ref=None,
            ),
            scenario_results=(
                ScenarioStepResult(1, "navigate", f"{SERVICE_URL}/", "PASSED", None),
                ScenarioStepResult(2, "fill", "#email", "PASSED", None),
                ScenarioStepResult(3, "click", 'button[type="submit"]', "PASSED", None),
            ),
            artifacts=ArtifactsSnapshot(),
            baseline=BaselineComparison(-2.0, -13, 5),
            recent_runs=(
                RecentRunSummary(97.0, True, 155),
                RecentRunSummary(97.0, True, 148),
                RecentRunSummary(99.0, True, 150),
                RecentRunSummary(99.0, True, 152),
            ),
            project_config=default_config(),
            recheck=RecheckResult(reproduced=True, overall_score=97.0),
        ),
        curated=True,
    )
    login_moved = EvalCase(
        "curated-login-moved-stale",
        RootCause.SCENARIO_STALE,
        "실측 2026-07-18: 로그인 폼 /login 이사 후 시나리오 스테일",
        ToolFixtures(
            check_run=CheckRunSnapshot(
                overall_score=59.0,
                grade="F",
                deployment_risk="RISK",
                gate_reason="Expected element was not found.",
                availability_ok=True,
                availability_failure=None,
                response_time_ms=120,
                response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
                ssl_valid=True,
                ssl_failure=None,
                lighthouse_performance=99,
                trigger_source="deploy",
                deploy_ref="970cfff",
            ),
            scenario_results=(
                ScenarioStepResult(1, "navigate", f"{SERVICE_URL}/", "PASSED", None),
                ScenarioStepResult(
                    2, "fill", "#email", "FAILED", 'no element matches selector "#email"'
                ),
                ScenarioStepResult(3, "click", 'button[type="submit"]', "SKIPPED", None),
            ),
            artifacts=ArtifactsSnapshot(
                console_errors=(),
                network_failures=(),
                failing_page_rendered_ok=True,
                redirect_detected_to=None,
            ),
            baseline=BaselineComparison(-38.0, 2, -10),
            recent_runs=(
                RecentRunSummary(97.0, True, 130),
                RecentRunSummary(97.0, True, 145),
            ),
            project_config=default_config(targets=(f"{SERVICE_URL}/",)),
            recheck=RecheckResult(reproduced=True, overall_score=59.0),
        ),
        curated=True,
    )
    return (gcp_down, downsize_perf, login_moved)


BUILDERS: dict[RootCause, Callable[[random.Random, int], EvalCase]] = {
    RootCause.SERVICE_DOWN: build_service_down,
    RootCause.SSL_INVALID: build_ssl_invalid,
    RootCause.SERVER_SLOW: build_server_slow,
    RootCause.FRONTEND_REGRESSION: build_frontend_regression,
    RootCause.UI_REGRESSION: build_ui_regression,
    RootCause.SCENARIO_STALE: build_scenario_stale,
    RootCause.MEASUREMENT_NOISE: build_measurement_noise,
}


def generate_cases(seed: int = DATASET_SEED) -> tuple[EvalCase, ...]:
    """전체 평가셋 105건 — 유형당 15건(수제 케이스는 해당 유형 수에 포함)."""
    rng = random.Random(seed)
    curated = curated_cases()
    curated_counts: dict[RootCause, int] = {}
    for case in curated:
        curated_counts[case.root_cause] = curated_counts.get(case.root_cause, 0) + 1

    cases: list[EvalCase] = list(curated)
    for cause, builder in BUILDERS.items():
        synthetic_count = CASES_PER_CAUSE - curated_counts.get(cause, 0)
        for index in range(synthetic_count):
            cases.append(builder(rng, index))
    return tuple(cases)


def split_cases(cases: tuple[EvalCase, ...]) -> tuple[tuple[EvalCase, ...], tuple[EvalCase, ...]]:
    """dev/test 분리 — 유형별로 교차 배분해 두 셋의 유형 균형을 유지한다."""
    dev: list[EvalCase] = []
    test: list[EvalCase] = []
    for cause in RootCause:
        of_cause = sorted(
            (case for case in cases if case.root_cause == cause), key=lambda c: c.case_id
        )
        for position, case in enumerate(of_cause):
            (dev if position % 2 == 0 else test).append(case)
    return tuple(dev), tuple(test)
