import httpx
import pytest
from aim_api.url_validation import ResolvedAddress
from aim_worker.availability import scan_http_availability


def public_resolver(hostname: str, port: int | None) -> list[ResolvedAddress]:
    _ = port
    return [ResolvedAddress(host=hostname, ip="8.8.8.8")]


def test_scan_http_availability_returns_success_for_2xx_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "AIM Availability Scanner/0.1"
        return httpx.Response(200, request=request, content=b"ok")

    result = scan_http_availability(
        "https://example.com",
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )

    assert result.is_available is True
    assert result.status_code == 200
    assert result.final_url == "https://example.com"
    assert result.redirect_count == 0
    assert result.uses_https is True
    assert result.timed_out is False
    assert result.failure_reason is None
    assert result.response_time_ms is not None


def test_scan_http_availability_revalidates_redirect_destination() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://example.com":
            return httpx.Response(
                302,
                request=request,
                headers={"location": "http://127.0.0.1/internal"},
            )

        pytest.fail(f"Unsafe redirect should not be requested: {request.url}")

    result = scan_http_availability(
        "https://example.com",
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )

    assert result.is_available is False
    assert result.status_code == 302
    assert result.redirect_count == 1
    assert result.failure_reason == "Redirect destination is not allowed."


def test_scan_http_availability_follows_safe_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://example.com":
            return httpx.Response(
                301,
                request=request,
                headers={"location": "/health"},
            )
        if str(request.url) == "https://example.com/health":
            return httpx.Response(204, request=request)

        pytest.fail(f"Unexpected request: {request.url}")

    result = scan_http_availability(
        "https://example.com",
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )

    assert result.is_available is True
    assert result.status_code == 204
    assert result.final_url == "https://example.com/health"
    assert result.redirect_count == 1


def test_scan_http_availability_fails_for_5xx_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    result = scan_http_availability(
        "https://example.com",
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )

    assert result.is_available is False
    assert result.status_code == 503
    assert result.failure_reason == "Service returned HTTP 503."


def test_scan_http_availability_records_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    result = scan_http_availability(
        "https://example.com",
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )

    assert result.is_available is False
    assert result.status_code is None
    assert result.timed_out is True
    assert result.failure_reason == "Service request timed out."
