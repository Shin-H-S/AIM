from typing import Literal
from uuid import uuid4

import pytest
from aim_api.models.scenario import StepResultStatus, TestStep
from aim_api.url_validation import UrlValidationError
from aim_worker import playwright_runner


class FakeLocator:
    def __init__(self, *, selector: str, count: int = 1, text: str = "") -> None:
        self.selector = selector
        self._count = count
        self._text = text
        self.clicks: list[int] = []
        self.fills: list[tuple[str, int]] = []

    def click(self, *, timeout: int) -> None:
        self.clicks.append(timeout)

    def fill(self, value: str, *, timeout: int) -> None:
        self.fills.append((value, timeout))

    def count(self) -> int:
        return self._count

    def inner_text(self, *, timeout: int) -> str:
        _ = timeout
        return self._text


class FakePage:
    def __init__(self) -> None:
        self._url = "https://example.com"
        self.goto_calls: list[tuple[str, str, float]] = []
        self.waits: list[int] = []
        self.screenshots = 0
        self.locators: dict[str, FakeLocator] = {
            "#email": FakeLocator(selector="#email"),
            "#submit": FakeLocator(selector="#submit"),
            "#dashboard": FakeLocator(selector="#dashboard"),
            "#missing": FakeLocator(selector="#missing", count=0),
            "body": FakeLocator(selector="body", text="Welcome to dashboard"),
        }

    @property
    def url(self) -> str:
        return self._url

    @url.setter
    def url(self, value: str) -> None:
        self._url = value

    def goto(
        self,
        url: str,
        *,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] | None,
        timeout: float | None,
    ) -> object:
        assert wait_until is not None
        assert timeout is not None
        self.goto_calls.append((url, wait_until, timeout))
        self.url = url
        return object()

    def locator(self, selector: str) -> FakeLocator:
        return self.locators[selector]

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)

    def screenshot(self, *, full_page: bool) -> bytes:
        assert full_page is True
        self.screenshots += 1
        return b"fake-screenshot"


class FakeRoute:
    def __init__(self) -> None:
        self.aborted = False
        self.continued = False

    def abort(self) -> None:
        self.aborted = True

    def continue_(self) -> None:
        self.continued = True


class FakeRequest:
    def __init__(
        self,
        url: str,
        *,
        method: str = "GET",
        resource_type: str = "fetch",
        failure: str | None = "net::ERR_FAILED",
    ) -> None:
        self.url = url
        self.method = method
        self.resource_type = resource_type
        self.failure = failure


class FakeConsoleMessage:
    def __init__(
        self,
        *,
        message_type: str,
        text: str,
        location: dict[str, str | int],
    ) -> None:
        self.type = message_type
        self.text = text
        self.location = location


def make_step(
    *,
    order: int,
    action: str,
    target: str | None = None,
    value: str | None = None,
    timeout_ms: int | None = None,
    is_critical: bool = True,
) -> TestStep:
    return TestStep(
        id=uuid4(),
        scenario_id=uuid4(),
        step_order=order,
        action=action,
        target=target,
        value=value,
        timeout_ms=timeout_ms,
        is_critical=is_critical,
    )


def test_execute_supported_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(playwright_runner, "validate_service_url", lambda _: None)
    page = FakePage()
    steps = [
        make_step(order=1, action="navigate", target="https://example.com/login"),
        make_step(order=2, action="fill", target="#email", value="user@example.com"),
        make_step(order=3, action="click", target="#submit"),
        make_step(order=4, action="wait", timeout_ms=50),
        make_step(order=5, action="assert_element_exists", target="#dashboard"),
        make_step(order=6, action="assert_text_exists", value="dashboard"),
        make_step(order=7, action="assert_url", value="https://example.com/login"),
        make_step(order=8, action="take_screenshot"),
    ]

    result = playwright_runner.execute_steps_on_page(page=page, steps=steps)

    assert result.is_successful is True
    assert result.failure_reason is None
    assert result.console_errors == []
    assert result.network_failures == []
    assert [step_result.status for step_result in result.step_results] == [
        StepResultStatus.PASSED,
        StepResultStatus.PASSED,
        StepResultStatus.PASSED,
        StepResultStatus.PASSED,
        StepResultStatus.PASSED,
        StepResultStatus.PASSED,
        StepResultStatus.PASSED,
        StepResultStatus.PASSED,
    ]
    assert page.goto_calls == [("https://example.com/login", "load", 10_000)]
    assert page.locators["#email"].fills == [("user@example.com", 10_000)]
    assert page.locators["#submit"].clicks == [10_000]
    assert page.waits == [50]
    assert page.screenshots == 1


def test_critical_failure_skips_remaining_steps() -> None:
    page = FakePage()
    steps = [
        make_step(order=1, action="assert_element_exists", target="#missing"),
        make_step(order=2, action="click", target="#submit"),
    ]

    result = playwright_runner.execute_steps_on_page(page=page, steps=steps)

    assert result.is_successful is False
    assert result.failure_reason == "Expected element was not found."
    assert [step_result.status for step_result in result.step_results] == [
        StepResultStatus.FAILED,
        StepResultStatus.SKIPPED,
    ]


def test_non_critical_failure_continues_remaining_steps() -> None:
    page = FakePage()
    steps = [
        make_step(
            order=1,
            action="assert_element_exists",
            target="#missing",
            is_critical=False,
        ),
        make_step(order=2, action="click", target="#submit"),
    ]

    result = playwright_runner.execute_steps_on_page(page=page, steps=steps)

    assert result.is_successful is True
    assert result.failure_reason is None
    assert [step_result.status for step_result in result.step_results] == [
        StepResultStatus.FAILED,
        StepResultStatus.PASSED,
    ]


def test_navigate_rejects_unsafe_url(monkeypatch: pytest.MonkeyPatch) -> None:
    page = FakePage()

    def reject_service_url(_: str) -> None:
        raise UrlValidationError("private IP")

    monkeypatch.setattr(playwright_runner, "validate_service_url", reject_service_url)

    result = playwright_runner.execute_steps_on_page(
        page=page,
        steps=[make_step(order=1, action="navigate", target="http://127.0.0.1")],
    )

    assert result.is_successful is False
    assert result.step_results[0].status == StepResultStatus.FAILED
    assert result.step_results[0].error_message == "Navigation URL is not allowed."
    assert page.goto_calls == []


def test_browser_request_handler_aborts_unsafe_url(monkeypatch: pytest.MonkeyPatch) -> None:
    route = FakeRoute()
    request = FakeRequest("http://127.0.0.1/admin")

    def reject_service_url(_: str) -> None:
        raise UrlValidationError("private IP")

    monkeypatch.setattr(playwright_runner, "validate_service_url", reject_service_url)

    playwright_runner.handle_browser_request(route, request)

    assert route.aborted is True
    assert route.continued is False


def test_browser_request_handler_continues_safe_url(monkeypatch: pytest.MonkeyPatch) -> None:
    route = FakeRoute()
    request = FakeRequest("https://example.com")
    monkeypatch.setattr(playwright_runner, "validate_service_url", lambda _: None)

    playwright_runner.handle_browser_request(route, request)

    assert route.aborted is False
    assert route.continued is True


def test_collect_console_error_masks_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(playwright_runner, "validate_service_url", lambda _: None)
    console_errors: list[playwright_runner.ConsoleErrorEvidence] = []
    message = FakeConsoleMessage(
        message_type="error",
        text="Login failed token=abc123 password=super-secret",
        location={
            "url": "https://example.com/app.js?api_key=secret-key",
            "lineNumber": 12,
            "columnNumber": 3,
        },
    )

    playwright_runner.collect_console_error(console_errors, message)

    assert len(console_errors) == 1
    assert console_errors[0].level == "error"
    assert console_errors[0].message == "Login failed token=[masked] password=[masked]"
    assert console_errors[0].source_url == "https://example.com/app.js?api_key=[masked]"
    assert console_errors[0].line_number == 12
    assert console_errors[0].column_number == 3


def test_collect_console_error_ignores_non_error_messages() -> None:
    console_errors: list[playwright_runner.ConsoleErrorEvidence] = []
    message = FakeConsoleMessage(
        message_type="warning",
        text="This is only a warning",
        location={},
    )

    playwright_runner.collect_console_error(console_errors, message)

    assert console_errors == []


def test_collect_network_failure_masks_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(playwright_runner, "validate_service_url", lambda _: None)
    network_failures: list[playwright_runner.NetworkFailureEvidence] = []
    request = FakeRequest(
        "https://example.com/api?token=abc123",
        method="POST",
        resource_type="xhr",
        failure="authorization: Bearer abc123",
    )

    playwright_runner.collect_network_failure(network_failures, request)

    assert len(network_failures) == 1
    assert network_failures[0].request_url == "https://example.com/api?token=[masked]"
    assert network_failures[0].method == "POST"
    assert network_failures[0].resource_type == "xhr"
    assert network_failures[0].failure_text == "authorization: Bearer [masked]"


def test_collect_network_failure_hides_unsafe_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_service_url(_: str) -> None:
        raise UrlValidationError("private IP")

    monkeypatch.setattr(playwright_runner, "validate_service_url", reject_service_url)
    network_failures: list[playwright_runner.NetworkFailureEvidence] = []
    request = FakeRequest("http://127.0.0.1/admin")

    playwright_runner.collect_network_failure(network_failures, request)

    assert len(network_failures) == 1
    assert network_failures[0].request_url == playwright_runner.BLOCKED_URL_PLACEHOLDER
    assert network_failures[0].failure_text == "Blocked unsafe request URL."
