"""운영 메트릭 — Prometheus 텍스트 형식.

**왜 in-process 카운터가 아닌가**: API·워커·beat가 별개 프로세스라, 프로세스
안에 카운터를 두면 어느 프로세스를 긁느냐에 따라 값이 달라진다. 이 제품에서
정말 보고 싶은 것은 요청 지연이 아니라 **검사가 성공하고 있는지, 인시던트가
열려 있는지, 에이전트가 토큰을 얼마나 쓰는지** 이고, 그 값들의 단일 출처는
데이터베이스다. 그래서 스크레이프 시점에 DB에서 읽어 렌더한다.

**비용을 넣지 않는 이유**: LLM 단가는 앱보다 빨리 바뀐다. 사실인 토큰 수를
노출하고, 단가를 곱하는 일은 대시보드·알림 쪽에 맡긴다.

노출 형식은 단순해서 클라이언트 라이브러리를 들이지 않는다.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Float, func, select
from sqlalchemy.orm import Session

from aim_api.models.agent_investigation import AgentInvestigation
from aim_api.models.ai_report import AIReport
from aim_api.models.alert import Alert, Incident, IncidentStatus
from aim_api.models.check_run import CheckRun
from aim_api.models.project import Project
from aim_api.models.scanner_result import Artifact
from aim_api.services import incidents as incidents_service
from aim_api.services import scan_scheduling

# 지연·성공률은 전 기간 평균이 아니라 최근 구간이어야 의미가 있다.
RECENT_WINDOW_HOURS = 24


@dataclass(frozen=True)
class Metric:
    name: str
    help_text: str
    metric_type: str
    samples: list[tuple[dict[str, str], float]]


def escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_metrics(metrics: list[Metric]) -> str:
    """Prometheus 텍스트 노출 형식으로 렌더한다."""
    lines: list[str] = []
    for metric in metrics:
        lines.append(f"# HELP {metric.name} {metric.help_text}")
        lines.append(f"# TYPE {metric.name} {metric.metric_type}")
        for labels, value in metric.samples:
            if labels:
                rendered_labels = ",".join(
                    f'{key}="{escape_label_value(str(label_value))}"'
                    for key, label_value in sorted(labels.items())
                )
                lines.append(f"{metric.name}{{{rendered_labels}}} {value}")
            else:
                lines.append(f"{metric.name} {value}")
    return "\n".join(lines) + "\n"


def count_by(session: Session, column: Any) -> list[tuple[dict[str, str], float]]:
    """단일 컬럼으로 그룹핑한 건수를 샘플 목록으로 만든다."""
    rows = session.execute(select(column, func.count()).group_by(column)).all()
    return [({"value": str(value)}, float(count)) for value, count in rows]


def collect_agent_token_samples(session: Session) -> list[tuple[dict[str, str], float]]:
    """조사 에이전트가 모델별로 쓴 토큰 합계.

    llm_calls는 JSON 배열이라 SQL로 집계하기보다 읽어서 더한다 — 조사 건수는
    쿨다운(프로젝트당 30분) 때문에 많아질 수 없는 규모다.
    """
    totals: dict[tuple[str, str], float] = {}
    for (llm_calls,) in session.execute(select(AgentInvestigation.llm_calls)):
        for call in llm_calls or []:
            model = str(call.get("model", "unknown"))
            for kind, field in (("input", "input_tokens"), ("output", "output_tokens")):
                totals[(model, kind)] = totals.get((model, kind), 0.0) + float(call.get(field, 0))

    return [
        ({"model": model, "kind": kind}, total) for (model, kind), total in sorted(totals.items())
    ]


def collect_agent_feedback_samples(session: Session) -> list[tuple[dict[str, str], float]]:
    """조사에 대한 사용자 판정(정확/부정확) 건수.

    피드백 채널은 조사 정확도를 합성 평가셋이 아닌 실데이터로 재기 위해 만들었다
    (ADR 0002의 남은 한계). 그런데 쌓이는지 볼 수단이 없으면 채널이 죽어 있어도
    모른다 — 이 메트릭이 그 감시다. 정확도 자체는 소비자가 두 값으로 계산한다.

    두 버킷을 항상 내보내는 이유는 인시던트 메트릭과 같다: 라벨이 사라지면
    스크레이퍼의 시계열이 끊긴다. 미피드백 조사 수는 조사 총수에서 빼면 나온다.
    """
    rows = session.execute(
        select(AgentInvestigation.feedback_verdict, func.count())
        .where(AgentInvestigation.feedback_verdict.is_not(None))
        .group_by(AgentInvestigation.feedback_verdict)
    ).all()

    counts = {"accurate": 0.0, "inaccurate": 0.0}
    for verdict, count in rows:
        counts[str(verdict)] = float(count)

    return [({"verdict": verdict}, count) for verdict, count in sorted(counts.items())]


def collect_open_incident_samples(
    session: Session, *, now: datetime
) -> list[tuple[dict[str, str], float]]:
    """열린 인시던트를 '최근 확인됨'과 '오래됨'으로 나눈다.

    나누지 않으면 지금 조치가 필요한 장애와 검사가 멈춘 프로젝트의 화석이 같은
    숫자로 세어져, 그 숫자로는 아무 판단도 할 수 없게 된다.
    """
    open_incidents = session.execute(
        select(Incident.project_id, func.count())
        .where(Incident.status == IncidentStatus.OPEN.value)
        .group_by(Incident.project_id)
    ).all()

    last_checked = incidents_service.latest_check_run_at_by_project(
        session, project_ids=[project_id for project_id, _ in open_incidents]
    )

    counts = {"current": 0.0, "stale": 0.0}
    for project_id, count in open_incidents:
        bucket = (
            "stale"
            if incidents_service.is_stale(last_checked.get(project_id), now=now)
            else "current"
        )
        counts[bucket] += float(count)

    return [({"freshness": freshness}, count) for freshness, count in sorted(counts.items())]


def collect_scheduled_overdue_count(session: Session, *, now: datetime) -> float:
    """정기 검사가 밀린 프로젝트 수 — 스케줄러(beat) 죽음의 심장박동 감시.

    beat·스케줄러가 죽으면 검사가 '안 생기는' 형태로 조용히 실패한다. 큐 적체
    메트릭은 이걸 못 본다 — 큐에 아무것도 들어오지 않기 때문이다. 대상(인증·
    옵트인) 프로젝트의 마지막 검사(한 번도 없으면 마지막 설정 변경 시각)가
    자기 주기의 2배를 넘겼으면 밀린 것으로 센다. 2배인 이유: 스케줄러 주기와
    검사 소요 시간만큼의 자연 지연을 오탐 없이 흡수하기 위해서다.
    """
    eligible_projects = session.scalars(
        select(Project).where(
            Project.verified_at.is_not(None),
            Project.owner_id.is_not(None),
            Project.scheduled_scans_enabled.is_(True),
        )
    ).all()
    if not eligible_projects:
        return 0.0

    latest_run_at = scan_scheduling.get_latest_check_run_created_at_by_project(session)
    overdue = 0
    for project in eligible_projects:
        baseline = latest_run_at.get(project.id) or project.updated_at
        deadline = scan_scheduling.as_utc(baseline) + timedelta(
            minutes=2 * project.scan_interval_minutes
        )
        if deadline <= now:
            overdue += 1
    return float(overdue)


def collect_metrics(session: Session, *, now: datetime | None = None) -> list[Metric]:
    current_time = now or datetime.now(UTC)
    window_start = current_time - timedelta(hours=RECENT_WINDOW_HOURS)

    recent_duration = session.scalar(
        select(
            func.avg(func.extract("epoch", CheckRun.finished_at - CheckRun.started_at).cast(Float))
        ).where(
            CheckRun.started_at.is_not(None),
            CheckRun.finished_at.is_not(None),
            CheckRun.created_at >= window_start,
        )
    )

    return [
        Metric(
            name="aim_check_runs_total",
            help_text="Check runs recorded, by terminal or in-flight status.",
            metric_type="gauge",
            samples=[
                ({"status": labels["value"]}, count)
                for labels, count in count_by(session, CheckRun.status)
            ],
        ),
        Metric(
            name="aim_check_run_duration_seconds_avg",
            help_text=(
                f"Mean check run duration over the last {RECENT_WINDOW_HOURS}h; "
                "0 when nothing finished."
            ),
            metric_type="gauge",
            samples=[({}, float(recent_duration or 0.0))],
        ),
        Metric(
            name="aim_incidents_open",
            help_text=(
                "Incidents currently open, split by whether the project has been checked "
                "recently. A stale one describes the past: resolution is only evaluated "
                "on that project's next check run, so an abandoned project keeps its "
                "incidents open forever. Alert on current, not on the total."
            ),
            metric_type="gauge",
            samples=collect_open_incident_samples(session, now=current_time),
        ),
        Metric(
            name="aim_scheduled_scans_overdue",
            help_text=(
                "Opted-in verified projects whose scheduled scan is more than twice "
                "their interval late. Nonzero means the scheduler (beat) is silent — "
                "the queue metric cannot see this failure because nothing is enqueued."
            ),
            metric_type="gauge",
            samples=[({}, collect_scheduled_overdue_count(session, now=current_time))],
        ),
        Metric(
            name="aim_alerts_total",
            help_text="Alerts recorded, by delivery status.",
            metric_type="gauge",
            samples=[
                ({"status": labels["value"]}, count)
                for labels, count in count_by(session, Alert.status)
            ],
        ),
        Metric(
            name="aim_ai_reports_total",
            help_text="AI reports recorded, by which generator produced the narrative.",
            metric_type="gauge",
            samples=[
                ({"generator": labels["value"]}, count)
                for labels, count in count_by(session, AIReport.generator)
            ],
        ),
        Metric(
            name="aim_agent_investigations_total",
            help_text="Agent investigations recorded, by concluded root cause.",
            metric_type="gauge",
            samples=[
                ({"root_cause": labels["value"]}, count)
                for labels, count in count_by(session, AgentInvestigation.root_cause)
            ],
        ),
        Metric(
            name="aim_agent_feedback_total",
            help_text=(
                "User verdicts on agent investigations. Accuracy against real incidents "
                "is accurate / (accurate + inaccurate); investigations without feedback "
                "are the investigations total minus the sum of these."
            ),
            metric_type="gauge",
            samples=collect_agent_feedback_samples(session),
        ),
        Metric(
            name="aim_agent_llm_tokens_total",
            help_text=(
                "Tokens consumed by agent investigations, by model. "
                "Multiply by your price table to get spend."
            ),
            metric_type="gauge",
            samples=collect_agent_token_samples(session),
        ),
        Metric(
            name="aim_artifacts_bytes",
            help_text="Total size of stored artifacts; watch this against the retention policy.",
            metric_type="gauge",
            samples=[
                ({}, float(session.scalar(select(func.sum(Artifact.size_bytes))) or 0)),
            ],
        ),
        Metric(
            name="aim_artifacts_total",
            help_text="Artifact records stored.",
            metric_type="gauge",
            samples=[
                ({}, float(session.scalar(select(func.count()).select_from(Artifact)) or 0)),
            ],
        ),
    ]
