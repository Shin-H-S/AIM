"""평가셋 생성기 — 유형당 25건 × 7유형 = 175건, 시드 고정으로 결정적 생성.

원칙:
- 정답 라벨은 fixtures에 담긴 증거로 판별 가능해야 한다(공정한 채점).
- 단, 경계 사례(약한·혼합 신호)를 섞어 단순 규칙이 만점을 내지 못하게 한다 —
  규칙 베이스라인이 목표선(LLM이 넘어야 할 선)이 되게 하는 설계다.
- fixtures는 실제 스캐너의 의미론을 따른다(예: 무효 인증서는 가용성 검사도
  함께 죽는다) — 합성 케이스로 튜닝한 판단이 운영에서도 성립해야 한다.
- 표면(플로우·셀렉터·에러 문구)은 변주한다 — 특정 문자열이 라벨의 지름길이
  되면 LLM이 의미가 아니라 문자열을 학습한다.
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
CASES_PER_CAUSE = 25

SERVICE_URL = "https://myservice.example"
DEFAULT_THRESHOLD_MS = 500

# (플로우명, 경로, fill 셀렉터, click 셀렉터, 성공 확인 문구) — 케이스를
# 여러 사용자 플로우에 분산해 문자열 지름길 학습을 막는다.
FLOWS: tuple[tuple[str, str, str, str, str], ...] = (
    ("로그인", "/login", "#email", 'button[type="submit"]', "대시보드"),
    ("결제", "/checkout", "#card-number", "button.pay-now", "주문 완료"),
    ("검색", "/search", 'input[name="q"]', "button.search-submit", "검색 결과"),
    ("가입", "/signup", "#nickname", 'button[type="submit"]', "환영합니다"),
)


def healthy_recent_runs(rng: random.Random, count: int = 5) -> tuple[RecentRunSummary, ...]:
    return tuple(
        RecentRunSummary(
            overall_score=round(rng.uniform(94.0, 100.0), 1),
            all_scenarios_passed=True,
            response_time_ms=rng.randint(80, 240),
            lighthouse_performance=rng.randint(90, 99),
        )
        for _ in range(count)
    )


def passing_steps(
    rng: random.Random, flow: tuple[str, str, str, str, str] = FLOWS[0]
) -> tuple[ScenarioStepResult, ...]:
    _, path, fill_target, click_target, _ = flow
    return (
        ScenarioStepResult(1, "navigate", f"{SERVICE_URL}{path}", "PASSED", None),
        ScenarioStepResult(2, "fill", fill_target, "PASSED", None),
        ScenarioStepResult(3, "click", click_target, "PASSED", None),
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
    _, path, fill_target, click_target, _ = FLOWS[index % 4]
    steps = (
        ScenarioStepResult(1, "navigate", f"{SERVICE_URL}{path}", "FAILED", failure),
        ScenarioStepResult(2, "fill", fill_target, "SKIPPED", None),
        ScenarioStepResult(3, "click", click_target, "SKIPPED", None),
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
    # 실제 스캐너 의미론(availability.py): httpx가 기본 verify=True라 무효
    # 인증서는 TLS 핸드셰이크에서 실패한다 — 가용성 검사도 함께 죽고
    # Lighthouse·시나리오도 진행 불가. 판별 증거는 별도 핸드셰이크로 검증
    # 실패 후에도 인증서를 읽어내는 SSL 검사기의 ssl_valid=False(+사유)다.
    # (다운은 TCP 자체가 안 되므로 ssl_valid=None)
    days = rng.randint(1, 30)
    flavor = index % 3
    if flavor == 0:
        ssl_failure = f"certificate expired {days} days ago"
        navigate_error = "net::ERR_CERT_DATE_INVALID"
    elif flavor == 1:
        ssl_failure = "self-signed certificate in chain"
        navigate_error = "net::ERR_CERT_AUTHORITY_INVALID"
    else:
        ssl_failure = "hostname mismatch: certificate is not valid for myservice.example"
        navigate_error = "net::ERR_CERT_COMMON_NAME_INVALID"
    _, path, fill_target, click_target, _ = FLOWS[index % 4]
    steps = (
        ScenarioStepResult(1, "navigate", f"{SERVICE_URL}{path}", "FAILED", navigate_error),
        ScenarioStepResult(2, "fill", fill_target, "SKIPPED", None),
        ScenarioStepResult(3, "click", click_target, "SKIPPED", None),
    )
    fixtures = ToolFixtures(
        check_run=CheckRunSnapshot(
            overall_score=round(rng.uniform(5.0, 25.0), 1),
            grade="F",
            deployment_risk="RISK",
            gate_reason=f"SSL certificate is invalid: {ssl_failure}",
            availability_ok=False,
            availability_failure="Service request failed.",
            response_time_ms=None,
            response_time_threshold_ms=DEFAULT_THRESHOLD_MS,
            ssl_valid=False,
            ssl_failure=ssl_failure,
            lighthouse_performance=None,
            trigger_source="scheduled",
            deploy_ref=None,
        ),
        scenario_results=steps,
        artifacts=ArtifactsSnapshot(network_failures=(navigate_error,)),
        baseline=BaselineComparison(round(rng.uniform(-90.0, -60.0), 1), None, None),
        recent_runs=healthy_recent_runs(rng),
        project_config=default_config(),
        recheck=RecheckResult(reproduced=True, overall_score=round(rng.uniform(5.0, 25.0), 1)),
    )
    return EvalCase(
        f"ssl_invalid-{index:02d}", RootCause.SSL_INVALID, f"SSL 무효({ssl_failure})", fixtures
    )


def build_server_slow(rng: random.Random, index: int) -> EvalCase:
    multiplier = rng.uniform(2.2, 6.0)
    response_ms = int(DEFAULT_THRESHOLD_MS * multiplier)
    # 경계 사례(약 1/3): 지연 때문에 wait 스텝 하나가 타임아웃으로 실패
    slow_breaks_step = index % 3 == 0
    flow = FLOWS[index % 4]
    steps: tuple[ScenarioStepResult, ...]
    if slow_breaks_step:
        _, path, _, click_target, _ = flow
        steps = (
            ScenarioStepResult(1, "navigate", f"{SERVICE_URL}{path}", "PASSED", None),
            ScenarioStepResult(2, "wait", None, "FAILED", "timeout waiting for selector"),
            ScenarioStepResult(3, "click", click_target, "SKIPPED", None),
        )
    else:
        steps = passing_steps(rng, flow)
    creeping = tuple(
        RecentRunSummary(
            overall_score=round(rng.uniform(88.0, 97.0), 1),
            all_scenarios_passed=True,
            response_time_ms=int(DEFAULT_THRESHOLD_MS * (1.0 + 0.35 * offset)),
            lighthouse_performance=rng.randint(84, 95),
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
    # 변형(약 1/3): 점진 하락 — 추이에서 이미 성능이 미끄러지는 중이었다.
    # get_recent_runs로 "언제부터 나빠졌나"가 답 가능해야 한다.
    gradual = index % 3 == 2
    if gradual:
        recents = tuple(
            RecentRunSummary(
                overall_score=round(rng.uniform(90.0, 97.0), 1),
                all_scenarios_passed=True,
                response_time_ms=rng.randint(90, 240),
                lighthouse_performance=min(99, performance + boost),
            )
            for boost in (4, 8, 13, 18)
        )
    else:
        recents = healthy_recent_runs(rng)
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
        scenario_results=passing_steps(rng, FLOWS[index % 4]),
        artifacts=ArtifactsSnapshot(),
        baseline=BaselineComparison(
            round(rng.uniform(-18.0, -6.0), 1), -drop, rng.randint(-30, 30)
        ),
        recent_runs=recents,
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
    _, path, fill_target, click_target, assert_text = FLOWS[index % 4]
    broken_step = rng.choice(
        [
            (2, "fill", fill_target, f'no element matches selector "{fill_target}"'),
            (3, "click", click_target, "element is not clickable"),
            (4, "assert_text_exists", None, f'expected text "{assert_text}" not found'),
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
            (1, "navigate", f"{SERVICE_URL}{path}"),
            (2, "fill", fill_target),
            (3, "click", click_target),
            (4, "assert_text_exists", None),
        )
    )
    console_error = rng.choice(
        [
            "TypeError: cannot read properties of undefined",
            "ReferenceError: initForm is not defined",
            "Uncaught (in promise) SyntaxError: Unexpected token '<'",
        ]
    )
    network_failure = rng.choice(
        ["POST /api/session 500", "POST /api/orders 500", "GET /api/search 502"]
    )
    # 경계 사례(약 1/3): 콘솔 에러 없이 요소만 깨진 조용한 파손
    silent = index % 3 == 2
    artifacts = ArtifactsSnapshot(
        console_errors=() if silent else (console_error,),
        network_failures=() if silent or index % 2 == 0 else (network_failure,),
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
    flow_name, path, fill_target, click_target, _ = FLOWS[index % 4]
    moved_to = f"{SERVICE_URL}" + rng.choice([f"{path}/v2", f"/app{path}"])
    old_target = f"{SERVICE_URL}{path}"
    fill_error = f'no element matches selector "{fill_target}"'
    with_redirect = index % 5 != 4  # 일부는 리다이렉트 흔적 없이(더 어려운 케이스)
    steps = (
        ScenarioStepResult(1, "navigate", old_target, "PASSED", None),
        ScenarioStepResult(2, "fill", fill_target, "FAILED", fill_error),
        ScenarioStepResult(3, "click", click_target, "SKIPPED", None),
    )
    fixtures = ToolFixtures(
        check_run=CheckRunSnapshot(
            overall_score=round(rng.uniform(50.0, 68.0), 1),
            grade="F",
            deployment_risk="RISK",
            gate_reason=fill_error,
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
            relocation_hint=(
                f"navigate가 {moved_to}로 리다이렉트됨 — 새 페이지는 정상, 셀렉터만 불일치"
                if with_redirect
                else f"기존 페이지 정상 렌더 — {flow_name} 진입점이 {moved_to} 링크로 이동한 흔적"
            ),
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
    flavor = ("availability-blip", "timeout-blip", "lighthouse-dip")[index % 3]
    flow = FLOWS[index % 4]
    steps = passing_steps(rng, flow)
    artifacts = ArtifactsSnapshot()
    baseline = BaselineComparison(
        round(rng.uniform(-20.0, -8.0), 1), rng.randint(-20, 0), rng.randint(0, 900)
    )
    if flavor == "availability-blip":
        # 운영에서 가장 흔한 노이즈: 일시적 연결 실패. 겉모습은 다운과
        # 완전히 같고, 재검사 미재현만이 가른다 — "다운 확정 전 재검사"
        # 라우팅 규칙이 존재해야 하는 이유.
        failure = rng.choice(["connect timeout", "connection refused"])
        check = CheckRunSnapshot(
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
            trigger_source="scheduled",
            deploy_ref=None,
        )
        _, path, fill_target, click_target, _ = flow
        steps = (
            ScenarioStepResult(1, "navigate", f"{SERVICE_URL}{path}", "FAILED", failure),
            ScenarioStepResult(2, "fill", fill_target, "SKIPPED", None),
            ScenarioStepResult(3, "click", click_target, "SKIPPED", None),
        )
        artifacts = ArtifactsSnapshot(network_failures=(failure,))
        baseline = BaselineComparison(None, None, None)
        title = "일시적 연결 실패 — 재검사 시 정상"
    elif flavor == "timeout-blip":
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
        scenario_results=steps,
        artifacts=artifacts,
        baseline=baseline,
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
                RecentRunSummary(97.0, True, 150, 99),
                RecentRunSummary(99.0, True, 140, 99),
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
                # 다운사이징 직전까지 성능 99 유지 — 급락 시점이 추이로 보인다
                RecentRunSummary(97.0, True, 155, 99),
                RecentRunSummary(97.0, True, 148, 99),
                RecentRunSummary(99.0, True, 150, 99),
                RecentRunSummary(99.0, True, 152, 99),
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
                # 실제 진단 근거 그대로: 새 홈은 멀쩡히 렌더됐고 폼만 이사했다.
                relocation_hint=(
                    "새 홈이 정상 렌더 — 로그인 폼 대신 /login으로 가는 로그인 CTA 존재"
                ),
            ),
            baseline=BaselineComparison(-38.0, 2, -10),
            recent_runs=(
                RecentRunSummary(97.0, True, 130, 99),
                RecentRunSummary(97.0, True, 145, 99),
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
    """전체 평가셋 175건 — 유형당 25건(수제 케이스는 해당 유형 수에 포함)."""
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
