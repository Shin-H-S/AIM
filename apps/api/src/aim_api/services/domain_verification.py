from collections.abc import Callable
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx
from sqlalchemy.orm import Session

from aim_api.models.project import Project, generate_verification_token
from aim_api.url_validation import validate_service_url

MAX_REDIRECTS = 3
MAX_RESPONSE_BYTES = 1_000_000
REQUEST_TIMEOUT = httpx.Timeout(timeout=5.0, connect=2.0)


class DomainVerificationError(Exception):
    """Raised when domain ownership verification cannot be completed."""


class VerificationMetaParser(HTMLParser):
    def __init__(self, expected_token: str) -> None:
        super().__init__()
        self.expected_token = expected_token
        self.is_verified = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return

        values = {name.lower(): value for name, value in attrs if value is not None}
        if (
            values.get("name") == "aim-verification"
            and values.get("content") == self.expected_token
        ):
            self.is_verified = True


def ensure_verification_token(session: Session, project: Project) -> Project:
    if project.verification_token is not None:
        return project

    project.verification_token = generate_verification_token()
    session.commit()
    session.refresh(project)
    return project


def build_meta_tag(project: Project) -> str:
    token = require_verification_token(project)
    return f'<meta name="aim-verification" content="{token}" />'


def require_verification_token(project: Project) -> str:
    if project.verification_token is None:
        raise DomainVerificationError("Verification token is missing.")

    return project.verification_token


def verify_project_domain(
    session: Session,
    project: Project,
    *,
    html_fetcher: Callable[[str], str] | None = None,
) -> Project:
    project = ensure_verification_token(session, project)
    token = require_verification_token(project)
    fetch_html = html_fetcher or fetch_verification_html
    html = fetch_html(project.service_url)

    if not contains_verification_meta_tag(html, token):
        raise DomainVerificationError("Verification meta tag was not found.")

    project.verified_at = datetime.now(UTC)
    session.commit()
    session.refresh(project)
    return project


def contains_verification_meta_tag(html: str, expected_token: str) -> bool:
    parser = VerificationMetaParser(expected_token)
    parser.feed(html)
    return parser.is_verified


def fetch_verification_html(url: str) -> str:
    current_url = url
    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_service_url(current_url)
            response = client.get(current_url)

            if response.is_redirect:
                location = response.headers.get("location")
                if location is None:
                    raise DomainVerificationError("Redirect response did not include location.")

                current_url = urljoin(str(response.url), location)
                validate_service_url(current_url)
                continue

            if response.status_code >= 400:
                raise DomainVerificationError("Verification URL returned an error response.")

            content = read_limited_response(response)
            return content.decode(response.encoding or "utf-8", errors="replace")

    raise DomainVerificationError("Verification URL redirected too many times.")


def read_limited_response(response: httpx.Response) -> bytes:
    content = response.content
    if len(content) > MAX_RESPONSE_BYTES:
        raise DomainVerificationError("Verification response is too large.")

    return content
