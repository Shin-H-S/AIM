from aim_worker.agent.dataset import generate_cases
from aim_worker.agent.evaluate import evaluate
from aim_worker.agent.llm_policy import (
    SYSTEM_PROMPT,
    Judge,
    JudgeCall,
    LlmPolicy,
    LlmVerdict,
)
from aim_worker.agent.loop import AgentInvestigator, InvestigationLoop
from aim_worker.agent.policies import RouterPolicy, RulePolicy
from aim_worker.agent.root_causes import RootCause
from aim_worker.agent.toolbox import FixturesToolbox


def a_call(model: str) -> JudgeCall:
    return JudgeCall(model=model, input_tokens=1200, output_tokens=90, latency_ms=800)


class FakeJudge:
    """정해진 평결을 순서대로 내놓고 (model, system, prompt)를 기록한다."""

    def __init__(self, verdicts: list[LlmVerdict]) -> None:
        self._verdicts = list(verdicts)
        self.requests: list[tuple[str, str, str]] = []

    def judge(self, model: str, system: str, prompt: str) -> tuple[LlmVerdict, JudgeCall]:
        self.requests.append((model, system, prompt))
        return self._verdicts.pop(0), a_call(model)


class ExplodingJudge:
    """항상 실패하는 판별기 — LLM 장애 시뮬레이션."""

    def judge(self, model: str, system: str, prompt: str) -> tuple[LlmVerdict, JudgeCall]:
        raise RuntimeError("API unavailable")


class EvidenceReadingJudge:
    """프롬프트 텍스트만 읽고 판별 — 증거 카드가 판별 특징을 온전히
    싣고 있음을 증명하는 시험용 판별기(W3 LLM이 할 일의 하한)."""

    def judge(self, model: str, system: str, prompt: str) -> tuple[LlmVerdict, JudgeCall]:
        if "이동 흔적: " in prompt:
            cause = "scenario_stale"
        elif "timeout waiting for selector" in prompt:
            cause = "server_slow"
        else:
            cause = "ui_regression"
        verdict = LlmVerdict(
            root_cause=cause,
            confidence="high",
            summary="증거 카드 판독",
            recommendation="조치",
        )
        return verdict, a_call(model)


def stale_verdict(confidence: str = "high") -> LlmVerdict:
    return LlmVerdict(
        root_cause="scenario_stale",
        confidence=confidence,
        summary="이동 흔적 명확",
        recommendation="시나리오 갱신",
    )


def case_by_id(case_id: str):  # type: ignore[no-untyped-def]
    return next(case for case in generate_cases() if case.case_id == case_id)


def run_case(case_id: str, policy: LlmPolicy):  # type: ignore[no-untyped-def]
    case = case_by_id(case_id)
    loop = InvestigationLoop(
        RouterPolicy(policy), FixturesToolbox(case.fixtures), fallback_policy=RulePolicy()
    )
    return loop.run(case.case_id)


def test_prompt_carries_evidence_cards_and_g2_bias() -> None:
    """시스템에는 '애매하면 파손' 규칙이, 프롬프트에는 렌더된 증거 카드가 실린다."""
    judge = FakeJudge([stale_verdict()])
    trace = run_case("curated-login-moved-stale", LlmPolicy(judge))

    assert trace.root_cause == RootCause.SCENARIO_STALE
    model, system, prompt = judge.requests[0]
    assert model == "claude-haiku-4-5"
    assert "애매하면 ui_regression" in system
    assert system == SYSTEM_PROMPT
    assert "[get_check_run]" in prompt
    assert "[get_artifacts]" in prompt
    assert "이동 흔적: " in prompt  # relocation_hint가 카드로 실렸다
    assert "게이트 사유" in prompt


def test_generator_records_llm_model_and_confidence() -> None:
    trace = run_case("curated-login-moved-stale", LlmPolicy(FakeJudge([stale_verdict()])))

    assert trace.generator == "llm:claude-haiku-4-5"
    assert trace.confidence == "high"
    # 라우터가 check_run·recheck·scenario를 모았고, LLM 정책은 artifacts만 추가
    assert [call.tool for call in trace.tool_calls] == [
        "get_check_run",
        "trigger_recheck",
        "get_scenario_results",
        "get_artifacts",
    ]


def test_low_confidence_escalates_once() -> None:
    """저신뢰면 상위 모델로 1회 재판별 — generator에 최종 모델이 남는다."""
    judge = FakeJudge([stale_verdict(confidence="low"), stale_verdict(confidence="high")])
    policy = LlmPolicy(judge, model="claude-haiku-4-5", escalation_model="claude-sonnet-5")

    trace = run_case("curated-login-moved-stale", policy)

    assert [request[0] for request in judge.requests] == ["claude-haiku-4-5", "claude-sonnet-5"]
    assert trace.generator == "llm:claude-sonnet-5"
    assert len(policy.calls) == 2
    assert policy.calls[1].model == "claude-sonnet-5"


def test_no_escalation_when_disabled() -> None:
    judge = FakeJudge([stale_verdict(confidence="low")])
    policy = LlmPolicy(judge, escalation_model=None)

    trace = run_case("curated-login-moved-stale", policy)

    assert len(policy.calls) == 1
    assert trace.confidence == "low"


def test_judge_failure_falls_back_to_rule(monkeypatch: object) -> None:
    """판별기가 죽어도 조사는 규칙 폴백으로 종결된다 — G4."""
    trace = run_case("curated-login-moved-stale", LlmPolicy(ExplodingJudge()))

    assert trace.generator == "rule-fallback"
    # 규칙은 리다이렉트 없는 스테일을 ui로 판정한다(의도된 빈틈)
    assert trace.root_cause == RootCause.UI_REGRESSION


def test_router_llm_with_prompt_reading_judge_hits_ceiling() -> None:
    """프롬프트 텍스트만 읽는 판별기로 175건 만점 — 증거 카드가 판별
    특징을 온전히 실어 나른다는 증명이자, 실 LLM의 도달 가능 상한."""
    cases = generate_cases()

    def factory() -> RouterPolicy:
        return RouterPolicy(LlmPolicy(EvidenceReadingJudge()))

    report = evaluate(AgentInvestigator(factory, fallback_factory=RulePolicy), cases)

    assert report.accuracy == 1.0
    assert report.dangerous_misclassified_case_ids == ()


def _unused_protocol_check(judge: Judge) -> Judge:
    return judge
