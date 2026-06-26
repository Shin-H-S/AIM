import socket
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from aim_api.config import get_settings
from aim_api.url_validation import AddressResolver, UrlValidationError, validate_service_url

CertificateFetcher = Callable[[str, int, float, bool], Mapping[str, Any]]


@dataclass(frozen=True)
class SslInspectionResult:
    service_url: str
    is_applicable: bool
    is_valid: bool | None
    expires_at: datetime | None
    days_until_expiration: int | None
    failure_reason: str | None


def inspect_ssl_certificate(
    service_url: str,
    *,
    resolver: AddressResolver | None = None,
    certificate_fetcher: CertificateFetcher | None = None,
    now: datetime | None = None,
) -> SslInspectionResult:
    parsed_url = urlparse(service_url)
    if parsed_url.scheme.lower() != "https":
        return SslInspectionResult(
            service_url=service_url,
            is_applicable=False,
            is_valid=None,
            expires_at=None,
            days_until_expiration=None,
            failure_reason=None,
        )

    try:
        validate_service_url(service_url, resolver=resolver)
    except UrlValidationError:
        return invalid_result(
            service_url=service_url,
            failure_reason="Service URL is not allowed.",
        )

    hostname = parsed_url.hostname
    if hostname is None:
        return invalid_result(
            service_url=service_url,
            failure_reason="Service URL must include a hostname.",
        )

    try:
        port = parsed_url.port or 443
    except ValueError:
        return invalid_result(
            service_url=service_url,
            failure_reason="Service URL port is invalid.",
        )

    timeout_seconds = get_settings().ssl_inspection_timeout_seconds
    fetch_certificate = certificate_fetcher or fetch_peer_certificate
    inspected_at = now or datetime.now(UTC)

    try:
        certificate = fetch_certificate(hostname, port, timeout_seconds, True)
    except ssl.SSLCertVerificationError:
        return inspect_unverified_certificate_after_verification_failure(
            service_url=service_url,
            hostname=hostname,
            port=port,
            timeout_seconds=timeout_seconds,
            fetch_certificate=fetch_certificate,
            inspected_at=inspected_at,
        )
    except (OSError, ssl.SSLError):
        return invalid_result(
            service_url=service_url,
            failure_reason="SSL certificate inspection failed.",
        )

    return build_ssl_result(
        service_url=service_url,
        certificate=certificate,
        inspected_at=inspected_at,
        verification_failed=False,
    )


def inspect_unverified_certificate_after_verification_failure(
    *,
    service_url: str,
    hostname: str,
    port: int,
    timeout_seconds: float,
    fetch_certificate: CertificateFetcher,
    inspected_at: datetime,
) -> SslInspectionResult:
    try:
        certificate = fetch_certificate(hostname, port, timeout_seconds, False)
    except (OSError, ssl.SSLError):
        return invalid_result(
            service_url=service_url,
            failure_reason="SSL certificate verification failed.",
        )

    return build_ssl_result(
        service_url=service_url,
        certificate=certificate,
        inspected_at=inspected_at,
        verification_failed=True,
    )


def fetch_peer_certificate(
    hostname: str,
    port: int,
    timeout_seconds: float,
    verify: bool,
) -> Mapping[str, Any]:
    context = ssl.create_default_context() if verify else ssl._create_unverified_context()
    with (
        socket.create_connection((hostname, port), timeout=timeout_seconds) as tcp_socket,
        context.wrap_socket(tcp_socket, server_hostname=hostname) as tls_socket,
    ):
        certificate = tls_socket.getpeercert()
        if not certificate:
            raise ssl.SSLError("Peer did not provide a certificate.")
        return certificate


def build_ssl_result(
    *,
    service_url: str,
    certificate: Mapping[str, Any],
    inspected_at: datetime,
    verification_failed: bool,
) -> SslInspectionResult:
    expires_at = parse_certificate_expiration(certificate)
    if expires_at is None:
        return invalid_result(
            service_url=service_url,
            failure_reason="SSL certificate expiration date is unavailable.",
        )

    days_until_expiration = calculate_days_until_expiration(expires_at, inspected_at)
    if verification_failed:
        return SslInspectionResult(
            service_url=service_url,
            is_applicable=True,
            is_valid=False,
            expires_at=expires_at,
            days_until_expiration=days_until_expiration,
            failure_reason="SSL certificate verification failed.",
        )

    if expires_at <= inspected_at:
        return SslInspectionResult(
            service_url=service_url,
            is_applicable=True,
            is_valid=False,
            expires_at=expires_at,
            days_until_expiration=days_until_expiration,
            failure_reason="SSL certificate is expired.",
        )

    return SslInspectionResult(
        service_url=service_url,
        is_applicable=True,
        is_valid=True,
        expires_at=expires_at,
        days_until_expiration=days_until_expiration,
        failure_reason=None,
    )


def parse_certificate_expiration(certificate: Mapping[str, Any]) -> datetime | None:
    not_after = certificate.get("notAfter")
    if not isinstance(not_after, str):
        return None

    try:
        timestamp = ssl.cert_time_to_seconds(not_after)
    except (TypeError, ValueError):
        return None

    return datetime.fromtimestamp(timestamp, UTC)


def calculate_days_until_expiration(expires_at: datetime, inspected_at: datetime) -> int:
    return (expires_at - inspected_at).days


def invalid_result(*, service_url: str, failure_reason: str) -> SslInspectionResult:
    return SslInspectionResult(
        service_url=service_url,
        is_applicable=True,
        is_valid=False,
        expires_at=None,
        days_until_expiration=None,
        failure_reason=failure_reason,
    )
