from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aim_api.database import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class AvailabilityResult(Base):
    __tablename__ = "availability_results"
    __table_args__ = (
        CheckConstraint(
            "response_time_ms IS NULL OR response_time_ms >= 0",
            name="ck_availability_results_response_time_non_negative",
        ),
        CheckConstraint(
            "redirect_count >= 0",
            name="ck_availability_results_redirect_count_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    check_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("check_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    service_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str | None] = mapped_column(String(2048))
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    redirect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uses_https: Mapped[bool] = mapped_column(Boolean, nullable=False)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
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


class SslResult(Base):
    __tablename__ = "ssl_results"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    check_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("check_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    service_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    is_applicable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_valid: Mapped[bool | None] = mapped_column(Boolean)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    days_until_expiration: Mapped[int | None] = mapped_column(Integer)
    failure_reason: Mapped[str | None] = mapped_column(Text)
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


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(
            "size_bytes >= 0",
            name="ck_artifacts_size_bytes_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    check_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("check_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=func.now(),
    )


class LighthouseResult(Base):
    __tablename__ = "lighthouse_results"
    __table_args__ = (
        CheckConstraint(
            "performance_score IS NULL OR (performance_score >= 0 AND performance_score <= 100)",
            name="ck_lighthouse_results_performance_score_range",
        ),
        CheckConstraint(
            "accessibility_score IS NULL OR "
            "(accessibility_score >= 0 AND accessibility_score <= 100)",
            name="ck_lighthouse_results_accessibility_score_range",
        ),
        CheckConstraint(
            "seo_score IS NULL OR (seo_score >= 0 AND seo_score <= 100)",
            name="ck_lighthouse_results_seo_score_range",
        ),
        CheckConstraint(
            "best_practices_score IS NULL OR "
            "(best_practices_score >= 0 AND best_practices_score <= 100)",
            name="ck_lighthouse_results_best_practices_score_range",
        ),
        CheckConstraint(
            "largest_contentful_paint_ms IS NULL OR largest_contentful_paint_ms >= 0",
            name="ck_lighthouse_results_lcp_non_negative",
        ),
        CheckConstraint(
            "cumulative_layout_shift IS NULL OR cumulative_layout_shift >= 0",
            name="ck_lighthouse_results_cls_non_negative",
        ),
        CheckConstraint(
            "total_blocking_time_ms IS NULL OR total_blocking_time_ms >= 0",
            name="ck_lighthouse_results_tbt_non_negative",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    check_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("check_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    service_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    is_successful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    performance_score: Mapped[int | None] = mapped_column(Integer)
    accessibility_score: Mapped[int | None] = mapped_column(Integer)
    seo_score: Mapped[int | None] = mapped_column(Integer)
    best_practices_score: Mapped[int | None] = mapped_column(Integer)
    largest_contentful_paint_ms: Mapped[int | None] = mapped_column(Integer)
    cumulative_layout_shift: Mapped[float | None] = mapped_column(Float)
    total_blocking_time_ms: Mapped[int | None] = mapped_column(Integer)
    raw_json_artifact_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="SET NULL"),
        index=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    raw_json_artifact: Mapped[Artifact | None] = relationship()
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


class ScoreResult(Base):
    __tablename__ = "score_results"
    __table_args__ = (
        CheckConstraint(
            "availability_score IS NULL OR (availability_score >= 0 AND availability_score <= 100)",
            name="ck_score_results_availability_score_range",
        ),
        CheckConstraint(
            "functional_stability_score IS NULL OR "
            "(functional_stability_score >= 0 AND functional_stability_score <= 100)",
            name="ck_score_results_functional_stability_score_range",
        ),
        CheckConstraint(
            "web_performance_score IS NULL OR "
            "(web_performance_score >= 0 AND web_performance_score <= 100)",
            name="ck_score_results_web_performance_score_range",
        ),
        CheckConstraint(
            "accessibility_score IS NULL OR "
            "(accessibility_score >= 0 AND accessibility_score <= 100)",
            name="ck_score_results_accessibility_score_range",
        ),
        CheckConstraint(
            "seo_basic_quality_score IS NULL OR "
            "(seo_basic_quality_score >= 0 AND seo_basic_quality_score <= 100)",
            name="ck_score_results_seo_basic_quality_score_range",
        ),
        CheckConstraint(
            "regression_stability_score IS NULL OR "
            "(regression_stability_score >= 0 AND regression_stability_score <= 100)",
            name="ck_score_results_regression_stability_score_range",
        ),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_score_results_overall_score_range",
        ),
        CheckConstraint(
            "evaluated_weight >= 0 AND evaluated_weight <= 100",
            name="ck_score_results_evaluated_weight_range",
        ),
        CheckConstraint(
            "grade IN ('A', 'B', 'C', 'D', 'F')",
            name="ck_score_results_grade",
        ),
        CheckConstraint(
            "deployment_risk IN ('STABLE', 'WARNING', 'RISK')",
            name="ck_score_results_deployment_risk",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    check_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("check_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    availability_score: Mapped[int | None] = mapped_column(Integer)
    functional_stability_score: Mapped[int | None] = mapped_column(Integer)
    web_performance_score: Mapped[int | None] = mapped_column(Integer)
    accessibility_score: Mapped[int | None] = mapped_column(Integer)
    seo_basic_quality_score: Mapped[int | None] = mapped_column(Integer)
    regression_stability_score: Mapped[int | None] = mapped_column(Integer)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_weight: Mapped[int] = mapped_column(Integer, nullable=False)
    grade: Mapped[str] = mapped_column(String(1), nullable=False)
    deployment_risk: Mapped[str] = mapped_column(String(16), nullable=False)
    gate_reason: Mapped[str | None] = mapped_column(Text)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)
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
