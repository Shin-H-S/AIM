"""아티팩트 보존 정책 — 어떤 근거를 언제까지 들고 있을지 결정한다.

아티팩트(실패 스크린샷·Lighthouse JSON)는 단일 VM 디스크에 쌓이기만 하고
지워지는 경로가 없었다. 검사 주기 × 프로젝트 수로 선형 증가하므로 언젠가
디스크가 찬다.

그렇다고 일괄 삭제하면 안 된다. 아티팩트는 AI 리포트가 참조하는 근거 본체이고,
**사후에 다시 볼 가치는 검사마다 다르다.** 그래서 세 등급으로 나눈다:

1. 보존 — 베이스라인 검사의 근거. 비교의 기준점이므로 나이와 무관하게 남긴다.
2. 장기 — 장애가 걸린 근거. 실패한 검사, 인시던트를 열거나 해소한 검사,
   조사 에이전트가 들여다본 검사, 실패한 시나리오 실행. 사후 분석의 대상이다.
3. 일반 — 그 외. 이상 없이 끝난 검사의 근거는 오래 들고 있을 이유가 적다.

판정은 아티팩트 id 집합 단위로 한다. 검사에 직접 달린 아티팩트와 시나리오
실행에 달린 아티팩트를 같은 규칙으로 다루려면 그 편이 단순하다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import CompoundSelect, Select, or_, select, union
from sqlalchemy.orm import Session

from aim_api.models.agent_investigation import AgentInvestigation
from aim_api.models.alert import Incident
from aim_api.models.check_run import CheckRun, CheckRunStatus
from aim_api.models.project import Project
from aim_api.models.scanner_result import Artifact
from aim_api.models.scenario import ScenarioRun, ScenarioRunStatus


@dataclass(frozen=True)
class ArtifactRetentionPolicy:
    """보존 기간 설정. 일수는 아티팩트 생성 시각 기준이다."""

    default_days: int
    incident_days: int

    def __post_init__(self) -> None:
        if self.default_days < 1 or self.incident_days < 1:
            raise ValueError("Retention periods must be at least one day.")
        if self.incident_days < self.default_days:
            raise ValueError(
                "Incident retention must not be shorter than the default retention — "
                "evidence for a failure is the evidence most worth keeping."
            )


# 검사 id를 뽑는 SELECT. nullable 컬럼(baseline_check_run_id 등)에서 뽑으면
# UUID | None 이 되지만, 부르는 쪽이 NULL을 걸러낸 뒤 넘긴다.
CheckRunIdSelect = Select[tuple[UUID]] | Select[tuple[UUID | None]]


def as_id_select(statement: CompoundSelect[tuple[UUID]]) -> Select[tuple[UUID]]:
    """UNION 결과를 다시 IN 절에 넣을 수 있는 SELECT로 감싼다.

    CompoundSelect는 또 union할 수 없고 IN 절에서도 다루기 번거로워서,
    서브쿼리로 한 번 접은 뒤 단일 컬럼 SELECT로 되돌린다.
    """
    subquery = statement.subquery()
    return select(subquery.c[0])


def artifact_ids_for_check_runs(check_run_ids: CheckRunIdSelect) -> Select[tuple[UUID]]:
    """해당 검사들에 속한 아티팩트 id — 검사에 직접 달린 것과 연결된 시나리오 실행의 것."""
    direct = select(Artifact.id).where(Artifact.check_run_id.in_(check_run_ids))
    through_scenario_run = select(Artifact.id).where(
        Artifact.scenario_run_id.in_(
            select(ScenarioRun.id).where(ScenarioRun.check_run_id.in_(check_run_ids))
        )
    )
    return as_id_select(union(direct, through_scenario_run))


def preserved_artifact_ids() -> Select[tuple[UUID]]:
    """나이와 무관하게 남길 아티팩트 — 프로젝트 베이스라인 검사의 근거."""
    baseline_check_run_ids = select(Project.baseline_check_run_id).where(
        Project.baseline_check_run_id.is_not(None)
    )
    return artifact_ids_for_check_runs(baseline_check_run_ids)


def long_lived_artifact_ids() -> Select[tuple[UUID]]:
    """장애 등급으로 오래 남길 아티팩트.

    조사 에이전트가 참조한 검사를 포함하는 이유: 그 근거가 사라지면 조사 결론을
    나중에 다시 검증할 수 없다.
    """
    incident_check_run_ids = as_id_select(
        union(
            select(CheckRun.id).where(CheckRun.status == CheckRunStatus.FAILED.value),
            select(Incident.opened_check_run_id),
            select(Incident.resolved_check_run_id).where(
                Incident.resolved_check_run_id.is_not(None)
            ),
            select(AgentInvestigation.check_run_id),
            select(AgentInvestigation.recheck_check_run_id).where(
                AgentInvestigation.recheck_check_run_id.is_not(None)
            ),
        )
    )
    failed_scenario_run_artifacts = select(Artifact.id).where(
        Artifact.scenario_run_id.in_(
            select(ScenarioRun.id).where(ScenarioRun.status == ScenarioRunStatus.FAILED.value)
        )
    )
    return as_id_select(
        union(
            artifact_ids_for_check_runs(incident_check_run_ids),
            failed_scenario_run_artifacts,
        )
    )


def list_expired_artifacts(
    session: Session,
    *,
    now: datetime,
    policy: ArtifactRetentionPolicy,
    limit: int,
) -> list[Artifact]:
    """보존 기간이 지난 아티팩트를 오래된 것부터 최대 limit개 돌려준다.

    삭제하지 않는다 — 파일과 레코드 중 무엇을 먼저 지울지는 호출자가 정한다.
    """
    default_cutoff = now - timedelta(days=policy.default_days)
    incident_cutoff = now - timedelta(days=policy.incident_days)

    preserved = preserved_artifact_ids()
    long_lived = long_lived_artifact_ids()

    statement = (
        select(Artifact)
        .where(
            Artifact.id.not_in(preserved),
            or_(
                Artifact.id.in_(long_lived) & (Artifact.created_at < incident_cutoff),
                Artifact.id.not_in(long_lived) & (Artifact.created_at < default_cutoff),
            ),
        )
        .order_by(Artifact.created_at.asc(), Artifact.id.asc())
        .limit(limit)
    )

    return list(session.scalars(statement))


def delete_artifact_record(session: Session, *, artifact_id: UUID) -> None:
    """아티팩트 레코드를 지운다. 파일은 이미 지워졌다고 가정한다."""
    artifact = session.get(Artifact, artifact_id)
    if artifact is None:
        return

    session.delete(artifact)
    session.commit()
