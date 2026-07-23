"""조사 실행 서비스 — 검사 하나를 조사하고 trace를 DB에 남긴다.

정책 조립은 W3 그대로: RouterPolicy(확정 66%는 규칙 즉시 결론) +
LlmPolicy(실패 스텝 3자 판별) + RulePolicy 폴백(G4). API 키가 없으면
규칙 전용으로 강등되어 조사는 여전히 종결된다.
"""

import logging
import time
from datetime import timedelta
from uuid import UUID

from aim_api.config import get_settings
from aim_api.models.agent_investigation import AgentInvestigation, utc_now
from aim_api.models.check_run import CheckRun
from aim_api.models.project import Project
from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_worker.agent.db_toolbox import TERMINAL_CHECK_RUN_STATUSES, DbToolbox
from aim_worker.agent.llm_policy import LlmPolicy, build_llm_policy_factory
from aim_worker.agent.loop import InvestigationLoop, Policy
from aim_worker.agent.policies import RouterPolicy, RulePolicy

logger = logging.getLogger(__name__)

INVESTIGATION_TRIGGER_INCIDENT = "incident"
INVESTIGATION_TRIGGER_MANUAL = "manual"


def find_investigation(session: Session, *, check_run_id: UUID) -> AgentInvestigation | None:
    return session.scalars(
        select(AgentInvestigation).where(AgentInvestigation.check_run_id == check_run_id)
    ).first()


def is_in_cooldown(session: Session, *, project_id: UUID) -> bool:
    """같은 프로젝트의 직전 조사로부터 쿨다운이 지났는가 — 조사 폭주 방지."""
    cooldown_minutes = get_settings().aim_agent_cooldown_minutes
    threshold = utc_now() - timedelta(minutes=cooldown_minutes)
    recent = session.scalars(
        select(AgentInvestigation)
        .where(
            AgentInvestigation.project_id == project_id,
            AgentInvestigation.created_at >= threshold,
        )
        .limit(1)
    ).first()
    return recent is not None


def run_agent_investigation_for_check_run(
    session: Session,
    *,
    check_run_id: UUID,
    incident_id: UUID | None = None,
    trigger: str = INVESTIGATION_TRIGGER_INCIDENT,
) -> AgentInvestigation | None:
    """조사를 실행하고 기록한다. 조사가 부적합하면 None(멱등·쿨다운·상태)."""
    check_run = session.get(CheckRun, check_run_id)
    if check_run is None or check_run.status not in TERMINAL_CHECK_RUN_STATUSES:
        return None
    if find_investigation(session, check_run_id=check_run_id) is not None:
        return None
    project = session.get(Project, check_run.project_id)
    if project is None:
        return None
    if trigger == INVESTIGATION_TRIGGER_INCIDENT and is_in_cooldown(session, project_id=project.id):
        logger.info(
            "Agent investigation skipped by cooldown.",
            extra={"project_id": str(project.id), "check_run_id": str(check_run_id)},
        )
        return None

    toolbox = DbToolbox(session, project=project, check_run=check_run)
    llm_policy: LlmPolicy | None = None
    llm_factory = build_llm_policy_factory()
    policy: Policy
    if llm_factory is not None:
        llm_policy = llm_factory()
        policy = RouterPolicy(llm_policy)
    else:
        # API 키 없음 — 규칙 전용으로도 조사는 항상 종결된다(G4 사상).
        policy = RulePolicy()

    loop = InvestigationLoop(policy, toolbox, fallback_policy=RulePolicy())
    started = time.perf_counter()
    trace = loop.run(case_ref=str(check_run_id))
    duration_ms = int((time.perf_counter() - started) * 1000)

    investigation = AgentInvestigation(
        project_id=project.id,
        check_run_id=check_run.id,
        incident_id=incident_id,
        trigger=trigger,
        root_cause=trace.root_cause.value,
        confidence=trace.confidence,
        summary=trace.summary,
        recommendation=trace.recommendation,
        generator=trace.generator,
        recheck_used=trace.recheck_used,
        recheck_check_run_id=toolbox.recheck_check_run_id,
        tool_calls=[
            {"step": call.step, "tool": call.tool, "result_summary": call.result_summary}
            for call in trace.tool_calls
        ],
        violations=list(trace.violations),
        llm_calls=(
            [call.model_dump() for call in llm_policy.calls] if llm_policy is not None else []
        ),
        duration_ms=duration_ms,
    )
    session.add(investigation)
    session.commit()
    session.refresh(investigation)
    logger.info(
        "Agent investigation recorded.",
        extra={
            "check_run_id": str(check_run_id),
            "root_cause": investigation.root_cause,
            "generator": investigation.generator,
        },
    )
    return investigation
