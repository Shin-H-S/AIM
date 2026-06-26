# Infrastructure

Docker Compose를 포함한 로컬 개발 및 초기 배포 설정을 관리합니다.

현재 개발 구성은 PostgreSQL과 Redis를 제공합니다. MinIO는 아티팩트 저장 기능을 구현할 때 추가합니다.

저장소 루트에서 실행합니다.

```powershell
docker compose -f infra/compose.dev.yaml up -d postgres redis
docker compose -f infra/compose.dev.yaml ps
```

종료:

```powershell
docker compose -f infra/compose.dev.yaml down
```

데이터 볼륨까지 삭제하려면 명시적으로 `--volumes`를 추가해야 합니다.
