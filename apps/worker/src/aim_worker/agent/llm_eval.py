"""LLM 정책 평가 러너 — 라우터+LLM(+규칙 폴백)을 채점하고 게이트를 실측한다.

G1(정확도)·G2(위험 방향)·churn(기준 대비 고침/망가뜨림)·G3(LLM 호출률·
토큰·비용·지연)·G4(폴백 발동)를 한 리포트로 낸다. 실 API 호출이므로
ANTHROPIC_API_KEY(.env)가 필요하다.

실행:
    uv run python -m aim_worker.agent.llm_eval --split dev
"""

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass

from aim_worker.agent.cases import EvalCase
from aim_worker.agent.evaluate import (
    ALL_CLEAR_CAUSES,
    BREAKAGE_CAUSES,
    RuleBaselineInvestigator,
    select_split,
)
from aim_worker.agent.llm_policy import JudgeCall, build_llm_policy_factory
from aim_worker.agent.loop import InvestigationLoop
from aim_worker.agent.policies import RouterPolicy, RulePolicy
from aim_worker.agent.toolbox import FixturesToolbox

# USD / 1M 토큰 (입력, 출력) — 비용 추정용. 모델 추가 시 여기만 갱신.
MODEL_PRICES_USD: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (3.0, 15.0),
}


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    actual: str
    predicted: str
    correct: bool
    baseline_correct: bool
    generator: str
    confidence: str
    violations: int
    llm_calls: tuple[JudgeCall, ...]
    wall_ms: int


def call_cost_usd(call: JudgeCall) -> float:
    prices = MODEL_PRICES_USD.get(call.model)
    if prices is None:
        return 0.0
    input_price, output_price = prices
    return call.input_tokens / 1e6 * input_price + call.output_tokens / 1e6 * output_price


def run_split(cases: tuple[EvalCase, ...]) -> list[CaseResult]:
    factory = build_llm_policy_factory()
    if factory is None:
        sys.exit("ANTHROPIC_API_KEY가 설정되지 않아 LLM 평가를 실행할 수 없습니다.")
    baseline = RuleBaselineInvestigator()

    results: list[CaseResult] = []
    for index, case in enumerate(cases, start=1):
        policy = factory()
        loop = InvestigationLoop(
            RouterPolicy(policy),
            FixturesToolbox(case.fixtures),
            fallback_policy=RulePolicy(),
        )
        started = time.perf_counter()
        trace = loop.run(case.case_id)
        wall_ms = int((time.perf_counter() - started) * 1000)

        results.append(
            CaseResult(
                case_id=case.case_id,
                actual=case.root_cause.value,
                predicted=trace.root_cause.value,
                correct=trace.root_cause == case.root_cause,
                baseline_correct=baseline.investigate(case.fixtures) == case.root_cause,
                generator=trace.generator,
                confidence=trace.confidence,
                violations=len(trace.violations),
                llm_calls=tuple(policy.calls),
                wall_ms=wall_ms,
            )
        )
        marker = "✓" if results[-1].correct else "✗"
        print(f"  [{index:>3}/{len(cases)}] {marker} {case.case_id} → {trace.generator}")
    return results


@dataclass(frozen=True)
class EvalSummary:
    split: str
    total: int
    correct: int
    accuracy: float
    misclassified: tuple[str, ...]
    dangerous: tuple[str, ...]  # G2
    churn_fixed: tuple[str, ...]
    churn_broken: tuple[str, ...]
    violations_total: int
    llm_case_count: int
    llm_call_count: int
    escalation_count: int
    fallback_case_ids: tuple[str, ...]  # G4
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_p50_ms: int
    latency_p95_ms: int
    latency_max_ms: int

    def to_json_dict(self) -> dict[str, object]:
        return {
            "split": self.split,
            "total": self.total,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "misclassified_case_ids": list(self.misclassified),
            "dangerous_misclassified_case_ids": list(self.dangerous),
            "churn_fixed": list(self.churn_fixed),
            "churn_broken": list(self.churn_broken),
            "violations_total": self.violations_total,
            "llm_case_count": self.llm_case_count,
            "llm_call_count": self.llm_call_count,
            "escalation_count": self.escalation_count,
            "fallback_case_ids": list(self.fallback_case_ids),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "llm_latency_ms_p50": self.latency_p50_ms,
            "llm_latency_ms_p95": self.latency_p95_ms,
            "llm_latency_ms_max": self.latency_max_ms,
        }


def summarize(results: list[CaseResult], split: str) -> EvalSummary:
    total = len(results)
    breakage = {cause.value for cause in BREAKAGE_CAUSES}
    all_clear = {cause.value for cause in ALL_CLEAR_CAUSES}

    llm_results = [r for r in results if r.llm_calls]
    calls = [call for r in results for call in r.llm_calls]
    latencies = sorted(sum(call.latency_ms for call in r.llm_calls) for r in llm_results)

    def percentile(values: list[int], fraction: float) -> int:
        if not values:
            return 0
        return values[min(len(values) - 1, int(len(values) * fraction))]

    return EvalSummary(
        split=split,
        total=total,
        correct=sum(1 for r in results if r.correct),
        accuracy=round(sum(1 for r in results if r.correct) / total, 4) if total else 0.0,
        misclassified=tuple(r.case_id for r in results if not r.correct),
        dangerous=tuple(
            r.case_id
            for r in results
            if not r.correct and r.actual in breakage and r.predicted in all_clear
        ),
        churn_fixed=tuple(r.case_id for r in results if r.correct and not r.baseline_correct),
        churn_broken=tuple(r.case_id for r in results if r.baseline_correct and not r.correct),
        violations_total=sum(r.violations for r in results),
        llm_case_count=len(llm_results),
        llm_call_count=len(calls),
        escalation_count=sum(1 for r in results if len(r.llm_calls) > 1),
        fallback_case_ids=tuple(r.case_id for r in results if r.generator.endswith("-fallback")),
        input_tokens=sum(call.input_tokens for call in calls),
        output_tokens=sum(call.output_tokens for call in calls),
        cost_usd=round(sum(call_cost_usd(call) for call in calls), 4),
        latency_p50_ms=int(statistics.median(latencies)) if latencies else 0,
        latency_p95_ms=percentile(latencies, 0.95),
        latency_max_ms=latencies[-1] if latencies else 0,
    )


def format_text(summary: EvalSummary) -> str:
    lines = [
        f"=== LLM 평가({summary.split}) — {summary.total}건 ===",
        f"정확도 [G1]: {summary.accuracy:.1%} ({summary.correct}/{summary.total})",
        f"위험 방향 오분류 [G2]: {len(summary.dangerous)}건 {list(summary.dangerous)}",
        f"churn: 고침 {len(summary.churn_fixed)}건 {list(summary.churn_fixed)}"
        f" / 망가뜨림 {len(summary.churn_broken)}건 {list(summary.churn_broken)}",
        f"오분류: {list(summary.misclassified)}",
        f"무단 도구 시도: {summary.violations_total}건",
        f"LLM 호출 [G3]: 대상 {summary.llm_case_count}건 · 호출 {summary.llm_call_count}회"
        f" · 에스컬레이션 {summary.escalation_count}회",
        f"폴백 발동 [G4]: {len(summary.fallback_case_ids)}건 {list(summary.fallback_case_ids)}",
        f"토큰: 입력 {summary.input_tokens:,} / 출력 {summary.output_tokens:,}"
        f" → 비용 ${summary.cost_usd}",
        f"LLM 지연(케이스당): p50 {summary.latency_p50_ms}ms"
        f" · p95 {summary.latency_p95_ms}ms · max {summary.latency_max_ms}ms",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="조사 에이전트 LLM 정책 평가 러너")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--out", help="요약 JSON 저장 경로(선택)")
    args = parser.parse_args()

    cases = select_split(args.split)
    print(f"평가 시작: {args.split} {len(cases)}건 (LLM 대상은 실패 스텝 케이스만)")
    results = run_split(cases)
    summary = summarize(results, args.split)
    print()
    print(format_text(summary))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(summary.to_json_dict(), handle, ensure_ascii=False, indent=2)
        print(f"\n요약 저장: {args.out}")


if __name__ == "__main__":
    main()
