"""조사 trace — 에이전트가 무엇을 보고 왜 그렇게 결론냈는지의 기록.

루프가 도구를 부를 때마다 한 줄씩 쌓이고, 결론과 함께 하나의
InvestigationTrace로 닫힌다. 운영에서는 이 구조가 그대로
agent_investigations 저장·UI 타임라인의 원천이 된다(후속 주차).
"""

import json
from dataclasses import dataclass

from aim_worker.agent.root_causes import RootCause

# 도구 응답 요약의 길이 상한 — trace는 "무엇을 봤나"의 기록이지 응답 원본
# 저장소가 아니다. 원본은 언제나 케이스/DB에서 다시 꺼낼 수 있다.
RESULT_SUMMARY_MAX_CHARS = 300


def summarize_result(result: object) -> str:
    text = repr(result)
    if len(text) <= RESULT_SUMMARY_MAX_CHARS:
        return text
    return text[: RESULT_SUMMARY_MAX_CHARS - 1] + "…"


@dataclass(frozen=True)
class ToolCall:
    """도구 호출 한 번의 기록."""

    step: int
    tool: str
    result_summary: str


@dataclass(frozen=True)
class InvestigationTrace:
    """조사 한 건의 전체 기록 — 도구 호출 순서 + 결론."""

    case_ref: str | None  # 평가 케이스 id 또는 운영 check_run id
    tool_calls: tuple[ToolCall, ...]
    root_cause: RootCause
    summary: str
    recommendation: str
    recheck_used: bool
    # 미허용 도구 호출 시도(도구명, 시도 순) — "무단 변경 시도 0건" 지표의 근거
    violations: tuple[str, ...] = ()

    @property
    def steps_used(self) -> int:
        return len(self.tool_calls)

    def to_json(self) -> str:
        return json.dumps(
            {
                "case_ref": self.case_ref,
                "tool_calls": [
                    {"step": call.step, "tool": call.tool, "result_summary": call.result_summary}
                    for call in self.tool_calls
                ],
                "root_cause": self.root_cause.value,
                "summary": self.summary,
                "recommendation": self.recommendation,
                "recheck_used": self.recheck_used,
                "steps_used": self.steps_used,
                "violation_count": len(self.violations),
                "violations": list(self.violations),
            },
            ensure_ascii=False,
            indent=2,
        )
