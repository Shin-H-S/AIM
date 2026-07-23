"""LLM 조사 정책 — 실패 스텝의 3자 판별(ui/stale/slow)을 Claude에게 맡긴다.

RouterPolicy의 위임 정책이다. 라우터가 확정 신호(평가셋 66%)를 걸러낸
뒤라 이 정책이 보는 것은 "스텝이 실패했고 강신호가 없는" 케이스뿐이고,
관찰은 이미 대부분 모여 있다 — 부족한 것(artifacts)만 결정적으로 요청한
뒤, 증거 카드를 한 번의 판별 호출에 담아 결론낸다.

안전·게이트 연결:
- G2: 시스템 프롬프트가 "애매하면 파손(ui_regression)"을 강제한다 —
  파손을 정상류로 오판하는 거짓 안심이 운영에서 가장 위험하다.
- G3: confidence=low면 상위 모델로 1회 에스컬레이션. 호출별 토큰·지연을
  JudgeCall로 남겨 비용 리포트의 원자료가 된다.
- G4: API 예외·파싱 실패는 그대로 던진다 — 루프의 결정론 폴백이 받는다.
"""

import time
from collections.abc import Callable
from typing import Literal, Protocol

from aim_api.config import Settings, get_settings
from anthropic import Anthropic
from pydantic import BaseModel

from aim_worker.agent.cases import ArtifactsSnapshot
from aim_worker.agent.loop import AgentAction, CallTool, Conclude, Observations, ToolRefusal
from aim_worker.agent.render import render_observation
from aim_worker.agent.root_causes import RootCause
from aim_worker.agent.toolbox import RECHECK_TOOL

SYSTEM_PROMPT = """당신은 웹서비스 검사 실패의 원인을 판별하는 조사관입니다.
시나리오 스텝이 실패한 검사의 증거 카드를 읽고, 원인을 셋 중 하나로 판별하세요.

- ui_regression: 서비스가 실제로 깨졌다. 기대 요소가 파손·소실됐고 이동 흔적이 없다.
- scenario_stale: 서비스는 정상인데 테스트 정의가 낡았다. 기대 요소가 다른 곳으로
  '이동한 흔적'(리다이렉트 감지, 대체 진입점 발견)이 증거에 명확히 있다.
- server_slow: 응답 지연이 스텝을 깨뜨렸다. 응답시간이 임계값을 크게(2배 이상)
  초과하고 스텝 실패가 타임아웃 계열이다.

판별 규칙(안전 우선):
1. 응답시간이 임계의 2배를 넘고 실패가 타임아웃 대기라면 server_slow.
2. 이동 흔적이 증거에 명확할 때만 scenario_stale로 판정한다.
3. 애매하면 ui_regression으로 판정한다 — 진짜 파손을 "테스트가 낡았다"로
   오판하면 개발자가 장애를 놓친다. 거짓 안심이 가장 위험한 오류다.

confidence는 증거가 확정적이면 "high", 판단이 갈릴 수 있으면 "low".
summary는 판별 근거 한 문장, recommendation은 조치 한 문장 — 모두 한국어로."""

# 증거 카드를 프롬프트에 싣는 순서 — 판별에 중요한 것부터.
EVIDENCE_ORDER: tuple[str, ...] = (
    "get_check_run",
    "get_scenario_results",
    "get_artifacts",
    "compare_with_baseline",
    "get_recent_runs",
    "get_project_config",
    RECHECK_TOOL,
)


class LlmVerdict(BaseModel):
    """판별 호출의 structured output 스키마."""

    root_cause: Literal["ui_regression", "scenario_stale", "server_slow"]
    confidence: Literal["high", "low"]
    summary: str
    recommendation: str


class JudgeCall(BaseModel):
    """판별 호출 1회의 실측 — G3 비용·지연 리포트의 원자료."""

    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class Judge(Protocol):
    """판별 실행기 계약 — 시험은 가짜로, 운영은 AnthropicJudge로."""

    def judge(self, model: str, system: str, prompt: str) -> tuple[LlmVerdict, JudgeCall]: ...


class LlmJudgeError(Exception):
    """판별 응답을 신뢰할 수 없다 — 루프 폴백(G4)으로 넘어간다."""


def build_evidence_prompt(observations: Observations) -> str:
    lines = ["실패 스텝 검사의 증거 카드:"]
    for tool in EVIDENCE_ORDER:
        result = observations.get(tool)
        if result is None or isinstance(result, ToolRefusal):
            continue
        lines.append(f"[{tool}] {render_observation(tool, result)}")
    lines.append("위 증거만으로 원인을 판별하라.")
    return "\n".join(lines)


class LlmPolicy:
    """증거 카드 기반 3자 판별 정책 (RouterPolicy의 위임 대상)."""

    def __init__(
        self,
        judge: Judge,
        model: str = "claude-haiku-4-5",
        escalation_model: str | None = "claude-sonnet-5",
    ) -> None:
        self._judge = judge
        self._model = model
        self._escalation_model = escalation_model
        self._model_used = model
        # 호출 실측(케이스당 1~2건) — 평가 러너가 케이스별로 수거한다.
        self.calls: list[JudgeCall] = []

    @property
    def name(self) -> str:
        return f"llm:{self._model_used}"

    def decide(self, observations: Observations) -> AgentAction:
        # 판별에 필수인 artifacts(이동 흔적·렌더 상태)가 없으면 먼저 수집 —
        # 결정적 스텝이라 LLM 왕복을 아낀다.
        if not isinstance(observations.get("get_artifacts"), ArtifactsSnapshot):
            return CallTool("get_artifacts")

        prompt = build_evidence_prompt(observations)
        verdict, call = self._judge.judge(self._model, SYSTEM_PROMPT, prompt)
        self.calls.append(call)
        self._model_used = self._model

        if verdict.confidence == "low" and self._escalation_model is not None:
            verdict, call = self._judge.judge(self._escalation_model, SYSTEM_PROMPT, prompt)
            self.calls.append(call)
            self._model_used = self._escalation_model

        return Conclude(
            root_cause=RootCause(verdict.root_cause),
            summary=verdict.summary,
            recommendation=verdict.recommendation,
            confidence=verdict.confidence,
        )


class AnthropicJudge:
    """Anthropic 호출 판별기 — AI 리포트와 동일한 parse+Pydantic 관례.

    thinking은 설정하지 않는다: Haiku 4.5는 적응형 사고 미지원이고,
    에스컬레이션 모델(Sonnet 5)은 생략 시 적응형이 기본이라 한 코드
    경로로 두 모델을 모두 감당한다.
    """

    def __init__(self, client: Anthropic) -> None:
        self._client = client

    def judge(self, model: str, system: str, prompt: str) -> tuple[LlmVerdict, JudgeCall]:
        started = time.perf_counter()
        response = self._client.messages.parse(
            model=model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=LlmVerdict,
        )
        verdict = response.parsed_output
        if verdict is None:
            raise LlmJudgeError("판별 응답에 파싱된 결과가 없음")
        call = JudgeCall(
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        return verdict, call


def build_llm_policy_factory(
    settings: Settings | None = None,
) -> Callable[[], LlmPolicy] | None:
    """운영·평가 공용 팩토리 — API 키가 없으면 None(호출부가 규칙 전용으로)."""
    runtime_settings = settings or get_settings()
    if not runtime_settings.anthropic_api_key:
        return None
    judge = AnthropicJudge(
        Anthropic(
            api_key=runtime_settings.anthropic_api_key,
            timeout=runtime_settings.ai_report_llm_timeout_seconds,
            max_retries=runtime_settings.ai_report_llm_max_retries,
        )
    )
    model = runtime_settings.aim_agent_model
    escalation_model = runtime_settings.aim_agent_escalation_model

    def factory() -> LlmPolicy:
        return LlmPolicy(judge, model=model, escalation_model=escalation_model)

    return factory
