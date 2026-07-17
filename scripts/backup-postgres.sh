#!/usr/bin/env bash
# AIM production PostgreSQL daily backup.
#
# VM crontab example (VM clock is UTC; 18:00 UTC = 03:00 KST):
#   0 18 * * * $HOME/AIM/scripts/backup-postgres.sh >> $HOME/backups/aim/backup.log 2>&1
set -euo pipefail

# cron runs with a minimal PATH that may miss docker and the snap-installed gcloud.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${AIM_BACKUP_DIR:-$HOME/backups/aim}"
RETENTION_DAYS="${AIM_BACKUP_RETENTION_DAYS:-14}"

cd "$REPO_DIR"
mkdir -p "$BACKUP_DIR"

# Read the database name and user from the production env file.
source <(grep -E '^POSTGRES_(USER|DB)=' .env.production)

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/aim-$STAMP.sql.gz"

docker compose --env-file .env.production -f infra/compose.yaml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$OUT"

# An empty dump means the backup silently failed upstream.
[ -s "$OUT" ] || { echo "backup file is empty: $OUT" >&2; rm -f "$OUT"; exit 1; }

# 오프박스 사본: 백업이 DB와 같은 디스크에만 있으면 디스크 장애 때 함께 사라진다.
# 원격 보존: OCI Object Storage 버킷(오브젝트 버전 관리 on). 업로드는 쓰기 전용
# Pre-Authenticated Request URL로만 한다 — 서버에는 자격증명이 아예 없고 URL은
# 읽기·목록·삭제가 불가능해서, VM이 침해돼도 백업을 열람·삭제할 수 없다.
# (GCP 시절 objectCreator 생성 전용 설계를 오라클 이전(2026-07-17)에 맞춰 치환.
#  GCS SA 키·HMAC 발급이 iam.disableServiceAccountKeyCreation 정책으로 막혀
#  키리스 방식을 선택했다. 덮어쓰기 변조는 버킷 버전 관리가 방어한다.)
# URL 파일이 없으면 업로드를 건너뛴다(로컬 사본만 유지). 실패 시 로컬 사본은
# 남고 종료 코드 1. PAR에는 만료일이 있다 — 갱신 절차는 restore-runbook.md 참조.
PAR_URL_FILE="${AIM_BACKUP_PAR_URL_FILE:-$HOME/.config/aim/backup-par-url}"
if [ -f "$PAR_URL_FILE" ]; then
  curl -fsS -X PUT --upload-file "$OUT" \
    "$(cat "$PAR_URL_FILE")postgres/$(basename "$OUT")" >/dev/null
  echo "backup uploaded: oci bucket postgres/$(basename "$OUT")"
fi

find "$BACKUP_DIR" -name 'aim-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
