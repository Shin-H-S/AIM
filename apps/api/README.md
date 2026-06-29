# API

FastAPI 기반 AIM HTTP API가 위치합니다.

인증, 프로젝트와 서비스 대상 관리, 소유권 검증, 스캔 요청 및 결과 조회를 담당합니다. 장시간 실행되는 스캔은 요청 프로세스에서 실행하지 않고 Worker에 전달합니다.

## 로컬 실행

저장소 루트에서 의존성을 설치하고 PostgreSQL과 개발 서버를 실행합니다.

```powershell
uv sync
docker compose -f infra/compose.dev.yaml up -d postgres redis
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

HTTP availability scanner는 실제 요청 전 `service_url`과 redirect destination을 다시 검증하며, timeout과 response size 제한을 적용합니다.

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

check run 생성은 `QUEUED` 상태의 레코드를 만든 뒤 active scenario별 linked ScenarioRun을 함께 생성하고 Redis/Celery queue에 CheckRun task와 ScenarioRun task를 등록합니다. 큐 등록에 실패하면 check run과 linked scenario run을 `FAILED`로 기록하고 `503`과 `{"detail": "Scan queue is unavailable."}`를 반환합니다.

현재 worker는 task를 소비하면 check run을 `RUNNING`으로 전환한 뒤 HTTP availability scanner, SSL inspection, Lighthouse mobile scan을 실행합니다. 최종 HTTP 상태가 2xx 또는 3xx이고 HTTPS 인증서가 유효하며 Lighthouse 실행이 성공하면 `COMPLETED`, timeout·connection failure·차단된 redirect·4xx·5xx·인증서 검증 실패·인증서 만료·Lighthouse 실행 실패는 `FAILED`로 기록합니다. HTTP availability, SSL inspection, Lighthouse metric 결과는 각각 `availability_results`, `ssl_results`, `lighthouse_results`에 정규화해 저장합니다. Lighthouse raw JSON은 로컬 artifact 파일로 저장하고 `artifacts` 테이블에는 metadata와 storage path만 기록합니다. scanner 결과와 해당 CheckRun에 연결된 terminal ScenarioRun 결과를 기준으로 `score_results`에 결정론적 score와 deployment risk를 저장하고, 같은 프로젝트의 직전 terminal check run이 있으면 `run_comparisons`에 주요 delta를 저장합니다. 연결된 ScenarioRun이 없던 기존 run은 같은 프로젝트의 최신 terminal ScenarioRun을 fallback으로 사용합니다.

연결된 ScenarioRun이 아직 terminal 상태가 아니거나 ScenarioRun이 없으면 `functional_stability_score`는 `null`입니다. linked terminal ScenarioRun이 모두 성공하면 functional stability는 100점으로 반영되고, 완료된 run에 실패 step이 포함되면 감점됩니다. linked terminal ScenarioRun 중 실패한 run이 있으면 deployment risk를 `RISK`로 올리고 grade를 `F`로 제한합니다. ScenarioRun worker는 linked run 완료 후 scanner 결과가 이미 저장된 CheckRun의 score와 comparison을 다시 계산합니다.

`GET /projects/{project_id}/check-runs/{check_run_id}`는 polling에 사용할 수 있도록 CheckRun 상태와 함께 nullable `availability_result`, `ssl_result`, `lighthouse_result`, `score_result`, `comparison_result`, 그리고 `artifacts` metadata 목록을 반환합니다.

## TestScenario API

프로젝트별 Playwright 시나리오와 실행 step을 정의할 수 있습니다. 모든 시나리오 API는 Bearer token 인증을 요구하며, 현재 사용자 소유 프로젝트의 시나리오만 생성·조회·수정·삭제할 수 있습니다.

지원 엔드포인트:

- `POST /projects/{project_id}/scenarios`
- `GET /projects/{project_id}/scenarios`
- `GET /projects/{project_id}/scenarios/{scenario_id}`
- `PATCH /projects/{project_id}/scenarios/{scenario_id}`
- `DELETE /projects/{project_id}/scenarios/{scenario_id}`

지원 step action:

- `navigate`
- `click`
- `fill`
- `wait`
- `assert_element_exists`
- `assert_text_exists`
- `assert_url`
- `take_screenshot`

각 시나리오는 1개 이상 50개 이하의 step을 가져야 하며, API는 저장 순서대로 `step_order`를 부여합니다. worker는 저장된 step을 Playwright 브라우저에서 순서대로 실행하고 StepResult를 기록합니다. `navigate` 대상과 브라우저의 HTTP/HTTPS 요청 URL은 실행 전 SSRF-safe 검증을 수행합니다.

## ScenarioRun API

정의된 시나리오에 대해 실행 요청을 생성하고 실행 상태 및 step 결과를 조회할 수 있습니다. 모든 ScenarioRun API는 Bearer token 인증을 요구하며, 현재 사용자 소유 프로젝트의 scenario run만 생성·조회할 수 있습니다.

지원 엔드포인트:

- `POST /projects/{project_id}/scenarios/{scenario_id}/runs`
- `GET /projects/{project_id}/scenarios/{scenario_id}/runs`
- `GET /projects/{project_id}/scenarios/{scenario_id}/runs/{scenario_run_id}`

지원 상태:

- `QUEUED`
- `RUNNING`
- `COMPLETED`
- `FAILED`
- `CANCELLED`

step result 상태:

- `PASSED`
- `FAILED`
- `SKIPPED`

scenario run 생성은 `QUEUED` 상태의 레코드를 만든 뒤 Redis/Celery queue에 worker task를 등록합니다. 큐 등록에 실패하면 scenario run을 `FAILED`로 기록하고 `503`과 `{"detail": "Scan queue is unavailable."}`를 반환합니다.

현재 worker는 scenario run task를 소비하면 상태를 `RUNNING`으로 전환한 뒤 저장된 step을 순서대로 실행합니다. critical step이 실패하면 이후 step은 `SKIPPED`로 기록하고 scenario run을 `FAILED`로 종료합니다. non-critical step 실패는 step result에는 `FAILED`로 남기지만 전체 scenario run은 계속 진행합니다. CheckRun에서 생성된 ScenarioRun은 `check_run_id`로 원본 CheckRun과 연결됩니다.

ScenarioRun 단건 조회 응답에는 step result와 함께 브라우저 `console.error` 목록과 failed network request 목록이 포함됩니다. 실패한 step에서 screenshot을 캡처할 수 있으면 local artifact 파일로 저장하고 `StepResult.failure_screenshot_artifact_id`를 응답에 포함합니다. 웹 결과 페이지는 `/projects/{projectId}/scenarios/{scenarioId}/runs/{scenarioRunId}`에서 이 응답을 polling해 표시합니다. evidence message와 URL에 포함될 수 있는 token/password/API key 형태의 값은 저장 전에 마스킹하며, SSRF-safe 검증을 통과하지 못한 URL은 `[blocked-url]`로 저장합니다.

Artifact 파일은 `GET /artifacts/{artifact_id}/download`에서 다운로드할 수 있습니다. 이 API는 Bearer token 인증을 요구하며, 현재 사용자가 생성한 CheckRun 또는 ScenarioRun에 속한 artifact만 반환합니다.

## Artifact API

저장된 local artifact 파일을 다운로드할 수 있습니다.

지원 엔드포인트:

- `GET /artifacts/{artifact_id}/download`

현재는 `ARTIFACT_STORAGE_BACKEND=local`만 다운로드를 지원합니다. artifact metadata가 현재 사용자에게 속하지 않거나, 파일이 없거나, 저장 경로가 `ARTIFACT_LOCAL_ROOT` 밖으로 벗어나면 `404`와 `{"detail": "Artifact not found."}`를 반환합니다. local 이외의 storage backend는 `409`와 `{"detail": "Artifact storage backend is not downloadable."}`를 반환합니다.

## 검증

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```
