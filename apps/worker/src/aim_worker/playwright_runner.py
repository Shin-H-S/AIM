import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from aim_api.models.scenario import StepResultStatus, TestStep
from aim_api.url_validation import UrlValidationError, validate_service_url
from playwright.sync_api import ConsoleMessage, Request, sync_playwright

DEFAULT_STEP_TIMEOUT_MS = 10_000
BODY_SELECTOR = "body"
BLOCKED_URL_PLACEHOLDER = "[blocked-url]"
SECRET_VALUE_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|token|secret|api[_-]?key)(\s*[=:]\s*)([^\s&]+)"
)
BEARER_TOKEN_PATTERN = re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._~+/=-]+)")


class LocatorProtocol(Protocol):
    def click(self, *, timeout: int) -> None: ...

    def fill(self, value: str, *, timeout: int) -> None: ...

    def count(self) -> int: ...

    def inner_text(self, *, timeout: int) -> str: ...


class PageProtocol(Protocol):
    @property
    def url(self) -> str: ...

    def goto(
        self,
        url: str,
        *,
        wait_until: Literal["commit", "domcontentloaded", "load", "networkidle"] | None,
        timeout: float | None,
    ) -> object: ...

    def locator(self, selector: str) -> LocatorProtocol: ...

    def wait_for_timeout(self, timeout: int) -> None: ...

    def screenshot(self, *, full_page: bool) -> bytes: ...


class RouteProtocol(Protocol):
    def abort(self) -> None: ...

    def continue_(self) -> None: ...


class RequestProtocol(Protocol):
    @property
    def url(self) -> str: ...

    @property
    def method(self) -> str: ...

    @property
    def resource_type(self) -> str: ...

    @property
    def failure(self) -> str | None: ...


class ConsoleMessageProtocol(Protocol):
    @property
    def type(self) -> str: ...

    @property
    def text(self) -> str: ...

    @property
    def location(self) -> Mapping[str, object]: ...


@dataclass(frozen=True)
class ExecutedStepResult:
    test_step_id: UUID | None
    step_order: int
    action: str
    target: str | None
    status: StepResultStatus
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    error_message: str | None
    failure_screenshot: bytes | None = None


@dataclass(frozen=True)
class ConsoleErrorEvidence:
    level: str
    message: str
    source_url: str | None
    line_number: int | None
    column_number: int | None


@dataclass(frozen=True)
class NetworkFailureEvidence:
    request_url: str
    method: str
    resource_type: str | None
    failure_text: str | None


@dataclass(frozen=True)
class ScenarioExecutionResult:
    is_successful: bool
    failure_reason: str | None
    step_results: list[ExecutedStepResult]
    console_errors: list[ConsoleErrorEvidence]
    network_failures: list[NetworkFailureEvidence]


def calculate_duration_ms(*, started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)


def step_timeout_ms(step: TestStep) -> int:
    return step.timeout_ms or DEFAULT_STEP_TIMEOUT_MS


def validate_navigation_url(url: str) -> None:
    try:
        validate_service_url(url)
    except UrlValidationError as exc:
        raise RuntimeError("Navigation URL is not allowed.") from exc


def mask_secret_values(text: str) -> str:
    masked_text = BEARER_TOKEN_PATTERN.sub(r"\1[masked]", text)
    return SECRET_VALUE_PATTERN.sub(r"\1\2[masked]", masked_text)


def sanitize_evidence_url(url: str | None) -> str | None:
    if url is None:
        return None
    if not url.startswith(("http://", "https://")):
        return url

    try:
        validate_service_url(url)
    except UrlValidationError:
        return BLOCKED_URL_PLACEHOLDER

    return mask_secret_values(url)


def handle_browser_request(route: RouteProtocol, request: RequestProtocol) -> None:
    if request.url.startswith(("http://", "https://")):
        try:
            validate_service_url(request.url)
        except UrlValidationError:
            route.abort()
            return

    route.continue_()


def collect_console_error(
    console_errors: list[ConsoleErrorEvidence],
    message: ConsoleMessageProtocol,
) -> None:
    if message.type != "error":
        return

    location = message.location
    source_url = location.get("url")
    line_number = location.get("lineNumber")
    column_number = location.get("columnNumber")
    console_errors.append(
        ConsoleErrorEvidence(
            level=message.type,
            message=mask_secret_values(message.text),
            source_url=sanitize_evidence_url(str(source_url)) if source_url else None,
            line_number=line_number if isinstance(line_number, int) else None,
            column_number=column_number if isinstance(column_number, int) else None,
        )
    )


def collect_network_failure(
    network_failures: list[NetworkFailureEvidence],
    request: RequestProtocol,
) -> None:
    sanitized_url = sanitize_evidence_url(request.url)
    failure_text = (
        "Blocked unsafe request URL."
        if sanitized_url == BLOCKED_URL_PLACEHOLDER
        else mask_secret_values(request.failure or "Request failed.")
    )
    network_failures.append(
        NetworkFailureEvidence(
            request_url=sanitized_url or BLOCKED_URL_PLACEHOLDER,
            method=request.method,
            resource_type=request.resource_type,
            failure_text=failure_text,
        )
    )


def execute_step(page: PageProtocol, step: TestStep) -> None:
    timeout_ms = step_timeout_ms(step)

    match step.action:
        case "navigate":
            if step.target is None:
                raise RuntimeError("navigate step requires target.")
            validate_navigation_url(step.target)
            page.goto(step.target, wait_until="load", timeout=timeout_ms)
        case "click":
            if step.target is None:
                raise RuntimeError("click step requires target.")
            page.locator(step.target).click(timeout=timeout_ms)
        case "fill":
            if step.target is None or step.value is None:
                raise RuntimeError("fill step requires target and value.")
            page.locator(step.target).fill(step.value, timeout=timeout_ms)
        case "wait":
            if step.timeout_ms is None:
                raise RuntimeError("wait step requires timeout_ms.")
            page.wait_for_timeout(step.timeout_ms)
        case "assert_element_exists":
            if step.target is None:
                raise RuntimeError("assert_element_exists step requires target.")
            if page.locator(step.target).count() <= 0:
                raise RuntimeError("Expected element was not found.")
        case "assert_text_exists":
            if step.value is None:
                raise RuntimeError("assert_text_exists step requires value.")
            if step.value not in page.locator(BODY_SELECTOR).inner_text(timeout=timeout_ms):
                raise RuntimeError("Expected text was not found.")
        case "assert_url":
            if step.value is None:
                raise RuntimeError("assert_url step requires value.")
            # 쿼리 파라미터나 trailing slash 차이로 깨지지 않도록 부분 일치로 검사한다.
            if step.value not in page.url:
                raise RuntimeError("Current URL did not contain the expected URL fragment.")
        case "take_screenshot":
            page.screenshot(full_page=True)
        case _:
            raise RuntimeError("Unsupported scenario step action.")


def capture_failure_screenshot(page: PageProtocol) -> bytes | None:
    try:
        return page.screenshot(full_page=True)
    except Exception:
        return None


def failed_step_result(
    *,
    step: TestStep,
    started_at: datetime,
    finished_at: datetime,
    error_message: str,
    failure_screenshot: bytes | None,
) -> ExecutedStepResult:
    return ExecutedStepResult(
        test_step_id=step.id,
        step_order=step.step_order,
        action=step.action,
        target=step.target,
        status=StepResultStatus.FAILED,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=calculate_duration_ms(started_at=started_at, finished_at=finished_at),
        error_message=error_message,
        failure_screenshot=failure_screenshot,
    )


def passed_step_result(
    *,
    step: TestStep,
    started_at: datetime,
    finished_at: datetime,
) -> ExecutedStepResult:
    return ExecutedStepResult(
        test_step_id=step.id,
        step_order=step.step_order,
        action=step.action,
        target=step.target,
        status=StepResultStatus.PASSED,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=calculate_duration_ms(started_at=started_at, finished_at=finished_at),
        error_message=None,
    )


def skipped_step_result(*, step: TestStep) -> ExecutedStepResult:
    return ExecutedStepResult(
        test_step_id=step.id,
        step_order=step.step_order,
        action=step.action,
        target=step.target,
        status=StepResultStatus.SKIPPED,
        started_at=None,
        finished_at=None,
        duration_ms=None,
        error_message="Skipped after a critical step failed.",
    )


def execute_steps_on_page(
    *,
    page: PageProtocol,
    steps: Sequence[TestStep],
    step_executor: Callable[[PageProtocol, TestStep], None] = execute_step,
) -> ScenarioExecutionResult:
    step_results: list[ExecutedStepResult] = []
    first_critical_failure: str | None = None

    for index, step in enumerate(steps):
        if first_critical_failure is not None:
            step_results.extend(
                skipped_step_result(step=remaining_step) for remaining_step in steps[index:]
            )
            break

        started_at = datetime.now(UTC)
        try:
            step_executor(page, step)
        except Exception as exc:
            finished_at = datetime.now(UTC)
            error_message = str(exc) or "Scenario step failed."
            failure_screenshot = capture_failure_screenshot(page)
            step_results.append(
                failed_step_result(
                    step=step,
                    started_at=started_at,
                    finished_at=finished_at,
                    error_message=error_message,
                    failure_screenshot=failure_screenshot,
                )
            )
            if step.is_critical:
                first_critical_failure = error_message
            continue

        finished_at = datetime.now(UTC)
        step_results.append(
            passed_step_result(
                step=step,
                started_at=started_at,
                finished_at=finished_at,
            )
        )

    return ScenarioExecutionResult(
        is_successful=first_critical_failure is None,
        failure_reason=first_critical_failure,
        step_results=step_results,
        console_errors=[],
        network_failures=[],
    )


def run_playwright_scenario(steps: Sequence[TestStep]) -> ScenarioExecutionResult:
    with sync_playwright() as playwright:
        # Same container constraint as the Lighthouse chrome-flags: Chromium's
        # sandbox cannot start under Docker's default seccomp profile.
        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = browser.new_context()
            context.route("**/*", handle_browser_request)
            page = context.new_page()
            console_errors: list[ConsoleErrorEvidence] = []
            network_failures: list[NetworkFailureEvidence] = []

            def on_console_message(message: ConsoleMessage) -> None:
                collect_console_error(console_errors, message)

            def on_request_failed(request: Request) -> None:
                collect_network_failure(network_failures, request)

            page.on("console", on_console_message)
            page.on("requestfailed", on_request_failed)
            execution_result = execute_steps_on_page(page=page, steps=steps)
            return ScenarioExecutionResult(
                is_successful=execution_result.is_successful,
                failure_reason=execution_result.failure_reason,
                step_results=execution_result.step_results,
                console_errors=console_errors,
                network_failures=network_failures,
            )
        finally:
            browser.close()
