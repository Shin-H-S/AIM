import httpx
import pytest
from aim_api.services.domain_verification import (
    DomainVerificationError,
    contains_verification_meta_tag,
    read_limited_response,
)


def test_contains_verification_meta_tag() -> None:
    html = '<html><head><meta name="aim-verification" content="aim_verify_token" /></head></html>'

    assert contains_verification_meta_tag(html, "aim_verify_token") is True


def test_contains_verification_meta_tag_rejects_wrong_token() -> None:
    html = '<html><head><meta name="aim-verification" content="wrong" /></head></html>'

    assert contains_verification_meta_tag(html, "aim_verify_token") is False


def test_read_limited_response_rejects_large_body() -> None:
    response = httpx.Response(200, content=b"x" * 1_000_001)

    with pytest.raises(DomainVerificationError):
        read_limited_response(response)
