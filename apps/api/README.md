# API

FastAPI 기반 AIM HTTP API가 위치합니다.

인증, 프로젝트와 서비스 대상 관리, 소유권 검증, 스캔 요청 및 결과 조회를 담당합니다. 장시간 실행되는 스캔은 요청 프로세스에서 실행하지 않고 Worker에 전달합니다.

## 로컬 실행

저장소 루트에서 의존성을 설치하고 PostgreSQL과 개발 서버를 실행합니다.

```powershell
uv sync
docker compose -f infra/compose.dev.yaml up -d postgres
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

## 프로젝트 API

현재 프로젝트 CRUD 기반 API가 제공됩니다. 인증과 프로젝트 소유권 검사는 아직 포함하지 않았으며, 다음 인증 작업에서 연결합니다.

지원 엔드포인트:

- `POST /projects`
- `GET /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`
- `DELETE /projects/{project_id}`

프로젝트는 다음 정보를 저장합니다.

- 이름
- 서비스 URL
- 설명
- 환경: `development`, `staging`, `production`
- 스캔 주기
- 응답 시간 임계값
- 품질 점수 임계값

서비스 URL은 HTTP/HTTPS 형식만 허용합니다. SSRF 방어를 포함한 전체 URL 검증은 별도 작업에서 구현합니다.

## 검증

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```
