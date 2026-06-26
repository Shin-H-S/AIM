# Worker

가용성, Lighthouse, Playwright 및 AI 진단 작업을 실행하는 백그라운드 Worker가 위치합니다.

작업별 타임아웃과 실패 상태를 기록하고, 재시도가 중복 결과를 만들지 않도록 구현합니다. 원시 스캐너 출력과 정규화된 결과를 분리합니다.

## 로컬 실행

저장소 루트에서 PostgreSQL과 Redis를 실행한 뒤 Celery worker를 시작합니다.

```powershell
docker compose -f infra/compose.dev.yaml up -d postgres redis
uv run celery -A aim_worker.celery_app.celery_app worker --loglevel=INFO
```

현재 구현된 worker task는 CheckRun을 `RUNNING`으로 전환하고, 아직 HTTP availability scanner가 없다는 명시적 사유로 `FAILED`를 기록하는 큐 연결 골격입니다.
