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
from aim_worker.agent.loop import AgentAction, CallTool, Conclude, Observations
from aim_worker.agent.root_causes import ROOT_CAUSE_DESCRIPTIONS, RootCause
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
    return Conclude(
        root_cause=cause,
        summary=f"{ROOT_CAUSE_DESCRIPTIONS[cause]} — {evidence}",
        recommendation=RECOMMENDED_ACTIONS[cause],
    )


class RulePolicy:
    """강한 신호를 순서대로 확인하는 결정적 정책.

    판정 순서는 베이스라인과 동일: SSL 무효 먼저(무효 인증서는 가용성
    검사까지 죽이므로 더 확정적 증거), 가용성 실패는 재검사 재현을 확인한
    뒤에만 다운으로 확정(일시적 연결 실패 = 운영 최다 노이즈).
    """

    name = "rule"  # trace.generator 라벨 — 폴백으로 쓰이면 "rule-fallback"

    def decide(self, observations: Observations) -> AgentAction:
        check = observations.get("get_check_run")
        if not isinstance(check, CheckRunSnapshot):
            return CallTool("get_check_run")
        if check.ssl_valid is False:
            return conclude(RootCause.SSL_INVALID, f"인증서 검증 실패({check.ssl_failure})")

        recheck = observations.get(RECHECK_TOOL)
        if not check.availability_ok:
            if not isinstance(recheck, RecheckResult):
                return CallTool(RECHECK_TOOL)
            if recheck.reproduced:
                return conclude(
                    RootCause.SERVICE_DOWN,
                    f"가용성 실패 재현({check.availability_failure})",
                )
            return conclude(
                RootCause.MEASUREMENT_NOISE,
                f"가용성 실패가 재검사 미재현(점수 {recheck.overall_score})",
            )

        if not isinstance(recheck, RecheckResult):
            return CallTool(RECHECK_TOOL)
        if not recheck.reproduced:
            return conclude(
                RootCause.MEASUREMENT_NOISE, f"재검사 점수 {recheck.overall_score} — 재현 안 됨"
            )

        steps = observations.get("get_scenario_results")
        if not isinstance(steps, tuple):
            return CallTool("get_scenario_results")
        failed_step = next(
            (
                step
                for step in steps
                if isinstance(step, ScenarioStepResult) and step.status == "FAILED"
            ),
            None,
        )
        if failed_step is not None:
            artifacts = observations.get("get_artifacts")
            if not isinstance(artifacts, ArtifactsSnapshot):
                return CallTool("get_artifacts")
            if artifacts.redirect_detected_to is not None:
                return conclude(
                    RootCause.SCENARIO_STALE,
                    f"navigate가 {artifacts.redirect_detected_to}로 이동됨",
                )
            return conclude(RootCause.UI_REGRESSION, f"스텝 실패({failed_step.error})")

        if (
            check.response_time_ms is not None
            and check.response_time_ms > check.response_time_threshold_ms * 2
        ):
            return conclude(
                RootCause.SERVER_SLOW,
                f"응답 {check.response_time_ms}ms > 임계 {check.response_time_threshold_ms}ms×2",
            )

        baseline = observations.get("compare_with_baseline")
        if not isinstance(baseline, BaselineComparison):
            return CallTool("compare_with_baseline")
        if baseline.performance_delta is not None and baseline.performance_delta <= -10:
            return conclude(
                RootCause.FRONTEND_REGRESSION, f"성능 델타 {baseline.performance_delta}"
            )

        return conclude(RootCause.MEASUREMENT_NOISE, "강한 신호 없음")
