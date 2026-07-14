#!/usr/bin/env bash
# AIM 운영 VM 자체 경보 — 디스크·메모리(스왑) 잠행 성장을 Discord로 알린다.
# 빌드 캐시가 3주간 68GB까지 조용히 자랐던 사고의 재발 방지 장치.
#
# 설정 (VM에서 1회):
#   1) Discord incoming webhook URL을 한 줄로 저장: ~/.config/aim/ops-webhook (chmod 600)
#   2) 크론 등록 (15분 간격):
#      */15 * * * * $HOME/AIM/scripts/monitor-vm-health.sh >> $HOME/backups/aim/health.log 2>&1
#   발송 경로 테스트: scripts/monitor-vm-health.sh test
#
# 동작: 임계값을 넘는 순간 1회 경보, 정상으로 돌아오면 1회 복귀 알림(에지 트리거,
# 상태 파일 기반)이라 초과 상태가 지속돼도 반복 발송하지 않는다.
set -euo pipefail

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

WEBHOOK_FILE="${AIM_OPS_WEBHOOK_FILE:-$HOME/.config/aim/ops-webhook}"
DISK_ALERT_PCT="${AIM_DISK_ALERT_PCT:-80}"
SWAP_ALERT_PCT="${AIM_SWAP_ALERT_PCT:-50}"
STATE_DIR="${AIM_HEALTH_STATE_DIR:-$HOME/.local/state/aim-health}"

mkdir -p "$STATE_DIR"

if [ ! -f "$WEBHOOK_FILE" ]; then
  echo "webhook 파일(${WEBHOOK_FILE})이 없어 경보를 보낼 수 없습니다." >&2
  exit 1
fi

send_message() {
  curl -fsS -X POST -H "Content-Type: application/json" \
    -d "{\"content\": \"$1\"}" \
    "$(cat "$WEBHOOK_FILE")" >/dev/null
}

# 넘는 순간 경보 1회, 돌아오는 순간 복귀 알림 1회.
check_condition() {
  local name="$1" current="$2" threshold="$3" alert_text="$4" recovery_text="$5"
  local state_file="$STATE_DIR/$name.alert"

  if [ "$current" -ge "$threshold" ]; then
    if [ ! -f "$state_file" ]; then
      send_message "$alert_text" && touch "$state_file"
      echo "alert sent: $name (${current}%)"
    fi
  elif [ -f "$state_file" ]; then
    send_message "$recovery_text" && rm -f "$state_file"
    echo "recovery sent: $name (${current}%)"
  fi
}

if [ "${1:-}" = "test" ]; then
  send_message "🧪 AIM VM 경보 테스트 — 발송 경로 정상입니다."
  echo "test message sent"
  exit 0
fi

DISK_PCT="$(df --output=pcent / | tail -1 | tr -dc '0-9')"
SWAP_TOTAL="$(free -m | awk '/^Swap:/ {print $2}')"
SWAP_USED="$(free -m | awk '/^Swap:/ {print $3}')"
SWAP_PCT=0
if [ "$SWAP_TOTAL" -gt 0 ]; then
  SWAP_PCT=$((SWAP_USED * 100 / SWAP_TOTAL))
fi

check_condition disk "$DISK_PCT" "$DISK_ALERT_PCT" \
  "⚠️ AIM VM 디스크 ${DISK_PCT}% 사용 (임계 ${DISK_ALERT_PCT}%) — 빌드 캐시·백업·로그를 확인하세요." \
  "✅ AIM VM 디스크 ${DISK_PCT}% — 정상 범위로 복귀했습니다."

check_condition swap "$SWAP_PCT" "$SWAP_ALERT_PCT" \
  "⚠️ AIM VM 스왑 ${SWAP_PCT}% 사용 (${SWAP_USED}MB, 임계 ${SWAP_ALERT_PCT}%) — 메모리 압박, 컨테이너 상태를 확인하세요." \
  "✅ AIM VM 스왑 ${SWAP_PCT}% — 정상 범위로 복귀했습니다."

echo "health ok: disk=${DISK_PCT}% swap=${SWAP_PCT}%"
