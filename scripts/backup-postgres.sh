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
# 원격 보존 기간은 버킷 수명 주기(30일 삭제)가 담당하므로 여기서는 업로드만 한다.
# 빈 값으로 두면 업로드를 건너뛴다. 업로드 실패 시 로컬 사본은 남고 종료 코드 1.
BACKUP_BUCKET="${AIM_BACKUP_BUCKET:-gs://aim-db-backups-ai-manager-501413}"
if [ -n "$BACKUP_BUCKET" ]; then
  gcloud storage cp --no-user-output-enabled "$OUT" "$BACKUP_BUCKET/postgres/$(basename "$OUT")"
  echo "backup uploaded: $BACKUP_BUCKET/postgres/$(basename "$OUT")"
fi

find "$BACKUP_DIR" -name 'aim-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
