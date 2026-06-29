# API

외부에 노출되는 API 계약과 오류 응답 규칙을 기록합니다.

## Health

- `GET /health`
- `GET /health/database`

## Auth

### `POST /auth/signup`

이메일과 비밀번호로 사용자를 생성합니다.

요청 필드:

- `email`: 이메일 주소
- `password`: 8자 이상 128자 이하 비밀번호

성공 시 사용자 정보를 반환합니다. 원문 비밀번호와 비밀번호 해시는 응답에 포함하지 않습니다.

중복 이메일이면 `409`와 `{"detail": "Email is already registered."}`를 반환합니다.

### `POST /auth/login`

이메일과 비밀번호를 검증하고 JWT access token을 발급합니다.

성공 응답:

- `access_token`
- `token_type`: `bearer`

인증 실패 시 `401`과 `{"detail": "Invalid email or password."}`를 반환합니다.

### `GET /auth/me`

`Authorization: Bearer <token>` 헤더의 access token을 검증하고 현재 사용자 정보를 반환합니다.

토큰이 없거나 유효하지 않으면 `401`과 `{"detail": "Could not validate credentials."}`를 반환합니다.

### `POST /auth/logout`

`Authorization: Bearer <token>` 헤더의 access token을 검증하고 `204`를 반환합니다.

현재 로그아웃은 stateless JWT 방식에 맞춰 클라이언트가 토큰을 폐기하는 흐름입니다. 서버 측 토큰 폐기 목록은 아직 포함하지 않았습니다.

## Projects

모든 프로젝트 API는 `Authorization: Bearer <token>` 헤더를 요구합니다. 프로젝트 생성 시 현재 사용자가 소유자로 기록되며, 목록·단건 조회·수정·삭제는 현재 사용자 소유 프로젝트만 대상으로 합니다.

다른 사용자의 프로젝트 ID로 접근하면 존재 여부를 노출하지 않기 위해 `404`와 `{"detail": "Project not found."}`를 반환합니다.

서비스 URL이 허용되지 않으면 내부 네트워크 정보를 노출하지 않도록 `422`와 `{"detail": "Service URL is not allowed."}`를 반환합니다.

### `POST /projects`

프로젝트를 생성합니다.

필드:

- `name`: 프로젝트 이름
- `service_url`: HTTP/HTTPS 서비스 URL. 저장 전에 SSRF-safe 검증을 수행합니다.
- `description`: 설명, 선택
- `environment`: `development`, `staging`, `production`
- `scan_interval_minutes`: 스캔 주기, 분 단위
- `response_time_threshold_ms`: 응답 시간 임계값
- `quality_score_threshold`: 품질 점수 임계값, 0~100

### `GET /projects`

프로젝트 목록을 조회합니다.

쿼리:

- `limit`: 기본 50, 최대 100
- `offset`: 기본 0

### `GET /projects/{project_id}`

프로젝트 단건을 조회합니다.

존재하지 않으면 `404`와 `{"detail": "Project not found."}`를 반환합니다.

### `PATCH /projects/{project_id}`

프로젝트 일부 필드를 수정합니다. 최소 하나 이상의 필드가 필요합니다.

### `DELETE /projects/{project_id}`

프로젝트를 삭제합니다. 성공 시 `204`를 반환합니다.

### `GET /projects/{project_id}/verification`

현재 사용자 소유 프로젝트의 도메인 소유권 확인 정보를 반환합니다.

응답 필드:

- `project_id`
- `verification_token`
- `meta_tag`
- `is_verified`
- `verified_at`

### `POST /projects/{project_id}/verify`

프로젝트의 `service_url` HTML에서 다음 meta tag를 확인합니다.

```html
<meta name="aim-verification" content="aim_verify_generated_token" />
```

검증 성공 시 `status: "verified"`와 검증 상태를 반환합니다. 검증 실패 시 원격 응답 본문이나 내부 네트워크 정보를 노출하지 않고 `400`과 `{"detail": "Domain verification failed."}`를 반환합니다.

## CheckRuns

모든 CheckRun API는 `Authorization: Bearer <token>` 헤더를 요구합니다. 현재 사용자 소유 프로젝트의 check run만 생성·조회·취소할 수 있습니다.

CheckRun 생성은 프로젝트가 도메인 검증된 경우에만 허용됩니다. 검증되지 않은 프로젝트는 `409`와 `{"detail": "Project must be verified before creating a check run."}`를 반환합니다.

### `POST /projects/{project_id}/check-runs`

수동 check run을 생성합니다. API는 `QUEUED` 상태 레코드를 저장한 뒤 Redis/Celery scan queue에 worker task를 등록합니다.

큐 등록에 실패하면 check run을 `FAILED`로 기록하고 `503`과 `{"detail": "Scan queue is unavailable."}`를 반환합니다.

현재 worker는 task를 소비하면 check run을 `RUNNING`으로 전환한 뒤 HTTP availability scanner, SSL inspection, Lighthouse mobile scan을 실행합니다. 최종 HTTP 상태가 2xx 또는 3xx이고 HTTPS 인증서가 유효하며 Lighthouse 실행이 성공하면 `COMPLETED`, timeout·connection failure·차단된 redirect·4xx·5xx·인증서 검증 실패·인증서 만료·Lighthouse 실행 실패는 `FAILED`로 기록합니다. CheckRun 생성 시 active scenario별 linked ScenarioRun도 함께 생성됩니다. scanner 결과와 해당 CheckRun에 연결된 terminal ScenarioRun 결과를 기준으로 결정론적 score와 deployment risk를 계산하고, 같은 프로젝트의 직전 terminal check run이 있으면 주요 지표 delta를 저장합니다.

### `GET /projects/{project_id}/check-runs`

프로젝트 check run 목록을 조회합니다.

쿼리:

- `limit`: 기본 50, 최대 100
- `offset`: 기본 0

### `GET /projects/{project_id}/check-runs/{check_run_id}`

check run 단건을 조회합니다. Polling 클라이언트는 이 API를 반복 호출해 scan 상태와 저장된 결과를 확인할 수 있습니다.

응답에는 기본 CheckRun 필드와 함께 다음 nullable result 필드가 포함됩니다.

- `availability_result`: HTTP availability scan 결과. 아직 worker가 결과를 저장하지 않았다면 `null`입니다.
- `ssl_result`: SSL inspection 결과. HTTP scan이 실패했거나 아직 SSL 검사가 실행되지 않았다면 `null`입니다.
- `lighthouse_result`: Lighthouse mobile scan 결과. HTTP/SSL 단계가 실패했거나 아직 Lighthouse가 실행되지 않았다면 `null`입니다.
- `score_result`: scanner 결과와 해당 CheckRun에 연결된 terminal ScenarioRun 결과 기준의 결정론적 score와 deployment risk입니다. 아직 계산 전이면 `null`입니다. linked ScenarioRun이 없거나 아직 terminal 상태가 아니면 `functional_stability_score`는 `null`입니다.
- `comparison_result`: 같은 프로젝트의 직전 terminal run 대비 score, response time, Lighthouse performance delta입니다. 비교 가능한 이전 run이 없으면 `null`입니다.
- `artifacts`: CheckRun에서 생성된 artifact metadata 목록입니다. 현재는 Lighthouse raw JSON의 `storage_backend`, `storage_path`, `content_type`, `size_bytes`, `checksum_sha256`을 포함합니다.
- `linked_scenario_runs`: CheckRun 생성 시 함께 만들어진 ScenarioRun 목록입니다. 각 항목은 ScenarioRun id, scenario id, 상태, 실행 시간, 실패 사유를 포함합니다.

### `POST /projects/{project_id}/check-runs/{check_run_id}/cancel`

아직 완료되지 않은 check run을 `CANCELLED` 상태로 변경합니다.

## TestScenarios

모든 TestScenario API는 `Authorization: Bearer <token>` 헤더를 요구합니다. 현재 사용자 소유 프로젝트의 scenario만 생성·조회·수정·삭제할 수 있습니다.

다른 사용자의 프로젝트 ID로 접근하면 프로젝트 존재 여부를 노출하지 않기 위해 `404`와 `{"detail": "Project not found."}`를 반환합니다.

웹 Scenario 목록 페이지는 `/projects/{projectId}/scenarios`에서 이 API를 사용해 scenario와 step 정의를 표시합니다.

### `POST /projects/{project_id}/scenarios`

Playwright로 실행할 핵심 사용자 흐름을 정의합니다. 요청에는 scenario 정보와 1개 이상 50개 이하의 step이 필요합니다.

지원 action:

- `navigate`: `target` 필수
- `click`: `target` 필수
- `fill`: `target`, `value` 필수
- `wait`: `timeout_ms` 필수
- `assert_element_exists`: `target` 필수
- `assert_text_exists`: `value` 필수
- `assert_url`: `value` 필수
- `take_screenshot`: 추가 필드 선택

API는 저장 순서대로 `step_order`를 부여합니다.

### `GET /projects/{project_id}/scenarios`

프로젝트 scenario 목록을 조회합니다.

쿼리:

- `limit`: 기본 50, 최대 100
- `offset`: 기본 0

### `GET /projects/{project_id}/scenarios/{scenario_id}`

scenario 단건과 step 목록을 조회합니다. 존재하지 않으면 `404`와 `{"detail": "Scenario not found."}`를 반환합니다.

### `PATCH /projects/{project_id}/scenarios/{scenario_id}`

scenario 일부 필드를 수정합니다. 최소 하나 이상의 필드가 필요합니다. `steps`를 전달하면 기존 step 목록을 새 목록으로 교체하고 `step_order`를 다시 부여합니다.

### `DELETE /projects/{project_id}/scenarios/{scenario_id}`

scenario를 삭제합니다. 성공 시 `204`를 반환합니다.

### `POST /projects/{project_id}/scenarios/{scenario_id}/runs`

시나리오 실행 요청을 생성합니다. API는 `QUEUED` 상태의 `scenario_runs` 레코드를 저장한 뒤 Redis/Celery queue에 worker task를 등록합니다.

비활성 scenario는 `409`와 `{"detail": "Scenario must be active before creating a scenario run."}`를 반환합니다. 큐 등록에 실패하면 scenario run을 `FAILED`로 기록하고 `503`과 `{"detail": "Scan queue is unavailable."}`를 반환합니다.

### `GET /projects/{project_id}/scenarios/{scenario_id}/runs`

scenario run 목록을 조회합니다.

쿼리:

- `limit`: 기본 50, 최대 100
- `offset`: 기본 0

### `GET /projects/{project_id}/scenarios/{scenario_id}/runs/{scenario_run_id}`

scenario run 단건과 step result, console error, failed network request 목록을 조회합니다. Polling 클라이언트는 이 API를 반복 호출해 scenario 실행 상태와 step-level 결과 및 실패 근거를 확인할 수 있습니다. 웹 결과 페이지는 `/projects/{projectId}/scenarios/{scenarioId}/runs/{scenarioRunId}`에서 이 API를 사용합니다.

현재 worker는 저장된 step을 Playwright 브라우저에서 순서대로 실행합니다. `navigate`, `click`, `fill`, `wait`, `assert_element_exists`, `assert_text_exists`, `assert_url`, `take_screenshot` action을 지원합니다. `navigate` 대상과 브라우저의 HTTP/HTTPS 요청 URL은 실행 전 SSRF-safe 검증을 수행합니다.

critical step이 실패하면 해당 step은 `FAILED`, 이후 step은 `SKIPPED`로 기록하고 scenario run은 `FAILED`가 됩니다. non-critical step 실패는 step result에는 `FAILED`로 남기지만 전체 scenario run은 계속 진행합니다. CheckRun에서 생성된 ScenarioRun은 `check_run_id`를 포함합니다. 실패한 step은 screenshot artifact가 저장된 경우 `failure_screenshot_artifact_id`를 포함합니다.

브라우저의 `console.error`는 `console_errors`에 저장됩니다. failed network request는 `network_failures`에 저장됩니다. 실패 screenshot 파일은 local artifact로 저장하고 DB에는 metadata와 path만 기록합니다. evidence message와 URL에 포함될 수 있는 token/password/API key 형태의 값은 저장 전에 마스킹하며, SSRF-safe 검증을 통과하지 못한 URL은 `[blocked-url]`로 저장합니다.

## Artifacts

### `GET /artifacts/{artifact_id}/download`

저장된 local artifact 파일을 다운로드합니다. 모든 Artifact API는 `Authorization: Bearer <token>` 헤더를 요구합니다.

현재 사용자가 생성한 CheckRun 또는 ScenarioRun에 속한 artifact만 다운로드할 수 있습니다. 권한이 없거나 artifact 파일이 없거나 저장 경로가 `ARTIFACT_LOCAL_ROOT` 밖으로 벗어나면 `404`와 `{"detail": "Artifact not found."}`를 반환합니다.

현재는 `ARTIFACT_STORAGE_BACKEND=local`만 다운로드를 지원합니다. 다른 storage backend는 `409`와 `{"detail": "Artifact storage backend is not downloadable."}`를 반환합니다.

## 아직 포함하지 않은 범위

- recurring scan 차단 규칙과 스케줄러 연결
- verification token 재발급 API
- MinIO/GCS 업로드
- 로그인 UI와 연결된 frontend result page
