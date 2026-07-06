import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from aim_api.url_validation import ResolvedAddress
from aim_worker.lighthouse import extract_top_audits, run_lighthouse_scan


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
                    "performance": {
                        "score": 0.92,
                        "auditRefs": [
                            {"id": "largest-contentful-paint", "weight": 25},
                            {"id": "render-blocking-resources", "weight": 5},
                        ],
                    },
                    "accessibility": {
                        "score": 1.0,
                        "auditRefs": [{"id": "color-contrast", "weight": 3}],
                    },
                    "seo": {
                        "score": 0.87,
                        "auditRefs": [{"id": "meta-description", "weight": 1}],
                    },
                    "best-practices": {"score": 0.75, "auditRefs": []},
                },
                "audits": {
                    "largest-contentful-paint": {"numericValue": 1234.4, "score": 0.95},
                    "cumulative-layout-shift": {"numericValue": 0.03},
                    "total-blocking-time": {"numericValue": 45.6},
                    "render-blocking-resources": {
                        "score": 0.4,
                        "scoreDisplayMode": "metricSavings",
                        "title": "렌더링 차단 리소스 제거하기",
                        "displayValue": "잠재적 절감치: 1,860ms",
                        "details": {"overallSavingsMs": 1860.4, "overallSavingsBytes": 120000},
                    },
                    "color-contrast": {
                        "score": 0,
                        "scoreDisplayMode": "binary",
                        "title": "배경색과 전경색의 대비가 충분하지 않습니다.",
                    },
                    "meta-description": {
                        "score": 0,
                        "scoreDisplayMode": "binary",
                        "title": "문서에 메타 설명이 없습니다.",
                    },
                },
            },
            ensure_ascii=False,
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
    assert result.top_audits == [
        {
            "id": "render-blocking-resources",
            "category": "performance",
            "title": "렌더링 차단 리소스 제거하기",
            "display_value": "잠재적 절감치: 1,860ms",
            "score": 0.4,
            "savings_ms": 1860,
            "savings_bytes": 120000,
        },
        {
            "id": "color-contrast",
            "category": "accessibility",
            "title": "배경색과 전경색의 대비가 충분하지 않습니다.",
            "display_value": None,
            "score": 0.0,
            "savings_ms": None,
            "savings_bytes": None,
        },
        {
            "id": "meta-description",
            "category": "seo",
            "title": "문서에 메타 설명이 없습니다.",
            "display_value": None,
            "score": 0.0,
            "savings_ms": None,
            "savings_bytes": None,
        },
    ]
    assert "--form-factor=mobile" in captured_command
    assert "--only-categories=performance,accessibility,best-practices,seo" in captured_command
    assert "--locale=ko" in captured_command


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


def test_extract_top_audits_ranks_savings_then_score() -> None:
    raw_json = {
        "categories": {
            "performance": {
                "auditRefs": [
                    {"id": "small-savings"},
                    {"id": "big-savings"},
                    {"id": "worst-score"},
                ]
            }
        },
        "audits": {
            "small-savings": {
                "score": 0.2,
                "title": "Small savings",
                "details": {"overallSavingsMs": 150},
            },
            "big-savings": {
                "score": 0.8,
                "title": "Big savings",
                "details": {"overallSavingsMs": 2400},
            },
            "worst-score": {"score": 0.1, "title": "Worst score"},
        },
    }

    audits = extract_top_audits(raw_json)

    assert [audit["id"] for audit in audits] == ["big-savings", "small-savings", "worst-score"]


def test_extract_top_audits_skips_passing_informative_and_untitled_audits() -> None:
    raw_json = {
        "categories": {
            "performance": {
                "auditRefs": [
                    {"id": "passing"},
                    {"id": "informative"},
                    {"id": "untitled"},
                    {"id": "failing"},
                ]
            }
        },
        "audits": {
            "passing": {"score": 0.95, "title": "Passing"},
            "informative": {"score": 0.1, "scoreDisplayMode": "informative", "title": "Info"},
            "untitled": {"score": 0.1},
            "failing": {"score": 0.5, "title": "Failing"},
        },
    }

    audits = extract_top_audits(raw_json)

    assert [audit["id"] for audit in audits] == ["failing"]


def test_extract_top_audits_limits_results_and_handles_missing_sections() -> None:
    raw_json = {
        "categories": {
            "performance": {"auditRefs": [{"id": f"audit-{index}"} for index in range(8)]}
        },
        "audits": {
            f"audit-{index}": {
                "score": 0.1,
                "title": f"Audit {index}",
                "details": {"overallSavingsMs": 100 * (8 - index)},
            }
            for index in range(8)
        },
    }

    audits = extract_top_audits(raw_json)

    assert len(audits) == 5
    assert audits[0]["id"] == "audit-0"
    assert extract_top_audits({}) == []
