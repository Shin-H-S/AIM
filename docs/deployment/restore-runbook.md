# PostgreSQL 백업 복구 런북

운영 DB(단일 GCP VM, Docker Compose)의 백업 구조와 복구 절차. 마지막 리허설: **2026-07-14 (성공)**.

## 백업 구조

| 계층 | 내용 | 보존 | 복구 지점 |
|---|---|---|---|
| 로컬 덤프 | 매일 03:00 KST 크론 → `~/backups/aim/aim-*.sql.gz` | 14일 (`AIM_BACKUP_RETENTION_DAYS`) | 최대 24시간 전 |
| 오프박스 덤프 | 같은 크론이 `gs://aim-db-backups-ai-manager-501413/postgres/`로 업로드 | 30일 (버킷 수명 주기) | 최대 24시간 전 |
| 디스크 스냅샷 | GCP 주간 스케줄(`aim-weekly-snapshot`, 일요일 18:00 UTC) | 28일 | 최대 1주 전 |

- 크론: `0 18 * * * $HOME/AIM/scripts/backup-postgres.sh >> $HOME/backups/aim/backup.log 2>&1` (VM 시계는 UTC)
- 업로드에는 VM 서비스 계정의 버킷 objectCreator 권한과 `storage-rw` 스코프가 필요하다.
- **덤프에 없는 것**: `.env.production`, `~/.config/aim/deploy-token`, `~/.config/aim/scenario-secrets/` — 디스크 스냅샷에는 포함되지만, VM 전체 유실 시에는 수동 재구성이 필요하다.

## 절차 A — 데이터만 복구 (VM은 정상, 잘못된 데이터/삭제 복구)

```bash
cd ~/AIM
# 1) 쓰기 경로 정지 (postgres·caddy는 유지)
docker compose --env-file .env.production -f infra/compose.yaml stop api worker beat web

# 2) 복원할 덤프 선택 — 로컬 또는 GCS에서
ls -t ~/backups/aim/aim-*.sql.gz | head -5
# gcloud storage ls gs://aim-db-backups-ai-manager-501413/postgres/   # 오프박스에서 받을 때
# gcloud storage cp gs://.../postgres/aim-YYYYMMDD-HHMMSS.sql.gz /tmp/

# 3) DB 재생성 후 복원 (파괴적 — 대상 확인 후 실행)
source <(grep -E '^POSTGRES_(USER|DB)=' .env.production)
docker compose --env-file .env.production -f infra/compose.yaml exec -T postgres \
  psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE \"$POSTGRES_DB\";" -c "CREATE DATABASE \"$POSTGRES_DB\";"
gunzip -c <덤프파일> | docker compose --env-file .env.production -f infra/compose.yaml exec -T postgres \
  psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1

# 4) 마이그레이션 헤드 확인 후 재기동
docker compose --env-file .env.production -f infra/compose.yaml exec -T postgres \
  psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select version_num from alembic_version;"
docker compose --env-file .env.production -f infra/compose.yaml run --rm migrate   # 덤프가 옛 스키마면 헤드까지 적용
docker compose --env-file .env.production -f infra/compose.yaml up -d
```

## 절차 B — VM 전체 유실

1. 새 VM 생성(또는 주간 스냅샷에서 디스크 복원) 후 docker·gcloud 설치, 저장소 clone.
2. 수동 재구성: `.env.production`(시크릿 포함), `~/.config/aim/deploy-token`(웹에서 재발급),
   `~/.config/aim/scenario-secrets/secrets.env`(디렉토리 2750·파일 640·그룹 999), 크론 2줄(백업·기타), 스왑 2GB.
3. `docker compose ... up -d` 로 기동 후 **절차 A의 2~4단계**로 GCS 덤프 복원.
4. 고정 IP `aim-prod-ip` 를 새 VM에 연결(또는 DNS A 레코드 변경). Caddy가 인증서를 자동 재발급한다.
5. 검증: 로그인 → 수동 검사 1회 완주 → Discord 알림 수신 확인.

## 복원 리허설 (분기 1회 권장)

운영에 영향 없이 스크래치 컨테이너로 복원만 검증한다:

```bash
cd ~/AIM
source <(grep -E '^POSTGRES_(USER|PASSWORD|DB)=' .env.production)
IMG=$(docker inspect aim-postgres-1 --format '{{.Config.Image}}')
docker run -d --name aim-restore-rehearsal \
  -e POSTGRES_USER="$POSTGRES_USER" -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" -e POSTGRES_DB="$POSTGRES_DB" "$IMG"
until docker exec aim-restore-rehearsal pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do sleep 2; done
gunzip -c <최신덤프> | docker exec -i aim-restore-rehearsal \
  psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1
docker exec aim-restore-rehearsal psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c \
  "select version_num from alembic_version; select count(*) from check_runs;"
docker rm -f aim-restore-rehearsal
```

합격 기준: SQL 오류 0건, `alembic_version` = `migrations/versions/` 마지막 파일, 주요 테이블 행 수가 운영과 시점 차 내에서 일치.

### 리허설 기록

| 일자 | 덤프 | 결과 |
|---|---|---|
| 2026-07-14 | aim-20260713-180001.sql.gz (208K) | 성공 — 오류 0, alembic `20260713_0031`, 테이블 21, projects/users 운영 일치, check_runs 159(운영 164, 시점 차 5건) |
