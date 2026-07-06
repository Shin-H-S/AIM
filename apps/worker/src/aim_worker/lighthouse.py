import json
import logging
import shlex
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from aim_api.config import get_settings
from aim_api.url_validation import AddressResolver, UrlValidationError, validate_service_url

logger = logging.getLogger(__name__)

CommandRunner = Callable[[Sequence[str], int], subprocess.CompletedProcess[str]]

STDERR_LOG_MAX_LENGTH = 2000


@dataclass(frozen=True)
class LighthouseScanResult:
    service_url: str
    is_successful: bool
    performance_score: int | None
    accessibility_score: int | None
    seo_score: int | None
    best_practices_score: int | None
    largest_contentful_paint_ms: int | None
    cumulative_layout_shift: float | None
    total_blocking_time_ms: int | None
    raw_json: dict[str, Any] | None
    failure_reason: str | None


def run_lighthouse_scan(
    service_url: str,
    *,
    resolver: AddressResolver | None = None,
    runner: CommandRunner | None = None,
) -> LighthouseScanResult:
    try:
        validate_service_url(service_url, resolver=resolver)
    except UrlValidationError:
        return failed_lighthouse_result(service_url, "Service URL is not allowed.")

    settings = get_settings()
    command_runner = runner or run_lighthouse_command

    with NamedTemporaryFile(suffix=".json", delete=False) as output_file:
        output_path = Path(output_file.name)

    command = build_lighthouse_command(
        lighthouse_command=settings.lighthouse_command,
        service_url=service_url,
        output_path=output_path,
    )

    try:
        try:
            completed_process = command_runner(command, settings.lighthouse_timeout_seconds)
        except FileNotFoundError:
            return failed_lighthouse_result(service_url, "Lighthouse CLI is not available.")
        except subprocess.TimeoutExpired:
            return failed_lighthouse_result(service_url, "Lighthouse scan timed out.")

        # The CLI can exit non-zero after writing a complete report (for example
        # chrome-launcher's temp-profile cleanup fails on Windows), so the output
        # file is the source of truth and the exit code only matters without one.
        try:
            raw_json = parse_lighthouse_output(output_path)
        except (JSONDecodeError, OSError):
            stderr_tail = (completed_process.stderr or "")[-STDERR_LOG_MAX_LENGTH:]

            if completed_process.returncode != 0:
                logger.error(
                    "Lighthouse CLI failed for %s (exit code %d): %s",
                    service_url,
                    completed_process.returncode,
                    stderr_tail,
                )
                return failed_lighthouse_result(service_url, "Lighthouse CLI failed.")

            logger.error(
                "Lighthouse output could not be parsed for %s: %s",
                service_url,
                stderr_tail,
            )
            return failed_lighthouse_result(service_url, "Lighthouse output could not be parsed.")
    finally:
        output_path.unlink(missing_ok=True)

    return LighthouseScanResult(
        service_url=service_url,
        is_successful=True,
        performance_score=read_category_score(raw_json, "performance"),
        accessibility_score=read_category_score(raw_json, "accessibility"),
        seo_score=read_category_score(raw_json, "seo"),
        best_practices_score=read_category_score(raw_json, "best-practices"),
        largest_contentful_paint_ms=read_audit_numeric_value(
            raw_json,
            "largest-contentful-paint",
        ),
        cumulative_layout_shift=read_audit_float_value(raw_json, "cumulative-layout-shift"),
        total_blocking_time_ms=read_audit_numeric_value(raw_json, "total-blocking-time"),
        raw_json=raw_json,
        failure_reason=None,
    )


def build_lighthouse_command(
    *,
    lighthouse_command: str,
    service_url: str,
    output_path: Path,
) -> list[str]:
    base_command = shlex.split(lighthouse_command)
    return [
        *base_command,
        service_url,
        "--output=json",
        f"--output-path={output_path}",
        "--quiet",
        "--only-categories=performance,accessibility,best-practices,seo",
        "--form-factor=mobile",
        "--screenEmulation.mobile=true",
        # --no-sandbox / --disable-dev-shm-usage: Chromium cannot create its
        # sandbox under Docker's default seccomp profile (no unprivileged user
        # namespaces) and the default 64MB /dev/shm is too small for rendering;
        # the worker container itself is the isolation boundary.
        "--chrome-flags=--headless=new --disable-gpu --no-sandbox --disable-dev-shm-usage",
    ]


def run_lighthouse_command(
    command: Sequence[str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def parse_lighthouse_output(output_path: Path) -> dict[str, Any]:
    with output_path.open(encoding="utf-8") as output_file:
        payload = json.load(output_file)

    if not isinstance(payload, dict):
        raise JSONDecodeError("Lighthouse output must be a JSON object.", "", 0)

    return payload


def read_category_score(raw_json: dict[str, Any], category_id: str) -> int | None:
    categories = raw_json.get("categories")
    if not isinstance(categories, dict):
        return None

    category = categories.get(category_id)
    if not isinstance(category, dict):
        return None

    score = category.get("score")
    if not isinstance(score, int | float):
        return None

    return round(float(score) * 100)


def read_audit_numeric_value(raw_json: dict[str, Any], audit_id: str) -> int | None:
    value = read_audit_value(raw_json, audit_id)
    return round(value) if value is not None else None


def read_audit_float_value(raw_json: dict[str, Any], audit_id: str) -> float | None:
    return read_audit_value(raw_json, audit_id)


def read_audit_value(raw_json: dict[str, Any], audit_id: str) -> float | None:
    audits = raw_json.get("audits")
    if not isinstance(audits, dict):
        return None

    audit = audits.get(audit_id)
    if not isinstance(audit, dict):
        return None

    value = audit.get("numericValue")
    if not isinstance(value, int | float):
        return None

    return float(value)


def failed_lighthouse_result(service_url: str, failure_reason: str) -> LighthouseScanResult:
    return LighthouseScanResult(
        service_url=service_url,
        is_successful=False,
        performance_score=None,
        accessibility_score=None,
        seo_score=None,
        best_practices_score=None,
        largest_contentful_paint_ms=None,
        cumulative_layout_shift=None,
        total_blocking_time_ms=None,
        raw_json=None,
        failure_reason=failure_reason,
    )
