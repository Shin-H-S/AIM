# 백업 복구 런북

운영 데이터(단일 VM, Docker Compose — 2026-07-17부터 오라클 클라우드 도쿄 A1)의 백업 구조와 복구 절차.
마지막 리허설: **2026-07-14 (성공, GCP 시절 — DB만)**.

## 백업 구조

| 계층 | 내용 | 보존 | 복구 지점 |
|---|---|---|---|
| 로컬 덤프 | 매일 03:00 KST 크론 → `~/backups/aim/aim-*.sql.gz` | 14일 (`AIM_BACKUP_RETENTION_DAYS`) | 최대 24시간 전 |
| 오프박스 덤프 | 같은 크론이 OCI Object Storage `aim-db-backups` 버킷 `postgres/`로 업로드 | 수명 주기 미설정 (일 ~224KB라 무료 한도 영향 없음) | 최대 24시간 전 |
| 로컬 아티팩트 | 매주 월 03:30 KST 크론 → `~/backups/aim/aim-artifacts-*.tar.gz` | 28일 (`AIM_ARTIFACT_BACKUP_RETENTION_DAYS`) | 최대 7일 전 |
| 오프박스 아티팩트 | 같은 크론이 같은 버킷 `artifacts/`로 업로드 | 수명 주기 미설정 | 최대 7일 전 |
| (레거시) GCS 덤프 | `gs://aim-db-backups-ai-manager-501413/postgres/` — 오라클 이전 전 업로드분 | 30일 수명 주기로 자연 소멸 | 2026-07-17 이전 |

**아티팩트를 왜 따로 받나**: 실패 스크린샷·Lighthouse JSON은 AI 리포트가 참조하는 근거
본체다. DB에는 `storage_path`만 있으므로, 덤프만 복원하면 **모든 근거 링크가 깨진 리포트**가
복구된다. 덤프보다 크고 한 번 쓰이면 변하지 않으므로 주간으로 나눠 받는다.

- 크론 2줄 (VM 시계는 UTC):
  - `0 18 * * * $HOME/AIM/scripts/backup-postgres.sh >> $HOME/backups/aim/backup.log 2>&1`
  - `30 18 * * 0 $HOME/AIM/scripts/backup-artifacts.sh >> $HOME/backups/aim/backup.log 2>&1`
- 업로드는 **쓰기 전용 Pre-Authenticated Request URL**(`~/.config/aim/backup-par-url`, chmod 600)로 한다.
  서버에 자격증명이 없고 URL로는 읽기·목록·삭제가 불가능하다. 덮어쓰기 변조는 버킷 **오브젝트
  버전 관리**가 방어한다. GCS SA 키·HMAC 발급이 `iam.disableServiceAccountKeyCreation` 정책으로
  막혀 키리스 방식을 채택했다(2026-07-17).
- **PAR 만료 관리**: PAR에는 만료일이 있다(발급 시 +1년 권장). 만료되면 업로드가 조용히 실패하기
  시작한다(`backup.log`에 curl 오류, 로컬 덤프는 계속 쌓임). 갱신: OCI 콘솔 → 버킷 →
  Pre-Authenticated Requests → 새로 발급(Permit object writes) → 서버 파일 교체.
- **백업에 없는 것**: `.env.production`, `~/.config/aim/deploy-token`, `~/.config/aim/scenario-secrets/`,
  `~/.config/aim/ops-webhook`, `~/.config/aim/backup-par-url` — VM 전체 유실 시 수동 재구성이 필요하다.
- 아티팩트 백업은 `docker compose exec api tar` 로 실행 중인 컨테이너에서 뜬다. 아카이브 직후
  `gzip -t` 로 무결성을 확인하므로, 깨진 tar가 성공으로 보고되지 않는다. 아카이브가
  `AIM_ARTIFACT_BACKUP_WARN_BYTES`(기본 2GiB)를 넘으면 로그에 경고가 남는다 —
  **보존 정리 태스크가 동작하지 않고 있다는 신호**다.
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

### A-2. 아티팩트도 함께 되돌려야 할 때

DB만 과거 시점으로 되돌리면 그 시점 이후 생성된 아티팩트 파일은 남아 있지만 참조하는
레코드가 없어 고아가 되고, 반대로 되돌린 리포트가 참조하는 파일은 이미 정리됐을 수 있다.
근거 링크까지 복구해야 하면 아티팩트도 같은 시점 사본으로 맞춘다.

```bash
# 쓰기 경로가 멈춘 상태(위 1단계)에서 실행한다.
# 아티팩트는 주간 백업이라 덤프보다 오래된 시점일 수 있다 — 어느 쪽이 기준인지 먼저 정할 것.
ls -t ~/backups/aim/aim-artifacts-*.tar.gz | head -5

# 기존 내용을 비우고 아카이브를 푼다 (파괴적 — 대상 확인 후 실행)
docker compose --env-file .env.production -f infra/compose.yaml exec -T api \
  sh -c 'rm -rf /data/aim/artifacts/* /data/aim/artifacts/.[!.]*' || true
docker compose --env-file .env.production -f infra/compose.yaml exec -T api \
  tar -xzf - -C /data/aim/artifacts < <최신아티팩트아카이브>

# 검증: 아티팩트 레코드 수와 실제 파일 수가 근사한지
docker compose --env-file .env.production -f infra/compose.yaml exec -T api \
  sh -c 'find /data/aim/artifacts -type f | wc -l'
source <(grep -E '^POSTGRES_(USER|DB)=' .env.production)
docker compose --env-file .env.production -f infra/compose.yaml exec -T postgres \
  psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from artifacts;"
```

## 절차 B — VM 전체 유실

실제 수행 기록: 2026-07-17 GCP e2-medium → 오라클 A1 이전이 사실상 이 절차였다(성공).

1. 새 VM 생성(오라클 A1 등) 후 docker 설치, 저장소 clone. 스왑 4GB.
   오라클이면 OS iptables **와** VCN 보안 목록 양쪽에서 80/443을 열어야 한다.
2. 수동 재구성: `.env.production`(시크릿 포함), `~/.config/aim/deploy-token`(웹에서 재발급),
   `~/.config/aim/scenario-secrets/secrets.env`(디렉토리 2750·파일 640·그룹 999),
   `~/.config/aim/ops-webhook`, `~/.config/aim/backup-par-url`(PAR 재발급), 크론 3줄(DB 백업·아티팩트 백업·헬스).
3. `docker compose ... up -d` 로 기동 후 **절차 A의 2~4단계**로 오프박스 덤프 복원,
   이어서 **절차 A-2**로 오프박스 아티팩트 아카이브 복원. 아티팩트를 건너뛰면 서비스는
   뜨지만 과거 리포트의 근거 링크가 전부 깨진다.
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
