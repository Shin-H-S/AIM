from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.scanner_result import AvailabilityResult, LighthouseResult, SslResult


def record_availability_result(
    session: Session,
    *,
    check_run_id: UUID,
    service_url: str,
    final_url: str | None,
    is_available: bool,
    status_code: int | None,
    response_time_ms: int | None,
    redirect_count: int,
    uses_https: bool,
    timed_out: bool,
    failure_reason: str | None,
) -> AvailabilityResult:
    result = get_availability_result(session, check_run_id=check_run_id)
    if result is None:
        result = AvailabilityResult(check_run_id=check_run_id)
        session.add(result)

    result.service_url = service_url
    result.final_url = final_url
    result.is_available = is_available
    result.status_code = status_code
    result.response_time_ms = response_time_ms
    result.redirect_count = redirect_count
    result.uses_https = uses_https
    result.timed_out = timed_out
    result.failure_reason = failure_reason
    session.commit()
    session.refresh(result)
    return result


def record_ssl_result(
    session: Session,
    *,
    check_run_id: UUID,
    service_url: str,
    is_applicable: bool,
    is_valid: bool | None,
    expires_at: datetime | None,
    days_until_expiration: int | None,
    failure_reason: str | None,
) -> SslResult:
    result = get_ssl_result(session, check_run_id=check_run_id)
    if result is None:
        result = SslResult(check_run_id=check_run_id)
        session.add(result)

    result.service_url = service_url
    result.is_applicable = is_applicable
    result.is_valid = is_valid
    result.expires_at = expires_at
    result.days_until_expiration = days_until_expiration
    result.failure_reason = failure_reason
    session.commit()
    session.refresh(result)
    return result


def record_lighthouse_result(
    session: Session,
    *,
    check_run_id: UUID,
    service_url: str,
    is_successful: bool,
    performance_score: int | None,
    accessibility_score: int | None,
    seo_score: int | None,
    best_practices_score: int | None,
    largest_contentful_paint_ms: int | None,
    cumulative_layout_shift: float | None,
    total_blocking_time_ms: int | None,
    raw_json_artifact_id: UUID | None,
    failure_reason: str | None,
) -> LighthouseResult:
    result = get_lighthouse_result(session, check_run_id=check_run_id)
    if result is None:
        result = LighthouseResult(check_run_id=check_run_id)
        session.add(result)

    result.service_url = service_url
    result.is_successful = is_successful
    result.performance_score = performance_score
    result.accessibility_score = accessibility_score
    result.seo_score = seo_score
    result.best_practices_score = best_practices_score
    result.largest_contentful_paint_ms = largest_contentful_paint_ms
    result.cumulative_layout_shift = cumulative_layout_shift
    result.total_blocking_time_ms = total_blocking_time_ms
    result.raw_json_artifact_id = raw_json_artifact_id
    result.failure_reason = failure_reason
    session.commit()
    session.refresh(result)
    return result


def get_availability_result(
    session: Session,
    *,
    check_run_id: UUID,
) -> AvailabilityResult | None:
    return session.scalar(
        select(AvailabilityResult).where(AvailabilityResult.check_run_id == check_run_id)
    )


def get_ssl_result(
    session: Session,
    *,
    check_run_id: UUID,
) -> SslResult | None:
    return session.scalar(select(SslResult).where(SslResult.check_run_id == check_run_id))


def get_lighthouse_result(
    session: Session,
    *,
    check_run_id: UUID,
) -> LighthouseResult | None:
    return session.scalar(
        select(LighthouseResult).where(LighthouseResult.check_run_id == check_run_id)
    )
