#!/usr/bin/env bash
# AIM production PostgreSQL daily backup.
#
# VM crontab example (VM clock is UTC; 18:00 UTC = 03:00 KST):
#   0 18 * * * $HOME/AIM/scripts/backup-postgres.sh >> $HOME/backups/aim/backup.log 2>&1
set -euo pipefail

# cron runs with a minimal PATH that may miss docker.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

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

find "$BACKUP_DIR" -name 'aim-*.sql.gz' -mtime +"$RETENTION_DAYS" -delete

echo "backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
