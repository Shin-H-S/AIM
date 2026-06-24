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

### `POST /projects`

프로젝트를 생성합니다.

필드:

- `name`: 프로젝트 이름
- `service_url`: HTTP/HTTPS 서비스 URL
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

## 아직 포함하지 않은 범위

- SSRF 방어를 포함한 전체 URL 검증
- 도메인 소유권 확인
- 실제 스캔 실행
