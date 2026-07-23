"""평가 케이스 스키마.

케이스 하나 = 에이전트의 READ 도구들이 돌려줄 조사 입력 스냅샷(fixtures) +
정답 라벨(root_cause). W2의 에이전트 루프는 실 DB 대신 이 fixtures를 물린
FakeToolbox 위에서 평가되고, 같은 스키마가 운영 도구의 응답 형태를 규정한다.

값 필드는 실제 도구 응답의 축약형이다 — 채점에 필요한 판별 신호를 보존하는
수준으로 유지하고, 운영 도구가 확장되면 여기에만 필드를 추가한다.
"""

from dataclasses import dataclass, field

from aim_worker.agent.root_causes import RootCause


@dataclass(frozen=True)
class CheckRunSnapshot:
    """get_check_run — 점수·게이트 요약."""

    overall_score: float
    grade: str
    deployment_risk: str
    gate_reason: str | None
    availability_ok: bool
    availability_failure: str | None  # 예: "connect timeout", "dns error"
    response_time_ms: int | None
    response_time_threshold_ms: int
    ssl_valid: bool | None  # None = 판단 불가(서비스 불달 등)
    ssl_failure: str | None
    lighthouse_performance: int | None
    trigger_source: str  # manual | scheduled | deploy
    deploy_ref: str | None


@dataclass(frozen=True)
class ScenarioStepResult:
    """get_scenario_results — 스텝 하나의 결과."""

    step_order: int
    action: str
    target: str | None
    status: str  # PASSED | FAILED | SKIPPED
    error: str | None


@dataclass(frozen=True)
class ArtifactsSnapshot:
    """get_artifacts — 실패 시 수집된 근거의 요약."""

    console_errors: tuple[str, ...] = ()
    network_failures: tuple[str, ...] = ()
    # 실패 지점 페이지가 정상 렌더링됐는지(스크린샷 판독 요약).
    # 시나리오 스테일 판별의 핵심 신호: 페이지는 멀쩡한데 기대 요소만 없다.
    failing_page_rendered_ok: bool | None = None
    # navigate 대상이 다른 곳으로 리다이렉트됐는지 (URL 구조 변경의 흔적).
    redirect_detected_to: str | None = None


@dataclass(frozen=True)
class BaselineComparison:
    """compare_with_baseline — 기준점 대비 델타."""

    overall_delta: float | None
    performance_delta: int | None
    response_time_delta_ms: int | None


@dataclass(frozen=True)
class RecentRunSummary:
    """get_recent_runs — 과거 실행 하나의 요약(최근 순)."""

    overall_score: float
    all_scenarios_passed: bool
    response_time_ms: int | None


@dataclass(frozen=True)
class ProjectConfigSnapshot:
    """get_project_config — 판별에 필요한 설정 발췌."""

    service_url: str
    scenario_targets: tuple[str, ...]  # navigate 스텝들이 가리키는 URL
    response_time_threshold_ms: int
    quality_score_threshold: int


@dataclass(frozen=True)
class RecheckResult:
    """trigger_recheck — 재검사 1회의 결과(멱등·조사당 1회)."""

    reproduced: bool  # 같은 실패가 다시 났는가
    overall_score: float


@dataclass(frozen=True)
class ToolFixtures:
    """케이스 하나에 물리는 도구 응답 전체."""

    check_run: CheckRunSnapshot
    scenario_results: tuple[ScenarioStepResult, ...]
    artifacts: ArtifactsSnapshot
    baseline: BaselineComparison
    recent_runs: tuple[RecentRunSummary, ...]
    project_config: ProjectConfigSnapshot
    recheck: RecheckResult


@dataclass(frozen=True)
class EvalCase:
    """평가 케이스 — 조사 입력 스냅샷 + 정답 라벨."""

    case_id: str
    root_cause: RootCause
    title: str
    fixtures: ToolFixtures
    # 실측 사고를 재현한 케이스인지 (합성 케이스와 구분해 리포트에 표기)
    curated: bool = field(default=False)
