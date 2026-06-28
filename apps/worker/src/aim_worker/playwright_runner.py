from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from aim_api.models.scenario import StepResultStatus, TestStep
from aim_api.url_validation import UrlValidationError, validate_service_url
from playwright.sync_api import sync_playwright

DEFAULT_STEP_TIMEOUT_MS = 10_000
BODY_SELECTOR = "body"


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


@dataclass(frozen=True)
class ScenarioExecutionResult:
    is_successful: bool
    failure_reason: str | None
    step_results: list[ExecutedStepResult]


def calculate_duration_ms(*, started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)


def step_timeout_ms(step: TestStep) -> int:
    return step.timeout_ms or DEFAULT_STEP_TIMEOUT_MS


def validate_navigation_url(url: str) -> None:
    try:
        validate_service_url(url)
    except UrlValidationError as exc:
        raise RuntimeError("Navigation URL is not allowed.") from exc


def handle_browser_request(route: RouteProtocol, request: RequestProtocol) -> None:
    if request.url.startswith(("http://", "https://")):
        try:
            validate_service_url(request.url)
        except UrlValidationError:
            route.abort()
            return

    route.continue_()


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
            if page.url != step.value:
                raise RuntimeError("Current URL did not match the expected URL.")
        case "take_screenshot":
            page.screenshot(full_page=True)
        case _:
            raise RuntimeError("Unsupported scenario step action.")


def failed_step_result(
    *,
    step: TestStep,
    started_at: datetime,
    finished_at: datetime,
    error_message: str,
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
            step_results.append(
                failed_step_result(
                    step=step,
                    started_at=started_at,
                    finished_at=finished_at,
                    error_message=error_message,
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
    )


def run_playwright_scenario(steps: Sequence[TestStep]) -> ScenarioExecutionResult:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            context.route("**/*", handle_browser_request)
            page = context.new_page()
            return execute_steps_on_page(page=page, steps=steps)
        finally:
            browser.close()
