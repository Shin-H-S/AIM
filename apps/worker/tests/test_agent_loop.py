import json
from collections import Counter

import pytest
from aim_worker.agent.cases import EvalCase, RecheckResult, ToolFixtures
from aim_worker.agent.dataset import generate_cases
from aim_worker.agent.evaluate import RuleBaselineInvestigator, evaluate
from aim_worker.agent.loop import (
    AgentAction,
    AgentInvestigator,
    CallTool,
    Conclude,
    InvestigationLoop,
    Observations,
    StepLimitExceeded,
    ToolRefusal,
)
from aim_worker.agent.policies import RulePolicy
from aim_worker.agent.root_causes import RootCause
from aim_worker.agent.toolbox import TOOL_NAMES, FixturesToolbox


def case_by_id(case_id: str) -> EvalCase:
    return next(case for case in generate_cases() if case.case_id == case_id)


class ScriptedPolicy:
    """정해진 행동을 순서대로 내놓는 시험용 정책."""

    def __init__(self, actions: list[AgentAction]) -> None:
        self._actions = list(actions)

    def decide(self, observations: Observations) -> AgentAction:
        return self._actions.pop(0)


class CountingToolbox(FixturesToolbox):
    """도구 실행 횟수를 세는 감시용 도구 상자."""

    def __init__(self, fixtures: ToolFixtures) -> None:
        super().__init__(fixtures)
        self.executions: Counter[str] = Counter()

    def trigger_recheck(self) -> RecheckResult:
        self.executions["trigger_recheck"] += 1
        return super().trigger_recheck()


def a_conclusion() -> Conclude:
    return Conclude(RootCause.MEASUREMENT_NOISE, "요약", "조치")


def test_fixtures_toolbox_replays_fixtures() -> None:
    case = case_by_id("curated-gcp-vm-stopped")
    toolbox = FixturesToolbox(case.fixtures)

    assert toolbox.get_check_run() is case.fixtures.check_run
    assert toolbox.get_artifacts() is case.fixtures.artifacts
    assert toolbox.trigger_recheck() is case.fixtures.recheck
    assert set(TOOL_NAMES) == {
        "get_check_run",
        "get_scenario_results",
        "get_artifacts",
        "compare_with_baseline",
        "get_recent_runs",
        "get_project_config",
        "trigger_recheck",
    }


def test_loop_records_trace_in_order() -> None:
    case = case_by_id("scenario_stale-00")  # 리다이렉트 흔적 있는 스테일
    loop = InvestigationLoop(RulePolicy(), FixturesToolbox(case.fixtures))

    trace = loop.run(case_ref=case.case_id)

    assert trace.case_ref == case.case_id
    assert [call.tool for call in trace.tool_calls] == [
        "get_check_run",
        "trigger_recheck",
        "get_scenario_results",
        "get_artifacts",
    ]
    assert [call.step for call in trace.tool_calls] == [1, 2, 3, 4]
    assert trace.root_cause == RootCause.SCENARIO_STALE
    assert trace.recheck_used is True
    assert trace.steps_used == 4


def test_conclusion_without_tools_is_allowed() -> None:
    case = case_by_id("service_down-00")
    loop = InvestigationLoop(ScriptedPolicy([a_conclusion()]), FixturesToolbox(case.fixtures))

    trace = loop.run()

    assert trace.steps_used == 0
    assert trace.recheck_used is False
    assert trace.tool_calls == ()


def test_repeated_recheck_is_idempotent() -> None:
    """재검사를 두 번 시도해도 실행은 1회 — 조사당 1회 규율은 캐시로 강제된다."""
    case = case_by_id("measurement_noise-00")
    toolbox = CountingToolbox(case.fixtures)
    policy = ScriptedPolicy(
        [CallTool("trigger_recheck"), CallTool("trigger_recheck"), a_conclusion()]
    )

    trace = InvestigationLoop(policy, toolbox).run()

    assert toolbox.executions["trigger_recheck"] == 1
    assert [call.tool for call in trace.tool_calls] == ["trigger_recheck", "trigger_recheck"]
    assert trace.recheck_used is True


def test_unauthorized_tool_is_refused_and_counted() -> None:
    """미허용 도구 시도는 크래시가 아니라 위반 기록 + 거절 관찰 — 조사는
    계속되고, 시도 횟수가 '무단 변경 시도 0건' 지표의 근거가 된다."""
    case = case_by_id("service_down-00")
    policy = ScriptedPolicy([CallTool("drop_database"), CallTool("drop_database"), a_conclusion()])

    trace = InvestigationLoop(policy, FixturesToolbox(case.fixtures)).run()

    assert trace.violations == ("drop_database", "drop_database")
    assert [call.tool for call in trace.tool_calls] == ["drop_database", "drop_database"]
    assert "거절" in trace.tool_calls[0].result_summary
    assert trace.root_cause == RootCause.MEASUREMENT_NOISE
    payload = json.loads(trace.to_json())
    assert payload["violation_count"] == 2


def test_policy_can_observe_refusal() -> None:
    """정책은 거절 관찰(ToolRefusal)을 보고 재시도 대신 경로를 바꿀 수 있다."""

    class ProbingPolicy:
        def decide(self, observations: Observations) -> AgentAction:
            if isinstance(observations.get("update_baseline"), ToolRefusal):
                return a_conclusion()
            return CallTool("update_baseline")

    case = case_by_id("service_down-00")
    trace = InvestigationLoop(ProbingPolicy(), FixturesToolbox(case.fixtures)).run()

    assert trace.violations == ("update_baseline",)
    assert trace.steps_used == 1


def test_step_limit_allows_final_conclusion() -> None:
    case = case_by_id("service_down-00")
    actions: list[AgentAction] = [CallTool("get_check_run")] * 12 + [a_conclusion()]
    trace = InvestigationLoop(ScriptedPolicy(actions), FixturesToolbox(case.fixtures)).run()

    assert trace.steps_used == 12


def test_step_limit_without_conclusion_fails() -> None:
    case = case_by_id("service_down-00")
    actions: list[AgentAction] = [CallTool("get_check_run")] * 13
    loop = InvestigationLoop(ScriptedPolicy(actions), FixturesToolbox(case.fixtures))

    with pytest.raises(StepLimitExceeded):
        loop.run()


def test_trace_serializes_to_json() -> None:
    case = case_by_id("curated-gcp-vm-stopped")
    trace = InvestigationLoop(RulePolicy(), FixturesToolbox(case.fixtures)).run(
        case_ref=case.case_id
    )

    payload = json.loads(trace.to_json())
    assert payload["case_ref"] == "curated-gcp-vm-stopped"
    assert payload["root_cause"] == "service_down"
    # 다운은 재검사 재현을 확인한 뒤에만 확정 — 2스텝
    assert payload["steps_used"] == 2
    assert [call["tool"] for call in payload["tool_calls"]] == [
        "get_check_run",
        "trigger_recheck",
    ]


def test_rule_policy_through_loop_matches_w1_baseline() -> None:
    """루프+도구 상자 위의 규칙 정책은 W1 베이스라인과 완전히 같은 분류를
    내야 한다 — 다르면 배선(도구·캐시·순서) 어딘가가 새고 있다는 뜻이다."""
    cases = generate_cases()

    loop_report = evaluate(AgentInvestigator(RulePolicy), cases)
    baseline_report = evaluate(RuleBaselineInvestigator(), cases)

    assert loop_report.accuracy == baseline_report.accuracy
    assert loop_report.misclassified_case_ids == baseline_report.misclassified_case_ids
    assert loop_report.confusion == baseline_report.confusion
