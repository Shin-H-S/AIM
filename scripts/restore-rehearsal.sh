#!/usr/bin/env bash
# 백업 복원 리허설 — 운영에 영향 없이 "이 백업으로 실제 복구가 되는가"를 검증한다.
#
# 복원해 본 적 없는 백업은 백업이 아니다. 이 스크립트는 스크래치 postgres
# 컨테이너에 최신 덤프를 실제로 복원하고, 아티팩트 아카이브의 무결성을
# 검사한 뒤, 합격 기준을 자동으로 판정한다. 운영 컨테이너·볼륨은 건드리지
# 않는다.
#
# 사용법 (VM의 저장소 루트 기준, 분기 1회 권장 — docs/deployment/restore-runbook.md):
#   scripts/restore-rehearsal.sh              # 최신 로컬 덤프·아카이브로
#   scripts/restore-rehearsal.sh <덤프.sql.gz>
set -euo pipefail

# AIM_REPO_DIR 오버라이드: 머지 전 검증처럼 저장소 밖 사본으로 돌릴 때 쓴다.
REPO_DIR="${AIM_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BACKUP_DIR="${AIM_BACKUP_DIR:-$HOME/backups/aim}"
CONTAINER="aim-restore-rehearsal"

cd "$REPO_DIR"
source <(grep -E '^POSTGRES_(USER|PASSWORD|DB)=' .env.production)

DUMP="${1:-$(ls -t "$BACKUP_DIR"/aim-[0-9]*.sql.gz 2>/dev/null | head -1)}"
[ -n "$DUMP" ] && [ -f "$DUMP" ] || { echo "복원할 덤프가 없습니다: $BACKUP_DIR" >&2; exit 1; }

STARTED=$(date +%s)
FAILURES=()

# 리허설 컨테이너가 남으면 다음 리허설이 이름 충돌로 실패한다 — 결과와 무관하게 지운다.
cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "== 1) 스크래치 postgres 기동 (운영과 같은 이미지)"
IMG=$(docker inspect aim-postgres-1 --format '{{.Config.Image}}')
docker run -d --name "$CONTAINER" \
  -e POSTGRES_USER="$POSTGRES_USER" -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -e POSTGRES_DB="$POSTGRES_DB" "$IMG" >/dev/null
until docker exec "$CONTAINER" pg_isready -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" 2>/dev/null; do
  sleep 2
done

echo "== 2) 덤프 복원: $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1))"
if ! gunzip -c "$DUMP" | docker exec -i "$CONTAINER" \
    psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 >/dev/null; then
  FAILURES+=("덤프 복원 중 SQL 오류")
fi

echo "== 3) 스키마 리비전 = 저장소 마이그레이션 헤드인가"
RESTORED_REV=$(docker exec "$CONTAINER" psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -c "select version_num from alembic_version;" 2>/dev/null || echo "MISSING")
# 헤드 리비전은 파일명 규칙(<날짜>_<순번>_슬러그.py, 리비전=<날짜>_<순번>)에서
# 읽는다 — 리허설 환경에는 파이썬이 없어도 된다.
HEAD_REV=$(ls migrations/versions/*.py | sed 's#.*/##' | awk -F_ '{print $1"_"$2}' | sort | tail -1)
echo "   복원본: $RESTORED_REV / 저장소 헤드: $HEAD_REV"
if [ "$RESTORED_REV" != "$HEAD_REV" ]; then
  # 옛 스키마 덤프 자체는 정상일 수 있다(복구 시 migrate로 헤드까지 올림) —
  # 다만 마지막 백업이 최신 배포를 반영하지 못했다는 뜻이므로 실패로 본다.
  FAILURES+=("alembic 리비전 불일치 (복원본 $RESTORED_REV ≠ 헤드 $HEAD_REV)")
fi

echo "== 4) 운영과 행 수 대조 (백업 시점 이후의 증가만큼 차이 나는 것이 정상)"
for table in users projects check_runs artifacts; do
  RESTORED=$(docker exec "$CONTAINER" psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "select count(*) from $table;" 2>/dev/null || echo "ERR")
  LIVE=$(docker compose --env-file .env.production -f infra/compose.yaml exec -T postgres \
    psql -tA -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "select count(*) from $table;" 2>/dev/null || echo "?")
  echo "   $table: 복원 $RESTORED / 운영 $LIVE"
  if [ "$RESTORED" = "ERR" ]; then
    FAILURES+=("테이블 조회 실패: $table")
  fi
done

echo "== 5) 아티팩트 아카이브 무결성 (최신 주간 백업)"
ARCHIVE=$(ls -t "$BACKUP_DIR"/aim-artifacts-*.tar.gz 2>/dev/null | head -1)
if [ -n "$ARCHIVE" ]; then
  if gzip -t "$ARCHIVE" && FILE_COUNT=$(tar -tzf "$ARCHIVE" | grep -c -v '/$'); then
    echo "   $(basename "$ARCHIVE") ($(du -h "$ARCHIVE" | cut -f1)) — 파일 $FILE_COUNT개, 아카이브 정상"
  else
    FAILURES+=("아티팩트 아카이브 손상: $(basename "$ARCHIVE")")
  fi
else
  FAILURES+=("아티팩트 아카이브가 없음: $BACKUP_DIR/aim-artifacts-*.tar.gz")
fi

ELAPSED=$(( $(date +%s) - STARTED ))
echo
if [ ${#FAILURES[@]} -eq 0 ]; then
  echo "리허설 합격 (${ELAPSED}초) — 이 백업으로 복구할 수 있다."
  echo "restore-runbook.md 리허설 기록 표에 오늘 결과를 추가할 것."
else
  echo "리허설 불합격 (${ELAPSED}초):" >&2
  printf ' - %s\n' "${FAILURES[@]}" >&2
  exit 1
fi
