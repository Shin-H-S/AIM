# GCP VM Docker Compose 배포 가이드

이 문서는 AIM을 GCP Compute Engine VM 한 대에서 Docker Compose로 운영하기 위한 최소 배포 절차입니다.

초기 MVP 운영 목표는 단순합니다.

```text
GCP VM
  ├─ Caddy
  ├─ Next.js Web
  ├─ FastAPI API
  ├─ Celery Worker
  ├─ Celery Beat
  ├─ PostgreSQL
  ├─ Redis
  └─ local artifact volume
```

Kubernetes, Kafka, 마이크로서비스 분리는 MVP 배포 범위에 넣지 않습니다.

## 1. 권장 VM 스펙

| 항목 | 권장값 |
|---|---|
| Machine type | `e2-standard-4` |
| OS | Ubuntu 24.04 LTS x86/64 |
| Boot disk | Balanced persistent disk 100GB |
| External IP | Static external IP |
| Firewall | 80, 443 허용 |
| SSH | 가능하면 내 IP 또는 IAP로 제한 |

비용을 줄여야 하면 `e2-standard-2`와 50GB 디스크로 시작할 수 있습니다. 이 경우 worker concurrency는 `1`로 유지합니다.

## 2. DNS 준비

운영 배포는 Web과 API를 별도 hostname으로 둡니다.

```text
aim.example.com      → VM static external IP
api.aim.example.com  → VM static external IP
```

DNS에는 다음 레코드를 추가합니다.

```text
Type: A
Name: aim
Value: VM static external IP

Type: A
Name: api.aim
Value: VM static external IP
```

실제 도메인에 맞게 `aim`과 `api.aim` 부분은 조정할 수 있습니다.

## 3. VM 기본 패키지 설치

VM에 SSH 접속 후 실행합니다.

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg git
```

Docker 공식 저장소를 추가합니다.

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
```

```bash
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

현재 사용자에게 Docker 권한을 부여합니다.

```bash
sudo usermod -aG docker $USER
```

SSH를 나갔다가 다시 접속한 뒤 확인합니다.

```bash
docker ps
docker compose version
```

## 4. AIM 저장소 준비

```bash
mkdir -p ~/apps
cd ~/apps
git clone https://github.com/Shin-H-S/AIM.git
cd AIM
```

배포하려는 브랜치 또는 태그로 이동합니다.

```bash
git checkout main
```

## 5. production 환경변수 작성

예시 파일을 복사합니다.

```bash
cp infra/env.production.example .env.production
```

반드시 바꿔야 하는 값입니다.

```text
AIM_WEB_HOSTNAME
AIM_API_HOSTNAME
NEXT_PUBLIC_API_URL
CORS_ALLOWED_ORIGINS
POSTGRES_PASSWORD
DATABASE_URL
JWT_SECRET_KEY
```

예시:

```env
AIM_WEB_HOSTNAME=aim.example.com
AIM_API_HOSTNAME=api.aim.example.com
NEXT_PUBLIC_API_URL=https://api.aim.example.com
CORS_ALLOWED_ORIGINS=["https://aim.example.com"]
POSTGRES_PASSWORD=replace-with-a-strong-database-password
DATABASE_URL=postgresql+psycopg://aim:replace-with-a-strong-database-password@postgres:5432/aim
JWT_SECRET_KEY=replace-with-a-long-random-production-secret
```

`JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, SMTP password, `ANTHROPIC_API_KEY`는 Git에 커밋하지 않습니다.

## 6. 이미지 빌드

```bash
docker compose --env-file .env.production -f infra/compose.yaml build
```

`NEXT_PUBLIC_API_URL`은 Next.js build 시점에 반영됩니다. API hostname을 바꿨다면 web 이미지를 다시 빌드합니다.

## 7. DB migration 실행

서비스를 올리기 전에 migration을 한 번 실행합니다.

```bash
docker compose --env-file .env.production -f infra/compose.yaml run --rm migrate
```

## 8. 서비스 실행

```bash
docker compose --env-file .env.production -f infra/compose.yaml up -d
```

상태 확인:

```bash
docker compose --env-file .env.production -f infra/compose.yaml ps
```

로그 확인:

```bash
docker compose --env-file .env.production -f infra/compose.yaml logs -f caddy
docker compose --env-file .env.production -f infra/compose.yaml logs -f api
docker compose --env-file .env.production -f infra/compose.yaml logs -f worker
```

## 9. 배포 확인

브라우저에서 확인합니다.

```text
https://aim.example.com
https://api.aim.example.com/health
https://api.aim.example.com/health/database
```

확인할 것:

- Web 화면이 열린다.
- API health가 `ok`를 반환한다.
- DB health가 `ok`를 반환한다.
- Worker 로그에 Redis 연결 오류가 없다.
- Caddy 로그에 인증서 발급 오류가 없다.

## 10. 운영 명령

서비스 재시작:

```bash
docker compose --env-file .env.production -f infra/compose.yaml restart
```

이미지 재빌드 후 반영:

```bash
docker compose --env-file .env.production -f infra/compose.yaml build
docker compose --env-file .env.production -f infra/compose.yaml up -d
```

서비스 중지:

```bash
docker compose --env-file .env.production -f infra/compose.yaml down
```

데이터까지 삭제하는 명령은 운영에서 사용하지 않습니다.

```bash
docker compose --env-file .env.production -f infra/compose.yaml down -v
```

## 11. 백업

PostgreSQL 백업:

```bash
mkdir -p ~/backups/aim
docker compose --env-file .env.production -f infra/compose.yaml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > ~/backups/aim/aim-$(date +%Y%m%d-%H%M%S).sql
```

초기에는 하루 1회 DB 백업과 주 1회 VM snapshot을 권장합니다.

## 12. 운영 주의사항

- 외부에는 80/443만 공개합니다.
- PostgreSQL `5432`, Redis `6379`, API `8000`, Web `3000` 포트는 외부에 열지 않습니다.
- `CELERY_WORKER_CONCURRENCY=1`로 시작합니다.
- Lighthouse와 Playwright는 CPU/RAM 사용량이 크므로 동시 scan 수를 작게 유지합니다.
- local artifact volume은 디스크를 사용하므로 주기적으로 용량을 확인합니다.
- GCP Billing budget alert를 설정합니다.

## 13. 현재 제한

- artifact storage는 현재 local backend만 구현되어 있습니다.
- Cloud Storage, Secret Manager, Cloud SQL 분리는 이후 단계입니다.
- 이메일 발송은 SMTP 설정이 있어야 실제 전송됩니다.
- `ANTHROPIC_API_KEY`가 비어 있으면 deterministic AI report generator를 사용합니다.
