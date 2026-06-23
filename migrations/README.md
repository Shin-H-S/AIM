# Migrations

Alembic 데이터베이스 마이그레이션이 위치합니다.

데이터베이스 스키마를 수동으로 변경하지 않고 모든 변경을 마이그레이션으로 관리합니다.

저장소 루트에서 다음 명령을 실행합니다.

```powershell
uv run alembic -c migrations/alembic.ini upgrade head
uv run alembic -c migrations/alembic.ini current
```

모델 변경 후 새 마이그레이션을 생성할 때:

```powershell
uv run alembic -c migrations/alembic.ini revision --autogenerate -m "describe change"
```
