from collections.abc import Iterable
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import urljoin

import httpx
from aim_api.config import get_settings
from aim_api.url_validation import AddressResolver, UrlValidationError, validate_service_url

AIM_SCANNER_USER_AGENT = "AIM Availability Scanner/0.1"
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True)
class AvailabilityScanResult:
    service_url: str
    final_url: str | None
    is_available: bool
    status_code: int | None
    response_time_ms: int | None
    redirect_count: int
    uses_https: bool
    timed_out: bool
    failure_reason: str | None


def scan_http_availability(
    service_url: str,
    *,
    resolver: AddressResolver | None = None,
    transport: httpx.BaseTransport | None = None,
) -> AvailabilityScanResult:
    settings = get_settings()
    timeout_seconds = settings.scanner_timeout_seconds
    max_redirects = settings.scanner_max_redirects
    max_response_bytes = settings.scanner_max_response_bytes

    started_at = perf_counter()
    current_url = service_url
    redirect_count = 0

    try:
        validate_service_url(current_url, resolver=resolver)
    except UrlValidationError:
        return unavailable_result(
            service_url=service_url,
            final_url=None,
            status_code=None,
            response_time_ms=elapsed_ms(started_at),
            redirect_count=0,
            uses_https=current_url.lower().startswith("https://"),
            timed_out=False,
            failure_reason="Service URL is not allowed.",
        )

    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            headers={"User-Agent": AIM_SCANNER_USER_AGENT},
        ) as client:
            while True:
                try:
                    response = fetch_limited_response(client, current_url, max_response_bytes)
                except httpx.TimeoutException:
                    return unavailable_result(
                        service_url=service_url,
                        final_url=current_url,
                        status_code=None,
                        response_time_ms=elapsed_ms(started_at),
                        redirect_count=redirect_count,
                        uses_https=current_url.lower().startswith("https://"),
                        timed_out=True,
                        failure_reason="Service request timed out.",
                    )
                except httpx.RequestError:
                    return unavailable_result(
                        service_url=service_url,
                        final_url=current_url,
                        status_code=None,
                        response_time_ms=elapsed_ms(started_at),
                        redirect_count=redirect_count,
                        uses_https=current_url.lower().startswith("https://"),
                        timed_out=False,
                        failure_reason="Service request failed.",
                    )

                location = response.headers.get("location")
                if response.status_code in REDIRECT_STATUS_CODES and location:
                    if redirect_count >= max_redirects:
                        return unavailable_result(
                            service_url=service_url,
                            final_url=str(response.url),
                            status_code=response.status_code,
                            response_time_ms=elapsed_ms(started_at),
                            redirect_count=redirect_count,
                            uses_https=str(response.url).lower().startswith("https://"),
                            timed_out=False,
                            failure_reason="Service exceeded the redirect limit.",
                        )

                    redirected_url = urljoin(str(response.url), location)
                    try:
                        validate_service_url(redirected_url, resolver=resolver)
                    except UrlValidationError:
                        return unavailable_result(
                            service_url=service_url,
                            final_url=redirected_url,
                            status_code=response.status_code,
                            response_time_ms=elapsed_ms(started_at),
                            redirect_count=redirect_count + 1,
                            uses_https=redirected_url.lower().startswith("https://"),
                            timed_out=False,
                            failure_reason="Redirect destination is not allowed.",
                        )

                    current_url = redirected_url
                    redirect_count += 1
                    continue

                is_available = 200 <= response.status_code < 400
                return AvailabilityScanResult(
                    service_url=service_url,
                    final_url=str(response.url),
                    is_available=is_available,
                    status_code=response.status_code,
                    response_time_ms=elapsed_ms(started_at),
                    redirect_count=redirect_count,
                    uses_https=str(response.url).lower().startswith("https://"),
                    timed_out=False,
                    failure_reason=None
                    if is_available
                    else f"Service returned HTTP {response.status_code}.",
                )
    except httpx.HTTPError:
        return unavailable_result(
            service_url=service_url,
            final_url=current_url,
            status_code=None,
            response_time_ms=elapsed_ms(started_at),
            redirect_count=redirect_count,
            uses_https=current_url.lower().startswith("https://"),
            timed_out=False,
            failure_reason="Service request failed.",
        )


def fetch_limited_response(
    client: httpx.Client,
    url: str,
    max_response_bytes: int,
) -> httpx.Response:
    with client.stream("GET", url) as response:
        consume_limited_body(response.iter_bytes(), max_response_bytes)
        return response


def consume_limited_body(chunks: Iterable[bytes], max_response_bytes: int) -> None:
    consumed_bytes = 0
    for chunk in chunks:
        consumed_bytes += len(chunk)
        if consumed_bytes > max_response_bytes:
            break


def unavailable_result(
    *,
    service_url: str,
    final_url: str | None,
    status_code: int | None,
    response_time_ms: int | None,
    redirect_count: int,
    uses_https: bool,
    timed_out: bool,
    failure_reason: str,
) -> AvailabilityScanResult:
    return AvailabilityScanResult(
        service_url=service_url,
        final_url=final_url,
        is_available=False,
        status_code=status_code,
        response_time_ms=response_time_ms,
        redirect_count=redirect_count,
        uses_https=uses_https,
        timed_out=timed_out,
        failure_reason=failure_reason,
    )


def elapsed_ms(started_at: float) -> int:
    return max(round((perf_counter() - started_at) * 1000), 0)
