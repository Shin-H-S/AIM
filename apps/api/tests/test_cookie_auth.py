"""httpOnly 쿠키 세션과 CSRF 방어.

전환의 계약: 브라우저 세션은 JS가 만질 수 없는 쿠키로 오가고, 쿠키 세션의
상태 변경은 double-submit 증명을 요구하며, Bearer 경로(스크립트·배포 훅)는
이전과 완전히 동일하게 동작한다.
"""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from aim_api.auth_cookies import ACCESS_TOKEN_COOKIE, CSRF_COOKIE, CSRF_HEADER
from fastapi.testclient import TestClient


@pytest.fixture()
def client(api_client: TestClient) -> Iterator[TestClient]:
    """쿠키를 보관하는 클라이언트 — 이 파일의 검증 대상이 바로 그 동작이다.

    api_client(쿠키 비보존)를 받는 이유는 get_db 오버라이드를 세팅하기 위해서고,
    실제 요청은 같은 앱에 붙인 일반 TestClient로 보낸다.
    """
    with TestClient(api_client.app) as cookie_client:
        yield cookie_client


def signup(client: TestClient) -> dict[str, str]:
    credentials = {"email": f"{uuid4()}@example.com", "password": "correct horse battery staple"}
    client.post("/auth/signup", json=credentials)
    return credentials


def login(client: TestClient) -> dict[str, str]:
    credentials = signup(client)
    response = client.post("/auth/login", json=credentials)
    assert response.status_code == 200
    return credentials


def csrf_header(client: TestClient) -> dict[str, str]:
    return {CSRF_HEADER: client.cookies[CSRF_COOKIE]}


def test_login_sets_an_httponly_session_cookie(client: TestClient) -> None:
    credentials = signup(client)

    response = client.post("/auth/login", json=credentials)

    set_cookie_headers = response.headers.get_list("set-cookie")
    access = next(h for h in set_cookie_headers if h.startswith(f"{ACCESS_TOKEN_COOKIE}="))
    csrf = next(h for h in set_cookie_headers if h.startswith(f"{CSRF_COOKIE}="))
    # 토큰 쿠키는 JS가 읽을 수 없어야 탈취 표면이 사라진다.
    assert "HttpOnly" in access
    assert "SameSite=lax" in access
    # csrf 쿠키는 프런트가 읽어 헤더로 되돌려야 하므로 httpOnly면 안 된다.
    assert "HttpOnly" not in csrf


def test_the_cookie_alone_authenticates(client: TestClient) -> None:
    """Authorization 헤더 없이 쿠키만으로 세션이 성립해야 전환이 의미 있다."""
    login(client)

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert "email" in response.json()


def test_cookie_writes_require_the_csrf_proof(client: TestClient) -> None:
    """쿠키는 브라우저가 자동 첨부한다 — 증명 없는 상태 변경은 위조일 수 있다."""
    login(client)

    response = client.post("/projects", json={"name": "csrf", "service_url": "https://example.com"})

    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_a_wrong_csrf_header_is_rejected(client: TestClient) -> None:
    login(client)

    response = client.post(
        "/projects",
        json={"name": "csrf", "service_url": "https://example.com"},
        headers={CSRF_HEADER: "not-the-cookie-value"},
    )

    assert response.status_code == 403


def test_the_matching_csrf_proof_admits_the_write(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aim_api.services import projects as project_service

    monkeypatch.setattr(project_service, "validate_service_url", lambda _: None)
    login(client)

    response = client.post(
        "/projects",
        json={"name": "csrf-ok", "service_url": "https://example.com"},
        headers=csrf_header(client),
    )

    assert response.status_code == 201


def test_reads_do_not_require_csrf(client: TestClient) -> None:
    """GET은 상태를 바꾸지 않는다 — 요구하면 모든 화면이 헤더를 끌고 다녀야 한다."""
    login(client)

    response = client.get("/projects")

    assert response.status_code == 200


def test_bearer_requests_are_exempt_from_csrf(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """공격자 사이트는 피해자의 토큰으로 Authorization 헤더를 만들 수 없다."""
    from aim_api.services import projects as project_service

    monkeypatch.setattr(project_service, "validate_service_url", lambda _: None)
    credentials = login(client)
    # 세션 쿠키가 있는 상태의 재로그인도 상태 변경 POST다 — 증명이 필요하다.
    token = client.post("/auth/login", json=credentials, headers=csrf_header(client)).json()[
        "access_token"
    ]
    client.cookies.clear()

    response = client.post(
        "/projects",
        json={"name": "bearer", "service_url": "https://example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201


def test_unauthenticated_writes_skip_csrf_and_fail_auth(client: TestClient) -> None:
    """세션 쿠키가 없으면 위조할 세션도 없다 — 403(CSRF)이 아니라 401이어야 한다."""
    response = client.post("/projects", json={"name": "x", "service_url": "https://example.com"})

    assert response.status_code == 401


def test_logout_clears_both_cookies_and_revokes(client: TestClient) -> None:
    login(client)

    response = client.post("/auth/logout", headers=csrf_header(client))

    assert response.status_code == 204
    cleared = [
        h
        for h in response.headers.get_list("set-cookie")
        if f"{ACCESS_TOKEN_COOKIE}=" in h or f"{CSRF_COOKIE}=" in h
    ]
    # 두 쿠키 모두 만료로 지워져야 한다 — csrf만 남으면 프런트가 세션이 있다고 착각한다.
    assert len(cleared) == 2
    assert all('=""' in h or "Max-Age=0" in h for h in cleared)

    # 세션이 실제로 끝났는지 — 지운 쿠키로는 더 이상 인증되지 않는다.
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401


def test_the_bearer_path_still_works_end_to_end(client: TestClient) -> None:
    """배포 훅·스크립트·기존 테스트가 쓰는 경로는 그대로여야 한다."""
    credentials = signup(client)
    token = client.post("/auth/login", json=credentials).json()["access_token"]
    client.cookies.clear()

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
