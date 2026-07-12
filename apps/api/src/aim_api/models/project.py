from datetime import UTC, datetime
from secrets import token_urlsafe
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy import (
    false as sa_false,
)
from sqlalchemy.orm import Mapped, mapped_column

from aim_api.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def generate_verification_token() -> str:
    return f"aim_verify_{token_urlsafe(24)}"


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "environment IN ('development', 'staging', 'production')",
            name="ck_projects_environment",
        ),
        CheckConstraint(
            "scoring_preset IN ('service', 'content', 'internal')",
            name="ck_projects_scoring_preset",
        ),
        CheckConstraint("scan_interval_minutes > 0", name="ck_projects_scan_interval_positive"),
        CheckConstraint(
            "response_time_threshold_ms > 0",
            name="ck_projects_response_time_threshold_positive",
        ),
        CheckConstraint(
            "quality_score_threshold >= 0 AND quality_score_threshold <= 100",
            name="ck_projects_quality_score_threshold_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    service_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    verification_token: Mapped[str | None] = mapped_column(
        String(128),
        unique=True,
        index=True,
        default=generate_verification_token,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="development")
    # 서비스 성격별 카테고리 가중치 프리셋. 다음 검사부터 적용되며 과거 점수는 유지된다.
    scoring_preset: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="service",
        server_default="service",
    )
    scan_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    scheduled_scans_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sa_false(),
    )
    response_time_threshold_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    quality_score_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=80)
    alert_email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alert_recipient_email: Mapped[str | None] = mapped_column(String(320))
    # Slack/Discord incoming webhook. A non-null value enables the WEBHOOK alert channel.
    alert_webhook_url: Mapped[str | None] = mapped_column(String(1024))
    # No DB foreign key: projects <-> check_runs would form a circular table
    # dependency. Integrity is enforced in the projects service on assignment.
    baseline_check_run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=func.now(),
    )

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None
