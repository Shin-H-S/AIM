# Worker

가용성, Lighthouse, Playwright 및 AI 진단 작업을 실행하는 백그라운드 Worker가 위치합니다.

작업별 타임아웃과 실패 상태를 기록하고, 재시도가 중복 결과를 만들지 않도록 구현합니다. 원시 스캐너 출력과 정규화된 결과를 분리합니다.

## 로컬 실행

저장소 루트에서 PostgreSQL과 Redis를 실행한 뒤 Celery worker를 시작합니다.

```powershell
docker compose -f infra/compose.dev.yaml up -d postgres redis
uv run celery -A aim_worker.celery_app.celery_app worker --loglevel=INFO
```

현재 구현된 worker task는 CheckRun을 `RUNNING`으로 전환하고 HTTP availability scanner, SSL inspection, Lighthouse mobile scan을 실행합니다.

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

최종 HTTP 상태가 2xx 또는 3xx이고 HTTPS 인증서가 유효하며 Lighthouse 실행이 성공하면 CheckRun을 `COMPLETED`, timeout·connection failure·차단된 redirect·4xx·5xx·인증서 검증 실패·인증서 만료·Lighthouse 실행 실패는 `FAILED`로 기록합니다. HTTP availability와 SSL inspection 결과는 각각 `availability_results`, `ssl_results`에 정규화해 저장합니다. Lighthouse 결과 저장은 다음 단계에서 추가합니다.

Lighthouse CLI는 루트 Node 의존성으로 설치되며, 기본 실행 명령은 `corepack pnpm exec lighthouse`입니다. 필요한 경우 `LIGHTHOUSE_COMMAND`로 실행 명령을 바꿀 수 있습니다.
