"""결정적 조사 정책 — 규칙 베이스라인을 도구 루프 위에 올린 판.

W1의 RuleBaselineInvestigator와 같은 휴리스틱을 "도구를 불러 관찰을
모으는" 방식으로 재현한다. 목적 두 가지:
- 루프·도구 상자·trace가 끝까지 배선됐음을 평가셋 105건 전체로 증명
  (분류 결과가 W1 베이스라인과 완전히 일치해야 한다)
- LLM 정책(후속 주차)의 비용·정확도 비교 대상이 되는 결정적 바닥

베이스라인과 동일하게 relocation_hint는 읽지 않는다 — 그 빈틈을 넘는
것이 LLM 정책의 몫이다.
"""

from aim_worker.agent.cases import (
    ArtifactsSnapshot,
    BaselineComparison,
    CheckRunSnapshot,
    RecheckResult,
    ScenarioStepResult,
)
from aim_worker.agent.loop import (
    AgentAction,
    CallTool,
    Conclude,
    Observations,
    Policy,
    policy_name,
)
from aim_worker.agent.root_causes import RootCause
from aim_worker.agent.toolbox import RECHECK_TOOL

RECOMMENDED_ACTIONS: dict[RootCause, str] = {
    RootCause.SERVICE_DOWN: "서버·컨테이너 상태를 확인하고 재기동 후 재검사로 복구를 확인하세요.",
    RootCause.SSL_INVALID: "인증서를 갱신·교체하고 자동 갱신 경로를 점검하세요.",
    RootCause.SERVER_SLOW: "응답 지연이 지속됩니다 — 서버 리소스·쿼리를 점검하세요.",
    RootCause.FRONTEND_REGRESSION: "직전 배포의 프런트 번들 변경을 확인하고 회귀를 되돌리세요.",
    RootCause.UI_REGRESSION: "서비스가 실제로 깨졌습니다 — 직전 배포의 파손 요소를 수정하세요.",
    RootCause.SCENARIO_STALE: "서비스는 정상입니다 — 시나리오 정의를 새 URL·셀렉터로 갱신하세요.",
    RootCause.MEASUREMENT_NOISE: "조치가 필요 없습니다 — 재검사에서 재현되지 않은 일시 현상입니다.",
}


def conclude(cause: RootCause, evidence: str) -> Conclude:
    # summary는 사람이 읽는 근거 문장 하나 — 라벨은 알림 제목·UI 배지가
    # 이미 보여주므로 여기서 반복하지 않는다.
    return Conclude(
        root_cause=cause,
        summary=evidence,
        recommendation=RECOMMENDED_ACTIONS[cause],
    )


def _failed_step(observations: Observations) -> ScenarioStepResult | None:
    steps = observations.get("get_scenario_results")
    if not isinstance(steps, tuple):
        return None
    return next(
        (
            step
            for step in steps
            if isinstance(step, ScenarioStepResult) and step.status == "FAILED"
        ),
        None,
    )


def definitive_action(observations: Observations) -> AgentAction | None:
    """확정 분기 — 강한 신호만으로 결론 가능한 범위 (평가셋 실측 66%).

    판정 순서: SSL 무효 먼저(무효 인증서는 가용성 검사까지 죽이므로 더
    확정적 증거) → 가용성 실패는 재검사 재현 확인 후 다운/노이즈 →
    미재현 노이즈 → [실패 스텝이 있으면 None 반환: 판단 위임 필요] →
    응답 2x 지연 → 성능 델타 → 노이즈.
    """
    check = observations.get("get_check_run")
    if not isinstance(check, CheckRunSnapshot):
        return CallTool("get_check_run")
    if check.deployment_risk == "STABLE":
        # 건강 게이트: 시스템 스스로 '안정' 판정한 검사에는 조사할 이상
        # 징후가 없다 — 재검사·LLM 없이 즉시 종결한다(수동 조사 대비).
        return Conclude(
            root_cause=RootCause.MEASUREMENT_NOISE,
            summary=(
                f"이상 징후 없음 — 종합 {check.overall_score:.0f}점({check.grade})에 "
                "안정(STABLE) 판정입니다. 지표 변동은 정상 범위입니다."
            ),
            recommendation="조치가 필요 없습니다.",
        )
    if check.ssl_valid is False:
        return conclude(
            RootCause.SSL_INVALID,
            f"SSL 인증서가 유효하지 않습니다({check.ssl_failure}).",
        )

    recheck = observations.get(RECHECK_TOOL)
    if not check.availability_ok:
        if not isinstance(recheck, RecheckResult):
            return CallTool(RECHECK_TOOL)
        if recheck.reproduced:
            return conclude(
                RootCause.SERVICE_DOWN,
                f"서비스에 연결할 수 없고 재검사에서도 재현됐습니다({check.availability_failure}).",
            )
        return conclude(
            RootCause.MEASUREMENT_NOISE,
            f"가용성 실패가 재검사(점수 {recheck.overall_score:.0f})에서 재현되지 않았습니다"
            " — 일시적 연결 문제였습니다.",
        )

    if not isinstance(recheck, RecheckResult):
        return CallTool(RECHECK_TOOL)
    if not recheck.reproduced:
        return conclude(
            RootCause.MEASUREMENT_NOISE,
            f"재검사(점수 {recheck.overall_score:.0f})에서 재현되지 않았습니다"
            " — 일시적 변동입니다.",
        )

    steps = observations.get("get_scenario_results")
    if not isinstance(steps, tuple):
        return CallTool("get_scenario_results")
    if _failed_step(observations) is not None:
        return None  # 파손/스테일/지연 파손의 3자 판별 — 확정 불가, 위임

    if (
        check.response_time_ms is not None
        and check.response_time_ms > check.response_time_threshold_ms * 2
    ):
        return conclude(
            RootCause.SERVER_SLOW,
            f"응답 {check.response_time_ms}ms — 임계 {check.response_time_threshold_ms}ms의"
            " 2배를 넘는 지연이 지속됩니다.",
        )

    baseline = observations.get("compare_with_baseline")
    if not isinstance(baseline, BaselineComparison):
        return CallTool("compare_with_baseline")
    if baseline.performance_delta is not None and baseline.performance_delta <= -10:
        return conclude(
            RootCause.FRONTEND_REGRESSION,
            f"Lighthouse 성능이 기준 대비 {baseline.performance_delta} 하락했습니다.",
        )

    return conclude(
        RootCause.MEASUREMENT_NOISE,
        "강한 이상 신호가 없습니다 — 일시적 변동으로 판단합니다.",
    )


class RulePolicy:
    """강한 신호를 순서대로 확인하는 결정적 정책 (베이스라인의 도구 판).

    확정 분기(definitive_action) + 실패 스텝은 리다이렉트 유무만 보는
    단순 판별 — 경계 사례에서 틀리는 의도된 빈틈이다.
    """

    name = "rule"  # trace.generator 라벨 — 폴백으로 쓰이면 "rule-fallback"

    def decide(self, observations: Observations) -> AgentAction:
        action = definitive_action(observations)
        if action is not None:
            return action

        artifacts = observations.get("get_artifacts")
        if not isinstance(artifacts, ArtifactsSnapshot):
            return CallTool("get_artifacts")
        if artifacts.redirect_detected_to is not None:
            return conclude(
                RootCause.SCENARIO_STALE,
                "서비스는 정상이지만 시나리오가 옛 위치를 보고 있습니다 — navigate가 "
                f"{artifacts.redirect_detected_to}로 이동됐습니다.",
            )
        failed = _failed_step(observations)
        error = failed.error if failed is not None else "원인 미상"
        return conclude(
            RootCause.UI_REGRESSION,
            f"시나리오 스텝이 실제로 깨졌습니다 — {error}",
        )


class RouterPolicy:
    """rule-first 라우터 — 확정 신호는 규칙으로 즉시 결론(LLM 0콜),
    실패 스텝 케이스만 위임 정책(W3의 LLM)에게 3자 판별로 넘긴다.

    평가셋 실측: 확정 분기가 175건 중 116건(66%)을 전부 정답으로 처리하고,
    위임 대상은 실패 스텝 59건(ui 25·stale 25·slow 9)뿐이다. generator에는
    실제로 결론낸 쪽(rule 또는 위임 정책 이름)이 남는다.
    """

    def __init__(self, delegate: Policy) -> None:
        self._delegate = delegate
        self._concluded_by_delegate = False

    @property
    def name(self) -> str:
        if self._concluded_by_delegate:
            return policy_name(self._delegate)
        return "rule"

    def decide(self, observations: Observations) -> AgentAction:
        action = definitive_action(observations)
        if action is not None:
            return action
        delegated = self._delegate.decide(observations)
        if isinstance(delegated, Conclude):
            self._concluded_by_delegate = True
        return delegated
