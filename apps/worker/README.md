# Worker

가용성, Lighthouse, Playwright 및 AI 진단 작업을 실행하는 백그라운드 Worker가 위치합니다.

작업별 타임아웃과 실패 상태를 기록하고, 재시도가 중복 결과를 만들지 않도록 구현합니다. 원시 스캐너 출력과 정규화된 결과를 분리합니다.

## 로컬 실행

저장소 루트에서 PostgreSQL과 Redis를 실행한 뒤 Celery worker를 시작합니다.

```powershell
docker compose -f infra/compose.dev.yaml up -d postgres redis
uv run playwright install chromium
uv run celery -A aim_worker.celery_app.celery_app worker --loglevel=INFO
```

현재 구현된 worker task는 CheckRun을 `RUNNING`으로 전환하고 HTTP availability scanner, SSL inspection, Lighthouse mobile scan을 실행합니다. ScenarioRun task는 저장된 Playwright step을 브라우저에서 순서대로 실행하고 StepResult를 기록합니다.

scanner는 다음 항목을 측정하거나 판단합니다.

- HTTP status code
- response time
- redirect count
- HTTPS 사용 여부
- timeout 여부
- connection/request failure
- redirect destination SSRF-safe 재검증
- SSL certificate validity
- SSL expiration date
- SSL expiration remaining days
- Lighthouse performance score
- Lighthouse accessibility score
- Lighthouse SEO score
- Lighthouse best practices score
- Lighthouse LCP, CLS, TBT
- deterministic score and deployment risk
- previous-run comparison
- Playwright step action execution
- step-level pass/fail/skip result
- browser console error capture
- failed network request capture
- failure screenshot artifact storage

최종 HTTP 상태가 2xx 또는 3xx이고 HTTPS 인증서가 유효하며 Lighthouse 실행이 성공하면 CheckRun을 `COMPLETED`, timeout·connection failure·차단된 redirect·4xx·5xx·인증서 검증 실패·인증서 만료·Lighthouse 실행 실패는 `FAILED`로 기록합니다. HTTP availability, SSL inspection, Lighthouse metric 결과는 각각 `availability_results`, `ssl_results`, `lighthouse_results`에 정규화해 저장합니다. Lighthouse raw JSON은 `ARTIFACT_LOCAL_ROOT` 아래 로컬 파일로 저장하고 `artifacts` 테이블에는 metadata와 storage path만 기록합니다. scanner 결과와 같은 프로젝트의 최신 terminal ScenarioRun 결과 기준의 score와 risk gate 결과는 `score_results`에 저장하고, 같은 프로젝트의 직전 terminal check run이 있으면 `run_comparisons`에 score, performance, response time delta를 저장합니다.

ScenarioRun은 critical step 실패 시 해당 step을 `FAILED`, 이후 step을 `SKIPPED`로 기록하고 전체 run을 `FAILED`로 종료합니다. non-critical step 실패는 기록하되 이후 step을 계속 실행합니다. worker는 실행 중 발생한 `console.error`, failed network request, 실패 step screenshot을 failure evidence로 저장합니다. evidence message와 URL에 포함될 수 있는 token/password/API key 형태의 값은 저장 전에 마스킹하며, SSRF-safe 검증을 통과하지 못한 URL은 `[blocked-url]`로 저장합니다. 실패 screenshot 파일은 `ARTIFACT_LOCAL_ROOT` 아래 `scenario-runs/{scenario_run_id}/steps/{step_order}/failure.png` 경로에 저장하고, DB에는 artifact metadata와 `StepResult.failure_screenshot_artifact_id`만 기록합니다.

Lighthouse CLI는 루트 Node 의존성으로 설치되며, 기본 실행 명령은 `corepack pnpm exec lighthouse`입니다. 필요한 경우 `LIGHTHOUSE_COMMAND`로 실행 명령을 바꿀 수 있습니다.

로컬 artifact 저장 기본값은 다음과 같습니다.

```powershell
ARTIFACT_STORAGE_BACKEND=local
ARTIFACT_LOCAL_ROOT=artifacts
```
