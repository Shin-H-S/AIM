"""조사 도구 상자 — READ 6종 + ACT 1종(trigger_recheck).

에이전트가 세상을 보는 유일한 창이다. 설정·베이스라인·시나리오를 바꾸는
도구는 아예 존재하지 않는다 — "무단 변경 0건"은 프롬프트가 아니라 도구
표면에서 강제한다.

W2의 평가 루프는 FixturesToolbox(평가셋 fixtures 재생)를 물리고, 운영
배선은 같은 Protocol을 DB 조회로 구현한다(후속 주차). 도구 이름·응답
스키마는 cases.py의 스냅샷 타입이 규정한다.
"""

from collections.abc import Callable
from typing import Protocol

from aim_worker.agent.cases import (
    ArtifactsSnapshot,
    BaselineComparison,
    CheckRunSnapshot,
    ProjectConfigSnapshot,
    RecentRunSummary,
    RecheckResult,
    ScenarioStepResult,
    ToolFixtures,
)


class Toolbox(Protocol):
    """조사 도구 계약 — 에이전트 루프는 이 표면만 안다."""

    def get_check_run(self) -> CheckRunSnapshot: ...

    def get_scenario_results(self) -> tuple[ScenarioStepResult, ...]: ...

    def get_artifacts(self) -> ArtifactsSnapshot: ...

    def compare_with_baseline(self) -> BaselineComparison: ...

    def get_recent_runs(self) -> tuple[RecentRunSummary, ...]: ...

    def get_project_config(self) -> ProjectConfigSnapshot: ...

    def trigger_recheck(self) -> RecheckResult: ...


class FixturesToolbox:
    """평가 케이스의 fixtures를 그대로 재생하는 도구 상자."""

    def __init__(self, fixtures: ToolFixtures) -> None:
        self._fixtures = fixtures

    def get_check_run(self) -> CheckRunSnapshot:
        return self._fixtures.check_run

    def get_scenario_results(self) -> tuple[ScenarioStepResult, ...]:
        return self._fixtures.scenario_results

    def get_artifacts(self) -> ArtifactsSnapshot:
        return self._fixtures.artifacts

    def compare_with_baseline(self) -> BaselineComparison:
        return self._fixtures.baseline

    def get_recent_runs(self) -> tuple[RecentRunSummary, ...]:
        return self._fixtures.recent_runs

    def get_project_config(self) -> ProjectConfigSnapshot:
        return self._fixtures.project_config

    def trigger_recheck(self) -> RecheckResult:
        return self._fixtures.recheck


# 이름 → 호출 디스패치. 루프는 이 표에 없는 도구 호출을 거절한다.
TOOL_DISPATCH: dict[str, Callable[[Toolbox], object]] = {
    "get_check_run": lambda toolbox: toolbox.get_check_run(),
    "get_scenario_results": lambda toolbox: toolbox.get_scenario_results(),
    "get_artifacts": lambda toolbox: toolbox.get_artifacts(),
    "compare_with_baseline": lambda toolbox: toolbox.compare_with_baseline(),
    "get_recent_runs": lambda toolbox: toolbox.get_recent_runs(),
    "get_project_config": lambda toolbox: toolbox.get_project_config(),
    "trigger_recheck": lambda toolbox: toolbox.trigger_recheck(),
}

TOOL_NAMES: tuple[str, ...] = tuple(TOOL_DISPATCH)
RECHECK_TOOL = "trigger_recheck"
