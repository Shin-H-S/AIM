import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from aim_api.url_validation import ResolvedAddress
from aim_worker.lighthouse import run_lighthouse_scan


def public_resolver(hostname: str, port: int | None) -> list[ResolvedAddress]:
    _ = port
    return [ResolvedAddress(host=hostname, ip="8.8.8.8")]


def get_output_path(command: Sequence[str]) -> Path:
    for item in command:
        if item.startswith("--output-path="):
            return Path(item.removeprefix("--output-path="))

    raise AssertionError("Lighthouse command did not include --output-path.")


def write_lighthouse_payload(output_path: Path) -> None:
    output_path.write_text(
        json.dumps(
            {
                "categories": {
                    "performance": {"score": 0.92},
                    "accessibility": {"score": 1.0},
                    "seo": {"score": 0.87},
                    "best-practices": {"score": 0.75},
                },
                "audits": {
                    "largest-contentful-paint": {"numericValue": 1234.4},
                    "cumulative-layout-shift": {"numericValue": 0.03},
                    "total-blocking-time": {"numericValue": 45.6},
                },
            }
        ),
        encoding="utf-8",
    )


def test_run_lighthouse_scan_parses_mobile_lighthouse_output() -> None:
    captured_command: list[str] = []

    def runner(command: Sequence[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        captured_command.extend(command)
        assert timeout_seconds > 0
        write_lighthouse_payload(get_output_path(command))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = run_lighthouse_scan(
        "https://example.com",
        resolver=public_resolver,
        runner=runner,
    )

    assert result.is_successful is True
    assert result.performance_score == 92
    assert result.accessibility_score == 100
    assert result.seo_score == 87
    assert result.best_practices_score == 75
    assert result.largest_contentful_paint_ms == 1234
    assert result.cumulative_layout_shift == 0.03
    assert result.total_blocking_time_ms == 46
    assert result.failure_reason is None
    assert "--form-factor=mobile" in captured_command
    assert "--only-categories=performance,accessibility,best-practices,seo" in captured_command


def test_run_lighthouse_scan_rejects_unsafe_url_before_running_cli() -> None:
    calls: list[Sequence[str]] = []

    def runner(command: Sequence[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        _ = timeout_seconds
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = run_lighthouse_scan("https://127.0.0.1", runner=runner)

    assert calls == []
    assert result.is_successful is False
    assert result.failure_reason == "Service URL is not allowed."


def test_run_lighthouse_scan_records_missing_cli() -> None:
    def runner(command: Sequence[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        _ = command, timeout_seconds
        raise FileNotFoundError

    result = run_lighthouse_scan(
        "https://example.com",
        resolver=public_resolver,
        runner=runner,
    )

    assert result.is_successful is False
    assert result.failure_reason == "Lighthouse CLI is not available."


def test_run_lighthouse_scan_records_cli_failure() -> None:
    def runner(command: Sequence[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        _ = timeout_seconds
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")

    result = run_lighthouse_scan(
        "https://example.com",
        resolver=public_resolver,
        runner=runner,
    )

    assert result.is_successful is False
    assert result.failure_reason == "Lighthouse CLI failed."


def test_run_lighthouse_scan_records_timeout() -> None:
    def runner(command: Sequence[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout_seconds)

    result = run_lighthouse_scan(
        "https://example.com",
        resolver=public_resolver,
        runner=runner,
    )

    assert result.is_successful is False
    assert result.failure_reason == "Lighthouse scan timed out."


def test_run_lighthouse_scan_prefers_report_over_nonzero_exit_code() -> None:
    def runner(command: Sequence[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
        _ = timeout_seconds
        write_lighthouse_payload(get_output_path(command))
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="cleanup failed")

    result = run_lighthouse_scan(
        "https://example.com",
        resolver=public_resolver,
        runner=runner,
    )

    assert result.is_successful is True
    assert result.performance_score == 92
    assert result.failure_reason is None
