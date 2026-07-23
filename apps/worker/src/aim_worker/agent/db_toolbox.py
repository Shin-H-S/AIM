"""운영 도구 상자 — 실 DB를 읽어 Toolbox 계약을 채운다.

FixturesToolbox(평가)와 같은 스냅샷 스키마를 실 데이터로 채우는 구현.
READ 6종은 읽기 전용이고, 유일한 쓰기는 trigger_recheck의 재검사 생성이다.

정직성 노트: failing_page_rendered_ok와 relocation_hint는 운영 판독기가
아직 없어 None으로 남는다(합성 평가셋과의 알려진 갭 — W5 과제). LLM
프롬프트의 "애매하면 파손" 편향이 그 공백의 안전망이다.
"""

import logging
import time
from collections.abc import Callable
from uuid import UUID

from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import (
    AvailabilityResult,
    LighthouseResult,
    RunComparison,
    ScoreResult,
    SslResult,
)
from aim_api.models.scenario import (
    ConsoleError,
    NetworkFailure,
    ScenarioRun,
    ScenarioRunStatus,
    StepResult,
    TestScenario,
    TestStep,
)
from aim_api.services import scan_queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_worker.agent.cases import (
    ArtifactsSnapshot,
    BaselineComparison,
    CheckRunSnapshot,
    ProjectConfigSnapshot,
    RecentRunSummary,
    RecheckResult,
    ScenarioStepResult,
)

logger = logging.getLogger(__name__)

TERMINAL_CHECK_RUN_STATUSES = {
    CheckRunStatus.COMPLETED.value,
    CheckRunStatus.FAILED.value,
    CheckRunStatus.CANCELLED.value,
}
RECENT_RUN_LIMIT = 5
AGENT_RECHECK_TRIGGER_SOURCE = "agent_recheck"


def is_bad_result(score: ScoreResult | None, *, project: Project) -> bool:
    """검사 결과가 '나쁜가' — 재검사 재현 판정의 기준."""
    if score is None:
        return True
    if score.deployment_risk == "RISK":
        return True
    return score.overall_score < project.quality_score_threshold


class DbToolbox:
    """조사 대상 검사 하나에 바인딩된 운영 도구 상자.

    재검사 폴링은 워커 슬롯 하나를 최대 timeout 동안 점유한다 — 인시던트
    빈도(월 수 건)에서 허용 가능한 트레이드오프다.
    """

    def __init__(
        self,
        session: Session,
        *,
        project: Project,
        check_run: CheckRun,
        recheck_timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session
        self._project = project
        self._check_run = check_run
        self._recheck_timeout_seconds = recheck_timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._sleep = sleep
        # 재검사가 실제로 만든 검사 id — 조사 기록의 근거 링크가 된다.
        self.recheck_check_run_id: UUID | None = None

    def _score(self, check_run_id: UUID) -> ScoreResult | None:
        return self._session.scalars(
            select(ScoreResult).where(ScoreResult.check_run_id == check_run_id)
        ).first()

    def _availability(self, check_run_id: UUID) -> AvailabilityResult | None:
        return self._session.scalars(
            select(AvailabilityResult).where(AvailabilityResult.check_run_id == check_run_id)
        ).first()

    def _scenario_runs(self, check_run_id: UUID) -> list[ScenarioRun]:
        return list(
            self._session.scalars(
                select(ScenarioRun)
                .where(ScenarioRun.check_run_id == check_run_id)
                .order_by(ScenarioRun.created_at)
            )
        )

    def get_check_run(self) -> CheckRunSnapshot:
        score = self._score(self._check_run.id)
        availability = self._availability(self._check_run.id)
        ssl = self._session.scalars(
            select(SslResult).where(SslResult.check_run_id == self._check_run.id)
        ).first()
        lighthouse = self._session.scalars(
            select(LighthouseResult).where(LighthouseResult.check_run_id == self._check_run.id)
        ).first()

        ssl_valid: bool | None = None
        ssl_failure: str | None = None
        if ssl is not None and ssl.is_applicable:
            ssl_valid = ssl.is_valid
            ssl_failure = ssl.failure_reason

        return CheckRunSnapshot(
            overall_score=float(score.overall_score) if score is not None else 0.0,
            grade=score.grade if score is not None else "F",
            deployment_risk=score.deployment_risk if score is not None else "RISK",
            gate_reason=score.gate_reason if score is not None else None,
            availability_ok=bool(availability.is_available) if availability else False,
            availability_failure=(
                availability.failure_reason if availability is not None else "검사 결과 없음"
            ),
            response_time_ms=availability.response_time_ms if availability else None,
            response_time_threshold_ms=self._project.response_time_threshold_ms,
            ssl_valid=ssl_valid,
            ssl_failure=ssl_failure,
            lighthouse_performance=lighthouse.performance_score if lighthouse else None,
            trigger_source=self._check_run.trigger_source,
            deploy_ref=self._check_run.deploy_ref,
        )

    def get_scenario_results(self) -> tuple[ScenarioStepResult, ...]:
        steps: list[ScenarioStepResult] = []
        for scenario_run in self._scenario_runs(self._check_run.id):
            rows = self._session.scalars(
                select(StepResult)
                .where(StepResult.scenario_run_id == scenario_run.id)
                .order_by(StepResult.step_order)
            )
            steps.extend(
                ScenarioStepResult(
                    step_order=row.step_order,
                    action=row.action,
                    target=row.target,
                    status=row.status,
                    error=row.error_message,
                )
                for row in rows
            )
        return tuple(steps)

    def get_artifacts(self) -> ArtifactsSnapshot:
        scenario_run_ids = [run.id for run in self._scenario_runs(self._check_run.id)]
        console_errors: tuple[str, ...] = ()
        network_failures: tuple[str, ...] = ()
        if scenario_run_ids:
            console_errors = tuple(
                row.message
                for row in self._session.scalars(
                    select(ConsoleError)
                    .where(ConsoleError.scenario_run_id.in_(scenario_run_ids))
                    .order_by(ConsoleError.created_at)
                )
            )
            network_failures = tuple(
                f"{row.method} {row.request_url}"
                + (f" — {row.failure_text}" if row.failure_text else "")
                for row in self._session.scalars(
                    select(NetworkFailure)
                    .where(NetworkFailure.scenario_run_id.in_(scenario_run_ids))
                    .order_by(NetworkFailure.created_at)
                )
            )

        availability = self._availability(self._check_run.id)
        redirect_detected_to: str | None = None
        if (
            availability is not None
            and availability.redirect_count > 0
            and availability.final_url
            and availability.final_url != availability.service_url
        ):
            redirect_detected_to = availability.final_url

        return ArtifactsSnapshot(
            console_errors=console_errors,
            network_failures=network_failures,
            failing_page_rendered_ok=None,  # 스크린샷 판독기 없음 — W5 과제
            redirect_detected_to=redirect_detected_to,
            relocation_hint=None,  # 이동 흔적 판독기 없음 — W5 과제
        )

    def compare_with_baseline(self) -> BaselineComparison:
        comparison = self._session.scalars(
            select(RunComparison).where(RunComparison.check_run_id == self._check_run.id)
        ).first()
        if comparison is None:
            return BaselineComparison(None, None, None)
        return BaselineComparison(
            overall_delta=(
                float(comparison.overall_score_delta)
                if comparison.overall_score_delta is not None
                else None
            ),
            performance_delta=comparison.performance_score_delta,
            response_time_delta_ms=comparison.response_time_delta_ms,
        )

    def get_recent_runs(self) -> tuple[RecentRunSummary, ...]:
        rows = list(
            self._session.scalars(
                select(CheckRun)
                .where(
                    CheckRun.project_id == self._project.id,
                    CheckRun.id != self._check_run.id,
                    CheckRun.status.in_(TERMINAL_CHECK_RUN_STATUSES),
                    CheckRun.queued_at < self._check_run.queued_at,
                )
                .order_by(CheckRun.queued_at.desc())
                .limit(RECENT_RUN_LIMIT)
            )
        )
        summaries: list[RecentRunSummary] = []
        for run in rows:
            score = self._score(run.id)
            availability = self._availability(run.id)
            lighthouse = self._session.scalars(
                select(LighthouseResult).where(LighthouseResult.check_run_id == run.id)
            ).first()
            scenario_runs = self._scenario_runs(run.id)
            all_passed = all(
                scenario_run.status == ScenarioRunStatus.COMPLETED.value
                for scenario_run in scenario_runs
            )
            summaries.append(
                RecentRunSummary(
                    overall_score=float(score.overall_score) if score is not None else 0.0,
                    all_scenarios_passed=all_passed,
                    response_time_ms=availability.response_time_ms if availability else None,
                    lighthouse_performance=lighthouse.performance_score if lighthouse else None,
                )
            )
        return tuple(summaries)

    def get_project_config(self) -> ProjectConfigSnapshot:
        targets = tuple(
            self._session.scalars(
                select(TestStep.target)
                .join(TestScenario, TestStep.scenario_id == TestScenario.id)
                .where(
                    TestScenario.project_id == self._project.id,
                    TestScenario.is_active.is_(True),
                    TestStep.action == "navigate",
                    TestStep.target.is_not(None),
                )
                .order_by(TestStep.step_order)
            )
        )
        return ProjectConfigSnapshot(
            service_url=self._project.service_url,
            scenario_targets=tuple(target for target in targets if target is not None),
            response_time_threshold_ms=self._project.response_time_threshold_ms,
            quality_score_threshold=self._project.quality_score_threshold,
        )

    def trigger_recheck(self) -> RecheckResult:
        """재검사를 만들어 큐에 넣고 종결까지 폴링한다.

        재검사를 실행할 수 없거나 제때 끝나지 않으면 **재현된 것으로
        간주**한다 — 파손 쪽으로 보수적인 판정이 거짓 안심(G2)보다 낫다.
        """
        current_score = self._score(self._check_run.id)
        conservative = RecheckResult(
            reproduced=True,
            overall_score=(
                float(current_score.overall_score) if current_score is not None else 0.0
            ),
        )

        if self._project.owner_id is None:
            return conservative
        recheck_run = CheckRun(
            project_id=self._project.id,
            requested_by_id=self._project.owner_id,
            status=CheckRunStatus.QUEUED.value,
            trigger_source=AGENT_RECHECK_TRIGGER_SOURCE,
        )
        self._session.add(recheck_run)
        self._session.commit()
        self._session.refresh(recheck_run)
        try:
            scan_queue.enqueue_check_run(check_run_id=recheck_run.id)
        except scan_queue.ScanQueueUnavailableError:
            logger.warning(
                "Agent recheck could not be enqueued; treating as reproduced.",
                extra={"check_run_id": str(self._check_run.id)},
            )
            return conservative
        self.recheck_check_run_id = recheck_run.id

        deadline = time.monotonic() + self._recheck_timeout_seconds
        while time.monotonic() < deadline:
            self._sleep(self._poll_interval_seconds)
            self._session.expire_all()
            refreshed = self._session.get(CheckRun, recheck_run.id)
            if refreshed is None or refreshed.status not in TERMINAL_CHECK_RUN_STATUSES:
                continue
            recheck_score = self._score(recheck_run.id)
            return RecheckResult(
                reproduced=is_bad_result(recheck_score, project=self._project),
                overall_score=(
                    float(recheck_score.overall_score) if recheck_score is not None else 0.0
                ),
            )

        logger.warning(
            "Agent recheck timed out; treating as reproduced.",
            extra={"recheck_check_run_id": str(recheck_run.id)},
        )
        return conservative
