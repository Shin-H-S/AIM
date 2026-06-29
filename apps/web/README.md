# Web

Next.js 기반 AIM 사용자 인터페이스입니다.

## CheckRun 결과 페이지

다음 경로에서 CheckRun 상태와 기본 scanner result를 확인할 수 있습니다.

```text
/projects/{projectId}/check-runs/{checkRunId}
```

현재 인증 UI는 아직 없으므로 로그인 API에서 받은 access token을 결과 페이지에 직접 입력합니다. 페이지는 CheckRun이 `QUEUED`, `RUNNING`, `ANALYZING` 상태일 때 단건 조회 API를 polling하고, `COMPLETED`, `FAILED`, `CANCELLED` 상태가 되면 polling을 멈춥니다. 결과 페이지는 결정론적 score/risk, 직전 run 대비 변화, 연결된 ScenarioRun 목록과 결과 페이지 링크, availability, SSL, Lighthouse metric 결과와 artifact metadata 및 다운로드 버튼을 표시합니다.

## ScenarioRun 결과 페이지

다음 경로에서 ScenarioRun 상태와 step-level 결과를 확인할 수 있습니다.

```text
/projects/{projectId}/scenarios/{scenarioId}/runs/{scenarioRunId}
```

현재 인증 UI는 아직 없으므로 로그인 API에서 받은 access token을 결과 페이지에 직접 입력합니다. 페이지는 ScenarioRun이 `QUEUED`, `RUNNING` 상태일 때 단건 조회 API를 polling하고, `COMPLETED`, `FAILED`, `CANCELLED` 상태가 되면 polling을 멈춥니다. 결과 페이지는 linked CheckRun id, step 결과, error message, failure screenshot artifact id와 다운로드 버튼, browser console error, failed network request를 표시합니다.

## Scenario 목록 페이지

다음 경로에서 프로젝트의 Scenario 목록과 step 정의를 확인할 수 있습니다.

```text
/projects/{projectId}/scenarios
```

현재 인증 UI는 아직 없으므로 로그인 API에서 받은 access token을 페이지에 직접 입력합니다. 페이지는 등록된 scenario 목록과 step을 표시하고, active scenario에 대해 수동 ScenarioRun을 생성합니다. 생성 성공 후 ScenarioRun 결과 페이지 링크를 제공합니다.

Next.js 기반 AIM 사용자 인터페이스가 위치합니다.

대시보드, 프로젝트 설정, 스캔 상태와 결과, 회귀 비교 및 근거 기반 진단을 표시합니다. 로딩·빈 상태·오류·부분 결과를 명시적으로 처리하고 AI 추론을 관찰 사실과 구분합니다.

## 현재 구현

- Next.js App Router 기반 초기 화면
- TypeScript strict mode
- Tailwind CSS
- `NEXT_PUBLIC_API_URL` 기반 FastAPI `/health` 상태 확인
- 로딩, 성공, 실패 상태 표시
- Vitest 기반 API 상태 확인 유틸리티 테스트
- CheckRun 결과 페이지
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
