"""에이전트 루프 — 직접 구현(프레임워크 금지).

역할 분리: "다음에 무엇을 볼지·언제 결론낼지"는 Policy가 정하고, 루프는
규율만 강제한다 — 스텝 상한, 허용 도구 밖 호출 거절, 재검사 멱등(관찰
캐시), 결론 필수. LLM 정책(후속 주차)이 들어와도 루프는 그대로다.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from aim_worker.agent.cases import ToolFixtures
from aim_worker.agent.root_causes import RootCause
from aim_worker.agent.toolbox import TOOL_DISPATCH, FixturesToolbox, Toolbox
from aim_worker.agent.trace import InvestigationTrace, ToolCall, summarize_result

MAX_STEPS = 12


@dataclass(frozen=True)
class CallTool:
    """다음 행동: 도구 하나를 호출한다."""

    tool: str


@dataclass(frozen=True)
class Conclude:
    """다음 행동: 조사를 끝내고 결론을 낸다."""

    root_cause: RootCause
    summary: str
    recommendation: str


AgentAction = CallTool | Conclude

# Policy가 받는 관찰: 지금까지 호출한 도구 이름 → 응답. 읽기 전용이라
# 정책이 관찰을 조작해 루프 규율을 우회할 수 없다.
Observations = MappingProxyType[str, object]


class Policy(Protocol):
    """조사 정책 계약 — 관찰을 보고 다음 행동 하나를 정한다."""

    def decide(self, observations: Observations) -> AgentAction: ...


@dataclass(frozen=True)
class ToolRefusal:
    """미허용 도구 호출에 대한 거절 관찰 — 정책이 이걸 보고 경로를 바꾼다."""

    tool: str
    reason: str


class StepLimitExceeded(Exception):
    """스텝 상한까지 결론을 내지 못했다."""


class InvestigationLoop:
    def __init__(self, policy: Policy, toolbox: Toolbox, max_steps: int = MAX_STEPS) -> None:
        self._policy = policy
        self._toolbox = toolbox
        self._max_steps = max_steps

    def run(self, case_ref: str | None = None) -> InvestigationTrace:
        observations: dict[str, object] = {}
        tool_calls: list[ToolCall] = []
        violations: list[str] = []

        for step in range(1, self._max_steps + 1):
            action = self._policy.decide(MappingProxyType(observations))
            if isinstance(action, Conclude):
                return self._close(case_ref, tool_calls, observations, violations, action)

            dispatch = TOOL_DISPATCH.get(action.tool)
            if dispatch is None:
                # 미허용 도구는 크래시가 아니라 "기록 + 거절 관찰"이다 —
                # LLM이 도구명을 환각해도 조사는 계속되고, 시도 자체는
                # 위반으로 남아 "무단 변경 시도 0건" 지표의 근거가 된다.
                violations.append(action.tool)
                observations.setdefault(
                    action.tool, ToolRefusal(tool=action.tool, reason="허용된 조사 도구가 아님")
                )
                tool_calls.append(ToolCall(step, action.tool, "거절: 허용된 조사 도구가 아님"))
                continue
            # 같은 도구 재호출은 캐시를 돌려준다 — 특히 trigger_recheck가
            # 조사당 1회를 넘지 못하는 것은 이 멱등성으로 보장된다.
            if action.tool in observations:
                result = observations[action.tool]
            else:
                result = dispatch(self._toolbox)
                observations[action.tool] = result
            tool_calls.append(ToolCall(step, action.tool, summarize_result(result)))

        # 마지막 스텝까지 도구만 불렀다면 결론 기회를 한 번 더 준다 —
        # 그래도 결론이 아니면 정책 결함이므로 실패로 처리한다.
        action = self._policy.decide(MappingProxyType(observations))
        if isinstance(action, Conclude):
            return self._close(case_ref, tool_calls, observations, violations, action)
        raise StepLimitExceeded(f"{self._max_steps} steps used without a conclusion")

    def _close(
        self,
        case_ref: str | None,
        tool_calls: list[ToolCall],
        observations: dict[str, object],
        violations: list[str],
        action: Conclude,
    ) -> InvestigationTrace:
        return InvestigationTrace(
            case_ref=case_ref,
            tool_calls=tuple(tool_calls),
            root_cause=action.root_cause,
            summary=action.summary,
            recommendation=action.recommendation,
            recheck_used="trigger_recheck" in observations,
            violations=tuple(violations),
        )


class AgentInvestigator:
    """루프를 evaluate.Investigator 형태로 감싸는 어댑터.

    케이스마다 새 정책 인스턴스를 만들어(상태 오염 방지) fixtures 도구
    상자 위에서 루프를 돌리고 분류만 돌려준다 — W1 채점기를 그대로 쓴다.
    """

    def __init__(self, policy_factory: "PolicyFactory") -> None:
        self._policy_factory = policy_factory

    def investigate_with_trace(
        self, fixtures: ToolFixtures, case_ref: str | None = None
    ) -> InvestigationTrace:
        """분류뿐 아니라 trace(도구 체인·재검사·위반)까지 필요할 때 —
        W3의 비용·위반 리포트가 이 경로로 수집한다."""
        loop = InvestigationLoop(self._policy_factory(), FixturesToolbox(fixtures))
        return loop.run(case_ref)

    def investigate(self, fixtures: ToolFixtures) -> RootCause:
        return self.investigate_with_trace(fixtures).root_cause


class PolicyFactory(Protocol):
    def __call__(self) -> Policy: ...
