"""평가셋 채점기 — 조사기의 원인 분류를 코드로 채점한다.

핵심 지표(정확도·혼동 행렬)는 절대 LLM에 맡기지 않는다. W1의 규칙
베이스라인은 "LLM 에이전트가 넘어야 할 목표선"을 만들기 위한 결정적
조사기다.

실행:
    uv run python -m aim_worker.agent.evaluate --split dev
"""

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from aim_worker.agent.cases import EvalCase, ToolFixtures
from aim_worker.agent.dataset import generate_cases, split_cases
from aim_worker.agent.root_causes import RootCause


class Investigator(Protocol):
    """조사기 인터페이스 — W2의 에이전트 루프도 이 형태로 채점된다."""

    def investigate(self, fixtures: ToolFixtures) -> RootCause: ...


class RuleBaselineInvestigator:
    """결정적 휴리스틱 베이스라인.

    fixtures의 강한 신호만 순서대로 본다. 경계 사례(조용한 UI 파손,
    리다이렉트 흔적 없는 스테일, 지연이 스텝을 깨는 케이스)에서 틀리도록
    일부러 단순하게 유지한다 — 이 빈틈이 곧 에이전트의 개선 여지다.
    """

    def investigate(self, fixtures: ToolFixtures) -> RootCause:
        check = fixtures.check_run
        if not check.availability_ok:
            return RootCause.SERVICE_DOWN
        if check.ssl_valid is False:
            return RootCause.SSL_INVALID
        if not fixtures.recheck.reproduced:
            return RootCause.MEASUREMENT_NOISE

        has_failed_step = any(step.status == "FAILED" for step in fixtures.scenario_results)
        if has_failed_step:
            if fixtures.artifacts.redirect_detected_to is not None:
                return RootCause.SCENARIO_STALE
            return RootCause.UI_REGRESSION

        if (
            check.response_time_ms is not None
            and check.response_time_ms > check.response_time_threshold_ms * 2
        ):
            return RootCause.SERVER_SLOW

        performance_delta = fixtures.baseline.performance_delta
        if performance_delta is not None and performance_delta <= -10:
            return RootCause.FRONTEND_REGRESSION

        return RootCause.MEASUREMENT_NOISE


@dataclass(frozen=True)
class EvaluationReport:
    total: int
    correct: int
    accuracy: float
    per_cause_accuracy: dict[str, float]
    confusion: dict[str, dict[str, int]]  # 정답 → (예측 → 건수)
    misclassified_case_ids: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(
            {
                "total": self.total,
                "correct": self.correct,
                "accuracy": round(self.accuracy, 4),
                "per_cause_accuracy": {
                    cause: round(value, 4) for cause, value in self.per_cause_accuracy.items()
                },
                "confusion": self.confusion,
                "misclassified_case_ids": list(self.misclassified_case_ids),
            },
            ensure_ascii=False,
            indent=2,
        )


def evaluate(investigator: Investigator, cases: Iterable[EvalCase]) -> EvaluationReport:
    total = 0
    correct = 0
    per_cause_total: dict[str, int] = {}
    per_cause_correct: dict[str, int] = {}
    confusion: dict[str, dict[str, int]] = {}
    misclassified: list[str] = []

    for case in cases:
        total += 1
        predicted = investigator.investigate(case.fixtures)
        actual = case.root_cause
        per_cause_total[actual.value] = per_cause_total.get(actual.value, 0) + 1
        row = confusion.setdefault(actual.value, {})
        row[predicted.value] = row.get(predicted.value, 0) + 1
        if predicted == actual:
            correct += 1
            per_cause_correct[actual.value] = per_cause_correct.get(actual.value, 0) + 1
        else:
            misclassified.append(case.case_id)

    per_cause_accuracy = {
        cause: per_cause_correct.get(cause, 0) / count
        for cause, count in sorted(per_cause_total.items())
    }
    return EvaluationReport(
        total=total,
        correct=correct,
        accuracy=correct / total if total else 0.0,
        per_cause_accuracy=per_cause_accuracy,
        confusion=confusion,
        misclassified_case_ids=tuple(misclassified),
    )


def select_split(split: str) -> tuple[EvalCase, ...]:
    cases = generate_cases()
    if split == "all":
        return cases
    dev, test = split_cases(cases)
    return dev if split == "dev" else test


def format_text(report: EvaluationReport, split: str) -> str:
    lines = [
        f"평가셋({split}) {report.total}건 — 정확도 {report.accuracy:.1%}"
        f" ({report.correct}/{report.total})",
        "유형별:",
    ]
    lines.extend(f"  {cause:<22} {value:.1%}" for cause, value in report.per_cause_accuracy.items())
    if report.misclassified_case_ids:
        lines.append(
            f"오분류 {len(report.misclassified_case_ids)}건: "
            + ", ".join(report.misclassified_case_ids)
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="조사 에이전트 평가셋 채점기")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    cases = select_split(args.split)
    report = evaluate(RuleBaselineInvestigator(), cases)
    if args.format == "json":
        print(report.to_json())
    else:
        print(format_text(report, args.split))


if __name__ == "__main__":
    main()
