from datetime import UTC, datetime
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
from sqlalchemy.orm import Mapped, mapped_column

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
