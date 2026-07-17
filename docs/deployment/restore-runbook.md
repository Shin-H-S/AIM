# PostgreSQL 백업 복구 런북

운영 DB(단일 VM, Docker Compose — 2026-07-17부터 오라클 클라우드 도쿄 A1)의 백업 구조와 복구 절차.
마지막 리허설: **2026-07-14 (성공, GCP 시절)**.

## 백업 구조

| 계층 | 내용 | 보존 | 복구 지점 |
|---|---|---|---|
| 로컬 덤프 | 매일 03:00 KST 크론 → `~/backups/aim/aim-*.sql.gz` | 14일 (`AIM_BACKUP_RETENTION_DAYS`) | 최대 24시간 전 |
| 오프박스 덤프 | 같은 크론이 OCI Object Storage `aim-db-backups` 버킷 `postgres/`로 업로드 | 수명 주기 미설정 (일 ~224KB라 무료 한도 영향 없음) | 최대 24시간 전 |
| (레거시) GCS 덤프 | `gs://aim-db-backups-ai-manager-501413/postgres/` — 오라클 이전 전 업로드분 | 30일 수명 주기로 자연 소멸 | 2026-07-17 이전 |

- 크론: `0 18 * * * $HOME/AIM/scripts/backup-postgres.sh >> $HOME/backups/aim/backup.log 2>&1` (VM 시계는 UTC)
- 업로드는 **쓰기 전용 Pre-Authenticated Request URL**(`~/.config/aim/backup-par-url`, chmod 600)로 한다.
  서버에 자격증명이 없고 URL로는 읽기·목록·삭제가 불가능하다. 덮어쓰기 변조는 버킷 **오브젝트
  버전 관리**가 방어한다. GCS SA 키·HMAC 발급이 `iam.disableServiceAccountKeyCreation` 정책으로
  막혀 키리스 방식을 채택했다(2026-07-17).
- **PAR 만료 관리**: PAR에는 만료일이 있다(발급 시 +1년 권장). 만료되면 업로드가 조용히 실패하기
  시작한다(`backup.log`에 curl 오류, 로컬 덤프는 계속 쌓임). 갱신: OCI 콘솔 → 버킷 →
  Pre-Authenticated Requests → 새로 발급(Permit object writes) → 서버 파일 교체.
- **덤프에 없는 것**: `.env.production`, `~/.config/aim/deploy-token`, `~/.config/aim/scenario-secrets/`,
  `~/.config/aim/ops-webhook`, `~/.config/aim/backup-par-url` — VM 전체 유실 시 수동 재구성이 필요하다.
- 후속 과제: 오라클 부트 볼륨 백업 정책 미적용(무료 한도 내 주간 백업 가능) — GCP 주간 스냅샷의 대체물.

## 절차 A — 데이터만 복구 (VM은 정상, 잘못된 데이터/삭제 복구)

```bash
cd ~/AIM
# 1) 쓰기 경로 정지 (postgres·caddy는 유지)
docker compose --env-file .env.production -f infra/compose.yaml stop api worker beat web

# 2) 복원할 덤프 선택 — 로컬 또는 오프박스에서
ls -t ~/backups/aim/aim-*.sql.gz | head -5
# 오프박스에서 받을 때: 업로드 PAR은 쓰기 전용이라 다운로드가 안 된다.
# OCI 콘솔(버킷 → 객체 → Download)로 받거나, 사용자 인증된 OCI CLI로:
#   oci os object get -bn aim-db-backups --name postgres/aim-YYYYMMDD-HHMMSS.sql.gz --file /tmp/aim-restore.sql.gz

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

실제 수행 기록: 2026-07-17 GCP e2-medium → 오라클 A1 이전이 사실상 이 절차였다(성공).

1. 새 VM 생성(오라클 A1 등) 후 docker 설치, 저장소 clone. 스왑 4GB.
   오라클이면 OS iptables **와** VCN 보안 목록 양쪽에서 80/443을 열어야 한다.
2. 수동 재구성: `.env.production`(시크릿 포함), `~/.config/aim/deploy-token`(웹에서 재발급),
   `~/.config/aim/scenario-secrets/secrets.env`(디렉토리 2750·파일 640·그룹 999),
   `~/.config/aim/ops-webhook`, `~/.config/aim/backup-par-url`(PAR 재발급), 크론 2줄(백업·헬스).
3. `docker compose ... up -d` 로 기동 후 **절차 A의 2~4단계**로 오프박스 덤프 복원.
4. DNS A 레코드(`qaaimsync.com`, `api`)를 새 VM IP로 변경(Cloudflare, 프록시 OFF 유지).
   Caddy가 인증서를 자동 재발급한다.
5. 검증: 로그인 → 수동 검사 1회 완주 → Discord 알림 수신 확인.
   측정 위치(리전)가 바뀌었다면 정기 검사 몇 회 후 베이스라인을 재지정한다.

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
