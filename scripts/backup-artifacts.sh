#!/usr/bin/env bash
# AIM production artifact backup.
#
# 왜 DB 백업과 분리했나: 아티팩트(실패 스크린샷·Lighthouse JSON)는 덤프보다
# 훨씬 크고 한 번 쓰이면 변하지 않는다. 매일 전량 tar를 뜨는 것은 낭비이고,
# 검증된 DB 백업 경로에 큰 작업을 얹어 함께 실패하게 만들 이유도 없다.
# 그래서 주간 크론으로 따로 돈다.
#
# VM crontab example (VM clock is UTC; 일요일 18:30 UTC = 월요일 03:30 KST):
#   30 18 * * 0 $HOME/AIM/scripts/backup-artifacts.sh >> $HOME/backups/aim/backup.log 2>&1
set -euo pipefail

# cron runs with a minimal PATH that may miss docker.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${AIM_BACKUP_DIR:-$HOME/backups/aim}"
# 아티팩트 아카이브는 덤프보다 크므로 로컬 사본을 덜 오래 들고 있는다.
# 주간 실행 기준 28일 = 사본 4개.
RETENTION_DAYS="${AIM_ARTIFACT_BACKUP_RETENTION_DAYS:-28}"
# 이 크기를 넘으면 경고한다 — 보존 정책이 동작하지 않고 있다는 신호다.
WARN_BYTES="${AIM_ARTIFACT_BACKUP_WARN_BYTES:-2147483648}" # 2 GiB

cd "$REPO_DIR"
mkdir -p "$BACKUP_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/aim-artifacts-$STAMP.tar.gz"

COMPOSE=(docker compose --env-file .env.production -f infra/compose.yaml)

# api 컨테이너가 아티팩트 볼륨을 /data/aim/artifacts 로 마운트하고 있다.
# 별도 이미지를 받지 않고 이미 떠 있는 컨테이너에서 그대로 tar 한다.
# 실행 중 새 파일이 쓰여도 tar는 그 시점 스냅샷을 남기므로, 최악의 경우
# 마지막 검사 하나가 빠질 뿐 아카이브 자체는 온전하다.
"${COMPOSE[@]}" exec -T api tar -czf - -C /data/aim/artifacts . > "$OUT"

# 빈 파일은 상류에서 조용히 실패했다는 뜻이다(아티팩트가 0건이어도 tar 헤더는 남는다).
[ -s "$OUT" ] || { echo "artifact backup file is empty: $OUT" >&2; rm -f "$OUT"; exit 1; }

# 아카이브가 실제로 열리는지 확인한다 — 깨진 tar를 성공으로 보고하면
# 복구 시점에야 알게 된다.
gzip -t "$OUT"

SIZE_BYTES="$(stat -c %s "$OUT")"
if [ "$SIZE_BYTES" -gt "$WARN_BYTES" ]; then
  echo "warning: artifact archive is $(du -h "$OUT" | cut -f1); check the retention task" >&2
fi

# 오프박스 사본: 백업이 아티팩트와 같은 디스크에만 있으면 디스크 장애 때 함께
# 사라진다. DB 백업과 같은 쓰기 전용 PAR URL을 쓰되 prefix만 artifacts/ 로 나눈다.
# 자세한 근거와 PAR 갱신 절차는 scripts/backup-postgres.sh 와 restore-runbook.md 참조.
PAR_URL_FILE="${AIM_BACKUP_PAR_URL_FILE:-$HOME/.config/aim/backup-par-url}"
if [ -f "$PAR_URL_FILE" ]; then
  curl -fsS -X PUT --upload-file "$OUT" \
    "$(cat "$PAR_URL_FILE")artifacts/$(basename "$OUT")" >/dev/null
  echo "artifact backup uploaded: oci bucket artifacts/$(basename "$OUT")"
fi

find "$BACKUP_DIR" -name 'aim-artifacts-*.tar.gz' -mtime +"$RETENTION_DAYS" -delete

echo "artifact backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
