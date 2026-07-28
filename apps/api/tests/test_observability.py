import json
import logging
import sys

import pytest
from aim_api.observability import (
    REQUEST_ID_HEADER,
    JsonLogFormatter,
    RequestIdFilter,
    configure_logging,
    new_request_id,
    request_id_context,
    request_id_var,
)
from fastapi.testclient import TestClient


def make_record(message: str = "hello", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="aim_api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=None,
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_emits_one_object_per_line() -> None:
    payload = json.loads(JsonLogFormatter().format(make_record("scan finished")))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "aim_api.test"
    assert payload["message"] == "scan finished"
    assert "timestamp" in payload


def test_json_formatter_carries_domain_identifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    """extra로 넘긴 project_id/check_run_id로 검색·집계할 수 있어야 한다."""
    record = make_record(check_run_id="abc-123", project_id="def-456")

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["check_run_id"] == "abc-123"
    assert payload["project_id"] == "def-456"


def test_json_formatter_stringifies_values_it_cannot_serialise() -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    payload = json.loads(JsonLogFormatter().format(make_record(thing=Opaque())))

    assert payload["thing"] == "<opaque>"


def test_json_formatter_includes_the_traceback_for_exceptions() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="aim_api.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=None,
            exc_info=sys.exc_info(),
        )

    payload = json.loads(JsonLogFormatter().format(record))

    assert "ValueError: boom" in payload["exception"]


def test_request_id_filter_fills_the_current_correlation_id() -> None:
    record = make_record()

    with request_id_context("correlation-1"):
        RequestIdFilter().filter(record)

    assert record.__dict__["request_id"] == "correlation-1"


def test_request_id_context_is_restored_on_exit() -> None:
    """워커 프로세스는 재사용되므로 구간이 끝나면 이전 값으로 돌아가야 한다."""
    assert request_id_var.get() is None

    with request_id_context("outer"):
        with request_id_context("inner"):
            assert request_id_var.get() == "inner"
        assert request_id_var.get() == "outer"

    assert request_id_var.get() is None


def test_configure_logging_applies_the_configured_level() -> None:
    """app_log_level은 정의만 되고 어디서도 읽히지 않던 죽은 설정이었다."""
    try:
        configure_logging("WARNING")
        assert logging.getLogger().level == logging.WARNING

        configure_logging("DEBUG")
        assert logging.getLogger().level == logging.DEBUG
    finally:
        configure_logging("INFO")


def test_configure_logging_does_not_stack_duplicate_handlers() -> None:
    configure_logging("INFO")
    handler_count = len(logging.getLogger().handlers)

    configure_logging("INFO")

    assert len(logging.getLogger().handlers) == handler_count


def test_new_request_id_is_unique() -> None:
    assert new_request_id() != new_request_id()


def test_response_carries_a_request_id(api_client: TestClient) -> None:
    response = api_client.get("/health")

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]


def test_an_inbound_request_id_is_preserved(api_client: TestClient) -> None:
    """프록시·CI가 넘긴 id를 이어받아야 양쪽 로그를 같은 키로 맞출 수 있다."""
    response = api_client.get("/health", headers={REQUEST_ID_HEADER: "from-the-proxy"})

    assert response.headers[REQUEST_ID_HEADER] == "from-the-proxy"


def test_each_request_gets_a_distinct_request_id(api_client: TestClient) -> None:
    first = api_client.get("/health").headers[REQUEST_ID_HEADER]
    second = api_client.get("/health").headers[REQUEST_ID_HEADER]

    assert first != second
