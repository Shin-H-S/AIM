# AIM

[![CI](https://github.com/Shin-H-S/AIM/actions/workflows/ci.yml/badge.svg)](https://github.com/Shin-H-S/AIM/actions/workflows/ci.yml)

AIM은 배포 후 웹서비스가 실제로 더 안정적이고 좋아졌는지 근거 기반으로 판단해주는 AI 품질 모니터링 플랫폼입니다.

단순 uptime checker가 아니라, 서비스 가용성·웹 품질·핵심 사용자 흐름·이전 실행 대비 회귀 여부를 함께 보고 배포 위험을 판단하는 것을 목표로 합니다.

## 현재 목표

AIM은 1인 개발자, 사이드 프로젝트 팀, 초기 스타트업처럼 전담 QA 인력이 부족한 팀이 다음 질문에 답할 수 있게 돕습니다.

> “이번 배포가 이전보다 실제로 더 안정적인가?”

MVP에서 우선 완성하려는 흐름은 다음과 같습니다.

1. 사용자가 프로젝트와 서비스 URL을 등록합니다.
2. AIM이 URL과 도메인 소유권을 검증합니다.
3. 사용자가 CheckRun을 요청합니다.
4. Worker가 availability, SSL, Lighthouse, Playwright scenario를 실행합니다.
5. AIM이 결과와 artifact를 저장합니다.
6. AIM이 score, deployment risk, 이전 run 대비 변화를 계산합니다.
7. AIM이 수집 근거 기반 AI 진단 요약을 생성합니다.
8. Web 화면이 상태, 결과, 회귀, 우선 확인 항목을 보여줍니다.

상세 제품 범위와 개발 규칙은 [AGENTS.md](AGENTS.md)를 기준으로 합니다.

## 현재 구현 상태

### Foundation

- FastAPI API skeleton
- Next.js App Router 기반 Web skeleton
- PostgreSQL, Redis Docker Compose 개발 환경
- Alembic migration
- Email/password signup, login, logout, JWT 인증
- 사용자별 Project CRUD
- SSRF-safe URL validation
- HTML meta-tag 기반 도메인 소유권 확인

### Scan pipeline

- CheckRun 생성, 조회, 취소 API
- Redis/Celery 기반 비동기 scan queue
- HTTP availability scan
- SSL certificate inspection
- Lighthouse mobile scan
- 정규화된 availability, SSL, Lighthouse result 저장
- Lighthouse raw JSON local artifact 저장
- Artifact metadata 저장 및 다운로드 API
- CheckRun result polling API

### Functional testing

- Playwright scenario 정의 API
- 지원 step action:
  - `navigate`
  - `click`
  - `fill`
  - `wait`
  - `assert_element_exists`
  - `assert_text_exists`
  - `assert_url`
  - `take_screenshot`
- ScenarioRun 생성 및 worker 실행
- StepResult 저장
- Browser console error 저장
- Failed network request 저장
- 실패 step screenshot artifact 저장
- CheckRun-linked ScenarioRun 실패 요약

### Scoring, comparison, diagnosis

- 결정론적 score/risk 계산
- Service unavailable, SSL failure, Lighthouse failure, critical scenario failure risk gate
- 직전 terminal CheckRun 대비 comparison 저장
- AI diagnosis input schema와 builder
- AI diagnosis report output schema
- deterministic AIReport generator
- AIReport DB 저장 모델과 migration
- CheckRun별 AIReport 조회 API
- CheckRun 상세 응답의 AIReport 요약 필드
- Worker 기반 AIReport 자동 생성 및 linked ScenarioRun 완료 후 갱신
- AIReport 생성 실패 재시도를 위한 별도 worker task

### Alerts and incidents

- Incident와 pending email Alert 저장 모델 및 migration
- terminal CheckRun 결과 기반 incident open/recovery 기록
- Service connection failure, repeated 5xx, critical scenario failure alert trigger
- Performance score와 response time threshold alert trigger
- 복구 감지 시 recovery alert 기록
- SMTP 설정 기반 pending email Alert 발송 worker task
- 프로젝트별 Incident 목록 조회 API
- 프로젝트별 Alert 목록 조회 API
- 프로젝트별 email alert 사용 여부와 수신자 설정 저장
- FAILED email Alert 수동 재시도 API

### Web UI

- API health 상태 확인
- Signup 화면과 첫 Project 생성 온보딩 연결
- Login 화면과 access token 저장
- Project dashboard에서 프로젝트별 최신 CheckRun 목록 표시
- Project dashboard에서 최신 CheckRun의 linked ScenarioRun 요약과 바로가기 표시
- Project 생성·수정 화면
- HTML meta-tag 기반 domain verification 안내 및 확인 화면
- Project dashboard에서 수동 CheckRun 시작
- 결과·Scenario 페이지의 저장된 로그인 세션 자동 사용
- CheckRun 결과 페이지
- CheckRun score/risk 표시
- AIReport 요약 및 상세 패널 표시
- 직전 run 대비 변화 표시
- linked ScenarioRun 실패 요약과 상세 페이지 링크
- Availability, SSL, Lighthouse 결과 표시
- Artifact 다운로드 버튼
- Scenario 생성, 수정, 삭제, 목록 조회, 수동 ScenarioRun 생성 페이지
- ScenarioRun 목록 페이지
- ScenarioRun 목록의 더 보기 pagination
- ScenarioRun 결과 페이지
- Step 결과, console/network evidence, 실패 screenshot 미리보기
- Incident와 email Alert 목록 overview 페이지
- Alert overview에서 email alert 사용 여부와 수신자 email 저장
- Alert overview에서 FAILED email Alert 발송 재시도
- Alert overview에서 email Alert 상태 필터와 더 보기 pagination

현재 Web에는 회원가입과 로그인 UI, Project dashboard와 결과·Scenario 페이지 세션 연결, Project 생성·수정 UI, domain verification 안내 화면, Scenario 생성 UI가 있습니다.

## 저장소 구조

```text
apps/
  web/            Next.js 사용자 인터페이스
  api/            FastAPI HTTP API
  worker/         스캔 및 분석 백그라운드 작업
packages/
  contracts/      서비스 경계에서 공유하는 계약
infra/            로컬 개발 및 배포 인프라
migrations/       데이터베이스 마이그레이션
docs/
  architecture/   시스템 구조와 주요 흐름
  api/            API 계약
  decisions/      아키텍처 결정 기록
scripts/          반복 가능한 개발 자동화
tests/            저장소 수준 통합·E2E 테스트
```

## 로컬 실행

### 1. 의존성 설치

```powershell
uv sync
corepack pnpm install
```

### 2. PostgreSQL과 Redis 실행

```powershell
docker compose -f infra/compose.dev.yaml up -d postgres redis
```

### 3. DB migration 적용

```powershell
uv run alembic -c migrations/alembic.ini upgrade head
```

### 4. API 실행

```powershell
uv run uvicorn aim_api.main:app --app-dir apps/api/src --reload
```

상태 확인:

```text
GET http://localhost:8000/health
GET http://localhost:8000/health/database
```

### 5. Worker 실행

처음 한 번 Chromium browser를 설치합니다.

```powershell
uv run playwright install chromium
```

Redis가 실행 중인 상태에서 worker를 시작합니다.

```powershell
uv run celery -A aim_worker.celery_app.celery_app worker --loglevel=INFO
```

### 6. Web 실행

```powershell
corepack pnpm web:dev
```

기본 API 주소는 다음 환경 변수를 사용합니다.

```powershell
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 주요 화면

### Project dashboard

```text
/
```

표시 항목:

- API health 상태
- 로그인 세션 또는 직접 입력한 access token 기반 프로젝트 목록 조회
- 프로젝트별 service URL, environment, verification 상태
- 프로젝트별 최신 CheckRun 상태와 실패 사유
- 최신 CheckRun에 연결된 ScenarioRun 실패/진행 요약과 최근 결과 링크
- Project 생성 화면 링크
- Project 설정 및 domain verification 화면 링크
- verified Project의 수동 CheckRun 시작 버튼
- 최신 CheckRun 결과 페이지 링크
- Scenario 목록 페이지 링크
- Incident와 Alert overview 페이지 링크

### Login

```text
/login
```

표시 항목:

- 이메일·비밀번호 로그인
- JWT access token 저장
- 로그인 성공 후 Project dashboard 이동
- 인증 실패와 API 연결 실패 안내

### Signup

```text
/signup
```

표시 항목:

- 이메일·비밀번호 회원가입
- 중복 이메일과 입력값 오류 안내
- 가입 성공 후 자동 로그인
- 첫 Project 생성 화면으로 이동

### Project 생성

```text
/projects/new
```

표시 항목:

- service URL, environment, description 입력
- scan interval, response time threshold, quality score threshold 입력
- 클라이언트 기본 URL 형식 검증
- 생성 성공 후 Project 설정 화면 이동

### Project 설정과 domain verification

```text
/projects/{projectId}/settings
```

표시 항목:

- Project 기본 정보 수정
- HTML meta-tag verification token 표시
- target service head에 추가할 meta tag 안내
- domain verification 실행 버튼
- verified/unverified 상태 표시

### CheckRun 결과

```text
/projects/{projectId}/check-runs/{checkRunId}
```

표시 항목:

- CheckRun 상태와 polling 상태
- score, grade, deployment risk
- AI 진단 요약
- AI 진단 상세 패널의 top issues, 개선/회귀 영역, generation warning
- risk gate reason
- 이전 run 대비 변화
- linked ScenarioRun 요약
- linked ScenarioRun 결과 및 ScenarioRun 목록 페이지 링크
- availability, SSL, Lighthouse 결과
- artifact metadata와 다운로드 버튼

### Scenario 목록

```text
/projects/{projectId}/scenarios
```

표시 항목:

- 등록된 scenario 목록
- 새 scenario 생성 폼
- 기존 scenario 수정 폼
- 삭제 전 확인 UI
- step 정의
- active scenario 수동 실행
- ScenarioRun 목록 페이지 링크
- 생성된 ScenarioRun 결과 페이지 링크

### ScenarioRun 목록

```text
/projects/{projectId}/scenarios/{scenarioId}/runs
```

표시 항목:

- 특정 Scenario의 최근 ScenarioRun 목록
- 더 보기 버튼을 통한 ScenarioRun 목록 pagination
- ScenarioRun 상태 요약
- queued/started/finished 시간
- duration과 failure reason
- linked CheckRun 결과 페이지 링크
- ScenarioRun 결과 페이지 링크

### ScenarioRun 결과

```text
/projects/{projectId}/scenarios/{scenarioId}/runs/{scenarioRunId}
```

표시 항목:

- ScenarioRun 상태
- step-level pass/fail/skip 결과
- error message
- browser console error
- failed network request
- failure screenshot 다운로드와 미리보기

### Alert overview

```text
/projects/{projectId}/alerts
```

표시 항목:

- Project response time threshold와 quality score threshold
- Incident 목록과 open/resolved 상태
- Incident evidence JSON
- Email Alert 목록과 pending/sent/failed 상태
- Email Alert 상태별 필터와 더 보기 pagination
- Email Alert 사용 여부와 수신자 email 설정
- FAILED Email Alert 발송 재시도
- 관련 CheckRun 결과 페이지 링크

수신자 email을 비워두면 Project owner email을 사용합니다. SMTP host/from email 같은 전역 발송 설정은 `.env`와 배포 환경에서 관리합니다.

## 배포

초기 운영 배포 목표는 GCP Compute Engine VM 한 대에 Docker Compose로 AIM 전체를 올리는 방식입니다.

```text
GCP VM
  ├─ Caddy
  ├─ Web
  ├─ API
  ├─ Worker
  ├─ Beat
  ├─ PostgreSQL
  └─ Redis
```

배포용 구성 파일:

- `apps/api/Dockerfile`
- `apps/worker/Dockerfile`
- `apps/web/Dockerfile`
- `infra/compose.yaml`
- `infra/Caddyfile`
- `infra/env.production.example`

자세한 VM 준비, 환경변수 작성, migration, 실행, 백업 절차는 [GCP VM Docker Compose 배포 가이드](docs/deployment/gcp-vm-compose.md)를 참고합니다.

## 주요 API

자세한 API 설명은 [apps/api/README.md](apps/api/README.md)를 참고합니다.

현재 사용할 수 있는 주요 API는 다음과 같습니다.

- Auth: `POST /auth/signup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`
- Projects: `POST /projects`, `GET /projects`, `GET /projects/{project_id}`, `PATCH /projects/{project_id}`, `DELETE /projects/{project_id}`
- Verification: `GET /projects/{project_id}/verification`, `POST /projects/{project_id}/verify`
- CheckRuns: `POST /projects/{project_id}/check-runs`, `GET /projects/{project_id}/check-runs`, `GET /projects/{project_id}/check-runs/{check_run_id}`, `POST /projects/{project_id}/check-runs/{check_run_id}/cancel`
- AIReport: `GET /projects/{project_id}/check-runs/{check_run_id}/ai-report`
- Scenarios: `POST /projects/{project_id}/scenarios`, `GET /projects/{project_id}/scenarios`, `GET /projects/{project_id}/scenarios/{scenario_id}`, `PATCH /projects/{project_id}/scenarios/{scenario_id}`, `DELETE /projects/{project_id}/scenarios/{scenario_id}`
- ScenarioRuns: `POST /projects/{project_id}/scenarios/{scenario_id}/runs`, `GET /projects/{project_id}/scenarios/{scenario_id}/runs`, `GET /projects/{project_id}/scenarios/{scenario_id}/runs/{scenario_run_id}`
- Incidents: `GET /projects/{project_id}/incidents`
- Alerts: `GET /projects/{project_id}/alerts`, `POST /projects/{project_id}/alerts/{alert_id}/retry`
- Artifacts: `GET /artifacts/{artifact_id}/download`

## 검증

### API와 Worker

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

### Web

```powershell
corepack pnpm web:lint
corepack pnpm web:typecheck
corepack pnpm web:test
corepack pnpm web:build
```

### CI

같은 검사를 GitHub Actions가 모든 pull request와 `main` push에서 자동 실행합니다(`.github/workflows/ci.yml`).

- `Python checks`: ruff lint/format, mypy, pytest
- `Web checks`: eslint, tsc, vitest, next build
- `Database migrations`: PostgreSQL service container에서 alembic `upgrade head` → `downgrade base` → `upgrade head` 왕복 검증

## 다음 개발 우선순위

1. ScenarioRun 목록 상태 필터 UI 추가
2. Project dashboard pagination/load more UI 추가

MVP가 완성될 때까지 Kubernetes, Kafka, microservice 분리, 결제, 복잡한 조직 권한 모델은 범위에 넣지 않습니다.
