import pytest
from aim_api.url_validation import ResolvedAddress, UrlValidationError, validate_service_url


def public_resolver(hostname: str, port: int | None) -> list[ResolvedAddress]:
    return [ResolvedAddress(host=hostname, ip="93.184.216.34")]


def private_resolver(hostname: str, port: int | None) -> list[ResolvedAddress]:
    return [ResolvedAddress(host=hostname, ip="10.0.0.10")]


def mixed_resolver(hostname: str, port: int | None) -> list[ResolvedAddress]:
    return [
        ResolvedAddress(host=hostname, ip="93.184.216.34"),
        ResolvedAddress(host=hostname, ip="10.0.0.10"),
    ]


def empty_resolver(hostname: str, port: int | None) -> list[ResolvedAddress]:
    return []


def test_validate_service_url_accepts_public_http_url() -> None:
    validate_service_url("https://example.com", resolver=public_resolver)


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/aim",
        "ftp://example.com",
        "https://user:password@example.com",
        "https://localhost",
        "https://app.localhost",
        "https://metadata",
        "https://metadata.google.internal",
        "http://127.0.0.1",
        "http://0.0.0.0",
        "http://10.0.0.1",
        "http://172.16.0.1",
        "http://192.168.0.1",
        "http://169.254.169.254",
        "http://169.254.170.2",
        "http://100.100.100.200",
        "http://224.0.0.1",
        "http://[::1]",
        "http://[fe80::1]",
    ],
)
def test_validate_service_url_rejects_unsafe_hosts(url: str) -> None:
    with pytest.raises(UrlValidationError):
        validate_service_url(url, resolver=public_resolver)


def test_validate_service_url_rejects_private_dns_result() -> None:
    with pytest.raises(UrlValidationError):
        validate_service_url("https://example.com", resolver=private_resolver)


def test_validate_service_url_rejects_mixed_public_and_private_dns_results() -> None:
    with pytest.raises(UrlValidationError):
        validate_service_url("https://example.com", resolver=mixed_resolver)


def test_validate_service_url_rejects_unresolved_hostname() -> None:
    with pytest.raises(UrlValidationError):
        validate_service_url("https://example.com", resolver=empty_resolver)
