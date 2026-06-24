# API

외부에 노출되는 API 계약과 오류 응답 규칙을 기록합니다.

## Health

- `GET /health`
- `GET /health/database`

## Projects

인증은 아직 연결되지 않았습니다. 현재 엔드포인트는 프로젝트 CRUD API 기반을 검증하기 위한 범위입니다.

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

- 인증
- 프로젝트 소유권 검사
- SSRF 방어를 포함한 전체 URL 검증
- 도메인 소유권 확인
- 실제 스캔 실행
