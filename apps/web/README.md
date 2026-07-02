# Web

Next.js 기반 AIM 사용자 인터페이스입니다.

## Project dashboard

다음 경로에서 프로젝트별 최신 CheckRun 상태를 확인할 수 있습니다.

```text
/
```

로그인 페이지에서 저장한 access token을 자동으로 사용합니다. 필요한 경우 access token을 직접 입력해 Dashboard를 갱신할 수도 있습니다. Dashboard는 현재 사용자 정보를 확인한 뒤 프로젝트 목록을 조회하고, 각 프로젝트의 최신 CheckRun 1개를 병렬로 가져와 service URL, environment, verification 상태, 최신 CheckRun 상태와 실패 사유, 결과 페이지 링크를 표시합니다.

Dashboard는 Project 생성 화면과 Project 설정/domain verification 화면으로 이동하는 링크를 제공합니다.

## Login

다음 경로에서 이메일·비밀번호 로그인을 수행할 수 있습니다.

```text
/login
```

로그인 성공 시 Auth API에서 받은 JWT access token을 브라우저 저장소에 저장하고 Project dashboard로 이동합니다. 회원가입 UI는 아직 없으므로 계정 생성은 API의 `POST /auth/signup`을 사용합니다.

## Project 생성 페이지

다음 경로에서 새 Project를 생성할 수 있습니다.

```text
/projects/new
```

페이지는 service URL, environment, description, scan interval, response time threshold, quality score threshold를 입력받습니다. URL은 클라이언트에서 기본 형식을 확인하고, API에서 SSRF-safe validation을 다시 수행합니다. 생성 성공 후 Project 설정 화면으로 이동합니다.

## Project 설정과 domain verification 페이지

다음 경로에서 Project 설정과 HTML meta-tag 기반 domain verification을 관리할 수 있습니다.

```text
/projects/{projectId}/settings
```

페이지는 Project 기본 정보를 수정하고, API에서 발급한 verification token과 meta tag를 표시합니다. 사용자는 target service의 HTML head에 meta tag를 추가한 뒤 확인 버튼으로 domain ownership을 검증합니다.

## CheckRun 결과 페이지

다음 경로에서 CheckRun 상태와 기본 scanner result를 확인할 수 있습니다.

```text
/projects/{projectId}/check-runs/{checkRunId}
```

현재 결과 페이지는 로그인 페이지에서 저장한 access token을 자동으로 읽지는 못하므로, access token을 직접 입력합니다. 페이지는 CheckRun이 `QUEUED`, `RUNNING`, `ANALYZING` 상태일 때 단건 조회 API를 polling하고, `COMPLETED`, `FAILED`, `CANCELLED` 상태가 되면 polling을 멈춥니다. 결과 페이지는 결정론적 score/risk, AI 진단 요약과 상세 패널, 직전 run 대비 변화, 연결된 ScenarioRun 실패 요약과 결과 페이지 링크, availability, SSL, Lighthouse metric 결과와 artifact metadata 및 다운로드 버튼을 표시합니다.

## ScenarioRun 결과 페이지

다음 경로에서 ScenarioRun 상태와 step-level 결과를 확인할 수 있습니다.

```text
/projects/{projectId}/scenarios/{scenarioId}/runs/{scenarioRunId}
```

현재 결과 페이지는 로그인 페이지에서 저장한 access token을 자동으로 읽지는 못하므로, access token을 직접 입력합니다. 페이지는 ScenarioRun이 `QUEUED`, `RUNNING` 상태일 때 단건 조회 API를 polling하고, `COMPLETED`, `FAILED`, `CANCELLED` 상태가 되면 polling을 멈춥니다. 결과 페이지는 linked CheckRun id, step 결과, error message, failure screenshot artifact id와 다운로드 버튼 및 미리보기, browser console error와 failed network request의 요약 및 상세 evidence를 표시합니다.

## Scenario 목록 페이지

다음 경로에서 프로젝트의 Scenario 목록과 step 정의를 확인할 수 있습니다.

```text
/projects/{projectId}/scenarios
```

현재 Scenario 목록 페이지는 로그인 페이지에서 저장한 access token을 자동으로 읽지는 못하므로, access token을 직접 입력합니다. 페이지는 등록된 scenario 목록과 step을 표시하고, active scenario에 대해 수동 ScenarioRun을 생성합니다. 생성 성공 후 ScenarioRun 결과 페이지 링크를 제공합니다.

Next.js 기반 AIM 사용자 인터페이스가 위치합니다.

대시보드, 프로젝트 설정, 스캔 상태와 결과, 회귀 비교 및 근거 기반 진단을 표시합니다. 로딩·빈 상태·오류·부분 결과를 명시적으로 처리하고 AI 추론을 관찰 사실과 구분합니다.

## 현재 구현

- Next.js App Router 기반 초기 화면
- TypeScript strict mode
- Tailwind CSS
- `NEXT_PUBLIC_API_URL` 기반 FastAPI `/health` 상태 확인
- 로딩, 성공, 실패 상태 표시
- Login 화면과 access token 저장
- Vitest 기반 API 상태 확인 유틸리티 테스트
- Project dashboard와 프로젝트별 최신 CheckRun 표시
- Project 생성·수정 화면
- Domain verification 안내 및 확인 화면
- CheckRun 결과 페이지
- CheckRun AI 진단 요약 표시
- CheckRun AI 진단 상세 패널 표시
- Scenario 목록 및 수동 실행 생성 페이지
- ScenarioRun 결과 페이지

## 실행

```powershell
corepack pnpm install
corepack pnpm web:dev
```

## 검증

```powershell
corepack pnpm web:lint
corepack pnpm web:typecheck
corepack pnpm web:test
corepack pnpm web:build
```
