# Web

Next.js 기반 AIM 사용자 인터페이스입니다.

## 로그인 (첫 페이지)

다음 경로가 서비스 첫 페이지이며 이메일·비밀번호 로그인을 수행합니다.

```text
/
```

브랜드 히어로와 로그인 폼을 함께 보여줍니다. 로그인 성공 시 Auth API에서 받은 JWT access token을 브라우저 저장소에 저장하고 Project dashboard(`/dashboard`)로 이동합니다. 저장된 세션이 이미 있으면 자동으로 dashboard로 이동하고, `/login` 경로는 `/`로 리다이렉트됩니다. 계정이 없으면 회원가입 화면으로 이동할 수 있습니다.

## Project dashboard

다음 경로에서 프로젝트별 최신 CheckRun 상태를 확인할 수 있습니다.

```text
/dashboard
```

로그인 세션을 자동으로 사용합니다. Dashboard는 프로젝트 목록을 조회한 뒤 프로젝트마다 최근 CheckRun 10개를 한 번의 목록 API 호출로 가져옵니다. 목록 응답에 점수 요약과 linked ScenarioRun이 포함되므로 별도 상세 조회 없이 최신 CheckRun 상태와 실패 사유, 최신 등급 미니 도넛과 점수 칩, 최근 검사 점수 추이 패널(종합·카테고리 토글), ScenarioRun 실패/진행 요약과 최근 결과 링크를 표시합니다.

Dashboard는 Project 생성 화면, Project 설정/domain verification 화면, CheckRun 이력 화면, Scenario 목록 화면, Alert overview 화면으로 이동하는 링크를 제공합니다. verified Project는 Dashboard에서 수동 CheckRun을 시작할 수 있으며, 생성 성공 후 CheckRun 결과 페이지로 이동합니다.

## Signup

다음 경로에서 이메일·비밀번호 회원가입을 수행할 수 있습니다.

```text
/signup
```

가입 성공 시 같은 자격 증명으로 자동 로그인하고 첫 Project 생성 화면으로 이동합니다. 중복 이메일, 입력값 오류, API 연결 실패를 명시적으로 안내합니다.

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

## CheckRun 이력 페이지

다음 경로에서 Project의 전체 CheckRun 이력을 조회할 수 있습니다.

```text
/projects/{projectId}/check-runs
```

상태·트리거·시각·실패 사유를 20개 단위 페이지네이션으로 보여주고, 각 항목에서 결과 페이지로 이동할 수 있습니다. 목록 위에는 최근 검사 점수 추이 라인 차트가 표시되며, 종합·가용성·기능 안정성·웹 성능·접근성·SEO/기본 품질 칩으로 시리즈를 전환할 수 있습니다(점수가 2회 미만인 항목은 칩이 숨겨집니다). Dashboard의 프로젝트 카드에서 `Runs` 링크로 진입합니다.

## CheckRun 결과 페이지

다음 경로에서 CheckRun 상태와 기본 scanner result를 확인할 수 있습니다.

```text
/projects/{projectId}/check-runs/{checkRunId}
```

페이지는 로그인 세션을 자동으로 사용합니다. CheckRun이 `QUEUED`, `RUNNING`, `ANALYZING` 상태일 때 단건 조회 API를 polling하고, `COMPLETED`, `FAILED`, `CANCELLED` 상태가 되면 polling을 멈춥니다.

결과 페이지는 위에서부터 결정론적 score/risk(등급 도넛·카테고리 링 게이지·점수 산출 근거), 직전 run 대비 변화와 baseline 대비 비교, 연결된 ScenarioRun 실패 요약, availability(응답 시간 임계값 바·권장 조치), SSL(권장 조치), Lighthouse(링 게이지·LCP/CLS/TBT 임계값 바·Top 개선 기회), artifact metadata와 다운로드 버튼, 그리고 맨 아래 AI 진단 요약과 상세 패널을 표시합니다. AI 이슈의 근거 링크를 누르면 페이지 안의 해당 결과 카드로 스크롤됩니다. 기술 용어 라벨 옆 `!` 마커에 마우스를 올리면 한국어 설명 툴팁이 표시됩니다.

## ScenarioRun 목록 페이지

다음 경로에서 특정 Scenario의 최근 실행 이력을 확인할 수 있습니다.

```text
/projects/{projectId}/scenarios/{scenarioId}/runs
```

페이지는 로그인 페이지에서 저장한 access token을 자동으로 사용하고, 필요한 경우 access token을 직접 입력해 다시 조회할 수 있습니다. 최근 ScenarioRun 상태 요약, queued/started/finished 시간, duration, failure reason, linked CheckRun 링크, ScenarioRun 결과 페이지 링크를 표시합니다. 목록은 20개 단위로 조회하며, 더 보기 버튼으로 다음 page를 이어서 불러올 수 있습니다.

## ScenarioRun 결과 페이지

다음 경로에서 ScenarioRun 상태와 step-level 결과를 확인할 수 있습니다.

```text
/projects/{projectId}/scenarios/{scenarioId}/runs/{scenarioRunId}
```

페이지는 로그인 페이지에서 저장한 access token을 자동으로 사용하고, 필요한 경우 access token을 직접 입력해 다시 조회할 수 있습니다. ScenarioRun이 `QUEUED`, `RUNNING` 상태일 때 단건 조회 API를 polling하고, `COMPLETED`, `FAILED`, `CANCELLED` 상태가 되면 polling을 멈춥니다. 결과 페이지는 linked CheckRun id, step 결과, error message, failure screenshot artifact id와 다운로드 버튼 및 미리보기, browser console error와 failed network request의 요약 및 상세 evidence를 표시합니다.

## Scenario 목록 페이지

다음 경로에서 프로젝트의 Scenario 목록과 step 정의를 확인할 수 있습니다.

```text
/projects/{projectId}/scenarios
```

페이지는 로그인 페이지에서 저장한 access token을 자동으로 사용하고, 필요한 경우 access token을 직접 입력해 다시 조회할 수 있습니다. Scenario 생성 폼으로 핵심 사용자 흐름과 step을 등록하고, 등록된 scenario 목록과 step을 표시합니다. 기존 scenario는 inline editor로 수정할 수 있고 삭제 전 확인 UI를 거쳐 삭제할 수 있습니다. active scenario에 대해 수동 ScenarioRun을 생성하며, ScenarioRun 목록 페이지와 생성 성공 후 ScenarioRun 결과 페이지 링크를 제공합니다.

## Alert overview 페이지

다음 경로에서 프로젝트의 Incident와 email Alert 이력을 확인할 수 있습니다.

```text
/projects/{projectId}/alerts
```

페이지는 로그인 페이지에서 저장한 access token을 자동으로 사용하고, 필요한 경우 access token을 직접 입력해 다시 조회할 수 있습니다. 현재 Project의 response time threshold, quality score threshold, Incident 목록, evidence JSON, email Alert 발송 상태와 관련 CheckRun 링크를 표시합니다. Email Alert 목록은 로드된 항목 기준으로 전체, 대기, 발송됨, 실패 상태 필터를 제공하고, 더 보기 버튼으로 다음 page를 이어서 불러올 수 있습니다.

Email alert 사용 여부와 수신자 email을 저장할 수 있습니다. 수신자 email을 비워두면 Project owner email을 사용합니다. FAILED 상태의 email Alert는 카드에서 발송 재시도를 요청할 수 있으며, 성공하면 상태가 PENDING으로 갱신됩니다.

Next.js 기반 AIM 사용자 인터페이스가 위치합니다.

대시보드, 프로젝트 설정, 스캔 상태와 결과, 회귀 비교 및 근거 기반 진단을 표시합니다. 로딩·빈 상태·오류·부분 결과를 명시적으로 처리하고 AI 추론을 관찰 사실과 구분합니다.

설정 페이지 하단의 위험 구역에서 Project 이름을 입력해 확인한 뒤 Project를 영구 삭제할 수 있습니다. CheckRun 결과 페이지에서는 대기·실행·분석 중인 CheckRun을 취소할 수 있습니다.

## 현재 구현

- Next.js App Router 기반 초기 화면
- TypeScript strict mode
- Tailwind CSS
- `NEXT_PUBLIC_API_URL` 기반 FastAPI `/health` 상태 확인
- 로딩, 성공, 실패 상태 표시
- 로그인 첫 페이지(`/`)와 로그인 후 `/dashboard` 라우팅, 공통 헤더
- Signup 화면과 첫 Project 생성 온보딩 연결
- Login 화면과 access token 저장
- Vitest 기반 유틸리티·시각화 로직 테스트
- Project dashboard와 프로젝트별 최신 CheckRun 표시
- Project dashboard의 최신 등급 미니 도넛과 점수 추이 패널
- Project dashboard의 최신 linked ScenarioRun 요약과 바로가기
- Project 생성·수정 화면
- Domain verification 안내 및 확인 화면
- Dashboard 수동 CheckRun 시작 버튼
- 결과·Scenario 페이지 저장 세션 자동 사용
- CheckRun 이력 페이지의 점수 추이 라인 차트(종합·카테고리 토글)
- CheckRun 결과 페이지
- 점수 카드의 등급 도넛·카테고리 링 게이지·점수 산출 근거 표시
- Lighthouse 링 게이지, LCP/CLS/TBT 임계값 바, Top 개선 기회 목록
- 응답 시간 임계값 바와 availability/SSL 권장 조치
- 기술 용어 한국어 설명 툴팁(`!` 마커)
- CheckRun AI 진단 요약 표시
- CheckRun AI 진단 상세 패널 표시(이슈별 근거 링크)
- Scenario 생성, 수정, 삭제, 목록 조회, 수동 실행 생성 페이지
- ScenarioRun 목록 페이지
- ScenarioRun 목록의 더 보기 pagination
- ScenarioRun 결과 페이지
- Alert overview 페이지
- Alert overview의 email alert 설정 저장 폼
- Alert overview의 FAILED email alert 발송 재시도 버튼
- Alert overview의 email alert 상태 필터와 더 보기 버튼
- 개발 전용 컴포넌트 갤러리 `/dev/result-preview` (프로덕션 빌드에서는 404)

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
