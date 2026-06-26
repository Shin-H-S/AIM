import ssl
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from aim_api.url_validation import ResolvedAddress
from aim_worker.ssl_inspection import inspect_ssl_certificate

VALID_CERTIFICATE = {"notAfter": "Jun 26 00:00:00 2027 GMT"}
EXPIRED_CERTIFICATE = {"notAfter": "Jun 26 00:00:00 2025 GMT"}


def public_resolver(hostname: str, port: int | None) -> list[ResolvedAddress]:
    _ = port
    return [ResolvedAddress(host=hostname, ip="8.8.8.8")]


def valid_fetcher(
    hostname: str,
    port: int,
    timeout_seconds: float,
    verify: bool,
) -> Mapping[str, Any]:
    assert hostname == "example.com"
    assert port == 443
    assert timeout_seconds > 0
    assert verify is True
    return VALID_CERTIFICATE


def test_inspect_ssl_certificate_skips_http_urls() -> None:
    result = inspect_ssl_certificate("http://example.com", resolver=public_resolver)

    assert result.is_applicable is False
    assert result.is_valid is None
    assert result.expires_at is None
    assert result.days_until_expiration is None
    assert result.failure_reason is None


def test_inspect_ssl_certificate_returns_valid_certificate_metadata() -> None:
    result = inspect_ssl_certificate(
        "https://example.com",
        resolver=public_resolver,
        certificate_fetcher=valid_fetcher,
        now=datetime(2026, 6, 26, tzinfo=UTC),
    )

    assert result.is_applicable is True
    assert result.is_valid is True
    assert result.expires_at == datetime(2027, 6, 26, tzinfo=UTC)
    assert result.days_until_expiration == 365
    assert result.failure_reason is None


def test_inspect_ssl_certificate_marks_expired_certificate_invalid() -> None:
    def expired_fetcher(
        hostname: str,
        port: int,
        timeout_seconds: float,
        verify: bool,
    ) -> Mapping[str, Any]:
        _ = hostname, port, timeout_seconds, verify
        return EXPIRED_CERTIFICATE

    result = inspect_ssl_certificate(
        "https://example.com",
        resolver=public_resolver,
        certificate_fetcher=expired_fetcher,
        now=datetime(2026, 6, 26, tzinfo=UTC),
    )

    assert result.is_valid is False
    assert result.expires_at == datetime(2025, 6, 26, tzinfo=UTC)
    assert result.days_until_expiration == -365
    assert result.failure_reason == "SSL certificate is expired."


def test_inspect_ssl_certificate_returns_metadata_after_verification_failure() -> None:
    calls: list[bool] = []

    def verification_failure_fetcher(
        hostname: str,
        port: int,
        timeout_seconds: float,
        verify: bool,
    ) -> Mapping[str, Any]:
        _ = hostname, port, timeout_seconds
        calls.append(verify)
        if verify:
            raise ssl.SSLCertVerificationError("certificate verify failed")
        return VALID_CERTIFICATE

    result = inspect_ssl_certificate(
        "https://example.com",
        resolver=public_resolver,
        certificate_fetcher=verification_failure_fetcher,
        now=datetime(2026, 6, 26, tzinfo=UTC),
    )

    assert calls == [True, False]
    assert result.is_valid is False
    assert result.expires_at == datetime(2027, 6, 26, tzinfo=UTC)
    assert result.days_until_expiration == 365
    assert result.failure_reason == "SSL certificate verification failed."


def test_inspect_ssl_certificate_blocks_unsafe_url_before_fetching_certificate() -> None:
    calls: list[str] = []

    def fetcher(
        hostname: str,
        port: int,
        timeout_seconds: float,
        verify: bool,
    ) -> Mapping[str, Any]:
        _ = port, timeout_seconds, verify
        calls.append(hostname)
        return VALID_CERTIFICATE

    result = inspect_ssl_certificate(
        "https://127.0.0.1",
        certificate_fetcher=fetcher,
        now=datetime(2026, 6, 26, tzinfo=UTC),
    )

    assert calls == []
    assert result.is_valid is False
    assert result.failure_reason == "Service URL is not allowed."
