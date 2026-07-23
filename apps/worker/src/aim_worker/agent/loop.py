"""에이전트 루프 — 직접 구현(프레임워크 금지).

역할 분리: "다음에 무엇을 볼지·언제 결론낼지"는 Policy가 정하고, 루프는
규율만 강제한다 — 스텝 상한, 허용 도구 밖 호출 거절, 재검사 멱등(관찰
캐시), 결론 필수. LLM 정책(후속 주차)이 들어와도 루프는 그대로다.

G4(조사는 절대 실패하지 않는다): fallback_policy를 물리면 주 정책이
예외를 던지거나 상한까지 결론을 못 내도 결정론 정책이 이어받아 종결하고,
trace.generator에 누가 결론냈는지 남는다.
"""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from aim_worker.agent.cases import ToolFixtures
from aim_worker.agent.render import render_observation
from aim_worker.agent.root_causes import RootCause
from aim_worker.agent.toolbox import RECHECK_TOOL, TOOL_DISPATCH, FixturesToolbox, Toolbox
from aim_worker.agent.trace import InvestigationTrace, ToolCall, clip_summary

MAX_STEPS = 12
# 폴백 정책에게 주는 추가 스텝 — 규칙 정책의 최악 경로(check_run·recheck·
# scenario·artifacts)가 4콜이므로 4면 항상 결론에 닿는다.
FALLBACK_EXTRA_STEPS = 4


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
    # high | medium | low — 저신뢰 시 상위 모델 에스컬레이션(W3 라우팅)의
    # 입력. 채점은 여전히 root_cause만 본다.
    confidence: str = "high"


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


def policy_name(policy: Policy) -> str:
    """generator 라벨 — 정책이 name을 선언하면 그것을, 아니면 클래스명."""
    name = getattr(policy, "name", None)
    return name if isinstance(name, str) else type(policy).__name__


class InvestigationLoop:
    def __init__(
        self,
        policy: Policy,
        toolbox: Toolbox,
        max_steps: int = MAX_STEPS,
        fallback_policy: Policy | None = None,
    ) -> None:
        self._policy = policy
        self._toolbox = toolbox
        self._max_steps = max_steps
        self._fallback_policy = fallback_policy

    def run(self, case_ref: str | None = None) -> InvestigationTrace:
        observations: dict[str, object] = {}
        tool_calls: list[ToolCall] = []
        violations: list[str] = []

        conclusion: Conclude | None
        try:
            conclusion = self._drive(
                self._policy, self._max_steps, observations, tool_calls, violations
            )
        except Exception:
            # 주 정책의 어떤 실패(LLM API 예외, 도구 예외)도 조사를 죽이지
            # 못한다 — 폴백이 있으면 결정론 정책으로 강등해 끝까지 간다(G4).
            if self._fallback_policy is None:
                raise
            conclusion = None

        if conclusion is not None:
            return self._close(
                case_ref,
                tool_calls,
                observations,
                violations,
                conclusion,
                generator=policy_name(self._policy),
            )

        if self._fallback_policy is None:
            raise StepLimitExceeded(f"{self._max_steps} steps used without a conclusion")
        conclusion = self._drive(
            self._fallback_policy, FALLBACK_EXTRA_STEPS, observations, tool_calls, violations
        )
        if conclusion is None:
            raise StepLimitExceeded("fallback policy did not conclude")
        return self._close(
            case_ref,
            tool_calls,
            observations,
            violations,
            conclusion,
            generator=f"{policy_name(self._fallback_policy)}-fallback",
        )

    def _drive(
        self,
        policy: Policy,
        step_budget: int,
        observations: dict[str, object],
        tool_calls: list[ToolCall],
        violations: list[str],
    ) -> Conclude | None:
        """정책을 예산만큼 굴린다 — 결론이 나면 그것을, 소진하면 None."""
        for _ in range(step_budget):
            action = policy.decide(MappingProxyType(observations))
            if isinstance(action, Conclude):
                return action
            self._execute(action, observations, tool_calls, violations)
        # 예산 소진 — 결론 기회를 한 번 더 준다(도구 호출은 불가).
        action = policy.decide(MappingProxyType(observations))
        return action if isinstance(action, Conclude) else None

    def _execute(
        self,
        action: CallTool,
        observations: dict[str, object],
        tool_calls: list[ToolCall],
        violations: list[str],
    ) -> None:
        step = len(tool_calls) + 1
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
            return
        # 같은 도구 재호출은 캐시를 돌려준다 — 특히 trigger_recheck가
        # 조사당 1회를 넘지 못하는 것은 이 멱등성으로 보장된다.
        if action.tool in observations:
            result = observations[action.tool]
        else:
            result = dispatch(self._toolbox)
            observations[action.tool] = result
        tool_calls.append(
            ToolCall(step, action.tool, clip_summary(render_observation(action.tool, result)))
        )

    def _close(
        self,
        case_ref: str | None,
        tool_calls: list[ToolCall],
        observations: dict[str, object],
        violations: list[str],
        action: Conclude,
        generator: str,
    ) -> InvestigationTrace:
        return InvestigationTrace(
            case_ref=case_ref,
            tool_calls=tuple(tool_calls),
            root_cause=action.root_cause,
            summary=action.summary,
            recommendation=action.recommendation,
            confidence=action.confidence,
            recheck_used=RECHECK_TOOL in observations,
            generator=generator,
            violations=tuple(violations),
        )


class AgentInvestigator:
    """루프를 evaluate.Investigator 형태로 감싸는 어댑터.

    케이스마다 새 정책 인스턴스를 만들어(상태 오염 방지) fixtures 도구
    상자 위에서 루프를 돌리고 분류만 돌려준다 — W1 채점기를 그대로 쓴다.
    fallback_factory를 주면 케이스마다 폴백 정책도 새로 물린다(G4).
    """

    def __init__(
        self,
        policy_factory: "PolicyFactory",
        fallback_factory: "PolicyFactory | None" = None,
    ) -> None:
        self._policy_factory = policy_factory
        self._fallback_factory = fallback_factory

    def investigate_with_trace(
        self, fixtures: ToolFixtures, case_ref: str | None = None
    ) -> InvestigationTrace:
        """분류뿐 아니라 trace(도구 체인·재검사·위반)까지 필요할 때 —
        W3의 비용·위반 리포트가 이 경로로 수집한다."""
        fallback = self._fallback_factory() if self._fallback_factory is not None else None
        loop = InvestigationLoop(
            self._policy_factory(), FixturesToolbox(fixtures), fallback_policy=fallback
        )
        return loop.run(case_ref)

    def investigate(self, fixtures: ToolFixtures) -> RootCause:
        return self.investigate_with_trace(fixtures).root_cause


class PolicyFactory(Protocol):
    def __call__(self) -> Policy: ...
