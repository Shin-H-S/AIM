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

현재 worker는 task를 소비하면 check run을 `RUNNING`으로 전환한 뒤 HTTP availability scanner, SSL inspection, Lighthouse mobile scan을 실행합니다. 최종 HTTP 상태가 2xx 또는 3xx이고 HTTPS 인증서가 유효하며 Lighthouse 실행이 성공하면 `COMPLETED`, timeout·connection failure·차단된 redirect·4xx·5xx·인증서 검증 실패·인증서 만료·Lighthouse 실행 실패는 `FAILED`로 기록합니다.

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
- `artifacts`: CheckRun에서 생성된 artifact metadata 목록입니다. 현재는 Lighthouse raw JSON의 `storage_backend`, `storage_path`, `content_type`, `size_bytes`, `checksum_sha256`을 포함합니다.

### `POST /projects/{project_id}/check-runs/{check_run_id}/cancel`

아직 완료되지 않은 check run을 `CANCELLED` 상태로 변경합니다.

## 아직 포함하지 않은 범위

- recurring scan 차단 규칙과 스케줄러 연결
- verification token 재발급 API
- artifact download API와 MinIO/GCS 업로드
- 로그인 UI와 연결된 frontend result page
