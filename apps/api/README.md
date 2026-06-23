# API

FastAPI 기반 AIM HTTP API가 위치합니다.

인증, 프로젝트와 서비스 대상 관리, 소유권 검증, 스캔 요청 및 결과 조회를 담당합니다. 장시간 실행되는 스캔은 요청 프로세스에서 실행하지 않고 Worker에 전달합니다.

## 로컬 실행

저장소 루트에서 의존성을 설치하고 개발 서버를 실행합니다.

```powershell
uv sync
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

## 검증

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```
