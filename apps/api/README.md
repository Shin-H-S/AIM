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

웹 개발 서버(`http://localhost:3000`)의 브라우저 요청을 허용하도록 CORS 허용 origin 기본값은 `http://localhost:3000`과 `http://127.0.0.1:3000`입니다. 다른 origin에서 API를 호출해야 하면 `CORS_ALLOWED_ORIGINS` 환경 변수에 JSON 배열로 지정합니다. 예: `CORS_ALLOWED_ORIGINS=["https://app.example.com"]`

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
- email alert 사용 여부
- email alert 수신자 주소

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

현재 worker는 task를 소비하면 check run을 `RUNNING`으로 전환한 뒤 HTTP availability scanner, SSL inspection, Lighthouse mobile scan을 실행합니다. 최종 HTTP 상태가 2xx 또는 3xx이고 HTTPS 인증서가 유효하며 Lighthouse 실행이 성공하면 `COMPLETED`, timeout·connection failure·차단된 redirect·4xx·5xx·인증서 검증 실패·인증서 만료·Lighthouse 실행 실패는 `FAILED`로 기록합니다. HTTP availability, SSL inspection, Lighthouse metric 결과는 각각 `availability_results`, `ssl_results`, `lighthouse_results`에 정규화해 저장합니다. Lighthouse raw JSON은 로컬 artifact 파일로 저장하고 `artifacts` 테이블에는 metadata와 storage path만 기록합니다. scanner 결과와 해당 CheckRun에 연결된 terminal ScenarioRun 결과를 기준으로 `score_results`에 결정론적 score와 deployment risk를 저장하고, 같은 프로젝트의 직전 terminal check run이 있으면 `run_comparisons`에 주요 delta를 저장합니다. CheckRun이 terminal 상태가 되면 worker는 incident open/recovery 상태와 pending email alert를 동기화한 뒤 별도 AIReport task를 queue에 등록하고, 이 task가 저장된 score와 evidence를 기준으로 AIReport를 생성합니다. 연결된 ScenarioRun이 없던 기존 run은 같은 프로젝트의 최신 terminal ScenarioRun을 fallback으로 사용합니다.

연결된 ScenarioRun이 아직 terminal 상태가 아니거나 ScenarioRun이 없으면 `functional_stability_score`는 `null`입니다. linked terminal ScenarioRun이 모두 성공하면 functional stability는 100점으로 반영되고, 완료된 run에 실패 step이 포함되면 감점됩니다. linked terminal ScenarioRun 중 실패한 run이 있으면 deployment risk를 `RISK`로 올리고 grade를 `F`로 제한합니다. ScenarioRun worker는 linked run 완료 후 scanner 결과가 이미 저장된 CheckRun의 score와 comparison을 다시 계산하고, CheckRun이 이미 terminal 상태라면 incident 상태와 AIReport task도 다시 갱신합니다.

`GET /projects/{project_id}/check-runs`는 CheckRun 목록과 함께 항목별 `score` 요약(overall/grade/deployment risk와 카테고리 점수)과 `linked_scenario_runs`를 반환합니다. 웹 dashboard와 점수 추이 차트는 이 목록 응답만으로 렌더링됩니다.

`GET /projects/{project_id}/check-runs/{check_run_id}`는 polling에 사용할 수 있도록 CheckRun 상태와 함께 nullable `availability_result`, `ssl_result`, `lighthouse_result`, `score_result`, `comparison_result`, `ai_report` 요약, `artifacts` metadata 목록, 그리고 이 CheckRun에서 생성된 `linked_scenario_runs` 목록을 반환합니다. `lighthouse_result`에는 절감 효과 기준 상위 개선 기회(`top_audits`)가, `score_result`에는 계산 시점에 저장된 점수 산출 근거(`score_breakdown`)가 포함됩니다. `ai_report` 요약에는 score/risk와 summary 중심 필드만 포함하며 전체 `report_json`은 포함하지 않습니다.

`GET /projects/{project_id}/check-runs/{check_run_id}/ai-report`는 해당 CheckRun에 저장된 AIReport를 반환합니다. Bearer token 인증과 프로젝트 소유권 검사를 요구하며, report가 아직 저장되지 않았으면 `404`와 `{"detail": "AI report not found."}`를 반환합니다.

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
- `assert_url` (현재 URL에 기대 값이 포함되는지 부분 일치로 검사)
- `take_screenshot`

각 시나리오는 1개 이상 50개 이하의 step을 가져야 하며, API는 저장 순서대로 `step_order`를 부여합니다. worker는 저장된 step을 Playwright 브라우저에서 순서대로 실행하고 StepResult를 기록합니다. `navigate` 대상과 브라우저의 HTTP/HTTPS 요청 URL은 실행 전 SSRF-safe 검증을 수행합니다.

## ScenarioRun API

정의된 시나리오에 대해 실행 요청을 생성하고 실행 상태 및 step 결과를 조회할 수 있습니다. 모든 ScenarioRun API는 Bearer token 인증을 요구하며, 현재 사용자 소유 프로젝트의 scenario run만 생성·조회할 수 있습니다.

웹에서는 `/projects/{projectId}/scenarios`에서 scenario 목록을 조회·수정·삭제하고 active scenario의 수동 ScenarioRun을 생성할 수 있습니다.

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

## Incidents and alerts

`incidents` 테이블은 프로젝트별 open/recovery 상태를 저장합니다. 현재 worker는 terminal CheckRun 또는 linked ScenarioRun 완료 후 다음 조건을 평가합니다.

- service connection failure
- repeated 5xx response
- critical linked scenario failure
- performance score below `quality_score_threshold`
- response time above `response_time_threshold_ms`

같은 프로젝트에 같은 trigger type의 open incident가 이미 있으면 incident와 evidence를 갱신하고 새 alert는 만들지 않습니다. 조건이 더 이상 active하지 않으면 incident를 `RESOLVED`로 닫고 recovery alert를 기록합니다. `alerts` 테이블은 `PENDING`, `SENT`, `FAILED` email alert 상태와 발송 시각, 실패 사유, 시도 횟수를 저장합니다.

지원 엔드포인트:

- `GET /projects/{project_id}/incidents`
- `GET /projects/{project_id}/alerts`
- `POST /projects/{project_id}/alerts/{alert_id}/retry`

세 엔드포인트 모두 Bearer token 인증과 프로젝트 소유권 검사를 요구하며, 현재 사용자 소유 프로젝트의 Incident/Alert만 반환하거나 변경합니다. 목록 조회는 `limit`과 `offset` query parameter로 범위를 제한할 수 있습니다.

Project의 `alert_email_enabled`가 `false`이면 incident open/recovery 시 pending email alert를 만들지 않습니다. `alert_recipient_email`이 설정되어 있으면 해당 주소로 발송하고, 비어 있으면 Project owner email을 사용합니다.

FAILED 상태의 email alert는 retry API로 다시 `PENDING` 상태로 되돌리고 email delivery task에 재등록할 수 있습니다. `PENDING` 또는 `SENT` alert 재시도는 `409`로 거부합니다. Queue 등록에 실패하면 alert를 다시 `FAILED`로 복구해 나중에 다시 재시도할 수 있게 합니다.

Worker는 incident sync 결과 새 alert가 생성되거나 retry API가 호출되면 별도 `deliver_pending_email_alerts` task를 queue에 등록합니다. 이 task는 `SMTP_HOST`와 `SMTP_FROM_EMAIL`이 설정되어 있으면 pending email alert를 SMTP로 발송하고 `SENT`로 기록합니다. SMTP 설정이 없으면 pending alert를 실패 처리하지 않고 건너뜁니다. 수신자 email이 없거나 SMTP 발송 오류가 발생하면 해당 alert를 `FAILED`로 기록합니다.

## AI diagnosis schemas

현재 API에는 AI diagnosis 실행 엔드포인트나 LLM 호출이 없습니다. 대신 후속 서비스가 사용할 `AIDiagnosisInput` Pydantic 스키마와 저장된 CheckRun 결과를 이 스키마로 조립하는 builder 서비스를 제공합니다.

`aim_api.services.ai_diagnosis_inputs.build_ai_diagnosis_input`은 CheckRun 결과, score/risk, 비교 결과, ScenarioRun evidence, artifact metadata, AI에 전달할 evidence item과 statement를 하나의 입력 계약으로 묶습니다. confirmed observation과 evidence-based inference는 evidence id를 반드시 참조해야 하며, unknown cause statement는 원인을 알 수 없는 이유를 포함해야 합니다.

또한 `AIDiagnosisReport` output 스키마와 `aim_api.services.ai_diagnosis_reports.build_ai_diagnosis_report` deterministic generator 서비스를 제공합니다. Report는 결정론적 score/risk를 authoritative summary로 포함하고, top issue, improved area, regressed area가 입력 evidence id를 참조하도록 제한합니다. `WARNING` 또는 `RISK` report는 최소 1개의 top issue를 포함해야 합니다. Generator는 `score_result`가 없거나 score evidence가 없으면 report를 생성하지 않습니다.

AIReport 저장을 위한 `ai_reports` 테이블, SQLAlchemy 모델, `aim_api.services.ai_reports.generate_and_record_ai_report` 저장 서비스, CheckRun별 전체 조회 API, CheckRun 상세 응답의 요약 필드도 제공합니다. `ai_reports`는 CheckRun당 하나의 report를 저장하며, 조회와 필터링에 필요한 score/risk 요약 컬럼과 전체 report JSON payload를 함께 보존합니다. Worker는 AIReport 생성을 별도 retryable task로 분리하므로, AIReport 생성 실패가 CheckRun 상태를 실패로 바꾸지 않습니다.

자세한 설계 의도는 [AI diagnosis input architecture](../../docs/architecture/ai-diagnosis-input.md)와 [AI diagnosis report architecture](../../docs/architecture/ai-diagnosis-report.md)를 참고합니다.

## 검증

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```
