# API

FastAPI 기반 AIM HTTP API가 위치합니다.

인증, 프로젝트와 서비스 대상 관리, 소유권 검증, 스캔 요청 및 결과 조회를 담당합니다. 장시간 실행되는 스캔은 요청 프로세스에서 실행하지 않고 Worker에 전달합니다.

## 로컬 실행

저장소 루트에서 의존성을 설치하고 PostgreSQL과 개발 서버를 실행합니다.

```powershell
uv sync
docker compose -f infra/compose.dev.yaml up -d postgres
uv run alembic -c migrations/alembic.ini upgrade head
uv run uvicorn aim_api.main:app --app-dir apps/api/src --reload
```

서버 실행 후 상태 확인:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

정상 응답:

```json
{
  "status": "ok",
  "service": "aim-api"
}
```

데이터베이스 연결 확인:

```powershell
Invoke-RestMethod http://localhost:8000/health/database
```

`/health`는 애플리케이션 프로세스의 liveness를 확인하며, `/health/database`는 PostgreSQL 연결 readiness를 확인합니다.

## 인증 API

이메일/비밀번호 기반 회원가입과 로그인을 지원합니다. 로그인에 성공하면 JWT access token을 반환하며, 보호된 API는 `Authorization: Bearer <token>` 헤더를 사용합니다.

지원 엔드포인트:

- `POST /auth/signup`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`

비밀번호는 Argon2 기반 해시로 저장하며, API 응답에 원문 비밀번호나 비밀번호 해시는 포함하지 않습니다. 현재 로그아웃은 stateless JWT 방식에 맞춰 유효한 토큰을 확인한 뒤 클라이언트가 토큰을 폐기하는 흐름입니다. 서버 측 토큰 폐기 목록은 아직 포함하지 않았습니다.

## 프로젝트 API

현재 프로젝트 CRUD API가 제공됩니다. 모든 프로젝트 API는 Bearer token 인증을 요구하며, 현재 사용자 소유 프로젝트만 조회·수정·삭제할 수 있습니다.

지원 엔드포인트:

- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `DELETE /projects/{project_id}`
- `GET /projects/{project_id}/verification`
- `POST /projects/{project_id}/verify`

프로젝트는 다음 정보를 저장합니다.

- 소유 사용자 ID
- 이름
- 서비스 URL
- 설명
- 환경: `development`, `staging`, `production`
- 스캔 주기
- 응답 시간 임계값
- 품질 점수 임계값

서비스 URL은 HTTP/HTTPS 형식만 허용하며, 저장 전에 SSRF-safe 검증을 수행합니다.

현재 URL 검증은 다음 대상을 차단합니다.

- `localhost` 및 `.localhost`
- 사용자 정보가 포함된 URL
- loopback, private, link-local, multicast, reserved, unspecified IP
- 주요 cloud metadata IP와 hostname
- DNS 결과 중 하나라도 public address가 아닌 호스트

실제 HTTP 요청, redirect destination 재검증, response size 제한은 스캐너 구현 단계에서 추가합니다.

## 도메인 소유권 확인

MVP는 HTML meta-tag 방식의 소유권 확인을 지원합니다.

1. `GET /projects/{project_id}/verification`으로 verification token과 meta tag를 조회합니다.
2. 대상 서비스의 HTML `<head>`에 다음 형식의 meta tag를 추가합니다.

```html
<meta name="aim-verification" content="aim_verify_generated_token" />
```

3. `POST /projects/{project_id}/verify`를 호출하면 API가 프로젝트의 `service_url`을 안전하게 재검증하고 HTML을 가져와 meta tag를 확인합니다.

검증 요청은 redirect destination마다 URL을 다시 검증하며, timeout과 response size 제한을 적용합니다. 검증 실패 시 내부 네트워크 정보나 원격 응답 본문을 사용자 응답에 노출하지 않습니다.

## CheckRun API

검증된 프로젝트에 대해 수동 check run을 생성하고 조회할 수 있습니다.

지원 엔드포인트:

- `POST /projects/{project_id}/check-runs`
- `GET /projects/{project_id}/check-runs`
- `GET /projects/{project_id}/check-runs/{check_run_id}`
- `POST /projects/{project_id}/check-runs/{check_run_id}/cancel`

지원 상태:

- `QUEUED`
- `RUNNING`
- `ANALYZING`
- `COMPLETED`
- `FAILED`
- `CANCELLED`

현재 check run 생성은 `QUEUED` 상태의 레코드만 만들며, 실제 스캔 작업을 실행하거나 queue에 넣지는 않습니다. Redis task queue와 worker 연결은 다음 작업에서 추가합니다.

## 검증

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```
