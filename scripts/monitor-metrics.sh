#!/usr/bin/env bash
# AIM 서비스 메트릭 경보 — /metrics를 아무도 안 읽으면 노출한 의미가 없다.
#
# monitor-vm-health.sh가 머신(디스크·스왑)을 보는 것과 짝으로, 이 스크립트는
# 서비스(큐 정체·조치 필요 인시던트)를 본다. 같은 에지 트리거 방식: 임계를
# 넘는 순간 1회 경보, 돌아오는 순간 1회 복귀 알림.
#
# 설정 (VM에서 1회):
#   크론 등록 (15분 간격, monitor-vm-health.sh와 같은 주기):
#     */15 * * * * $HOME/AIM/scripts/monitor-metrics.sh >> $HOME/backups/aim/health.log 2>&1
#   webhook은 monitor-vm-health.sh와 같은 ~/.config/aim/ops-webhook을 쓴다.
#   METRICS_TOKEN은 ~/AIM/.env.production에서 읽는다.
set -euo pipefail

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

REPO_DIR="${AIM_REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WEBHOOK_FILE="${AIM_OPS_WEBHOOK_FILE:-$HOME/.config/aim/ops-webhook}"
STATE_DIR="${AIM_HEALTH_STATE_DIR:-$HOME/.local/state/aim-health}"
METRICS_URL="${AIM_METRICS_URL:-https://api.qaaimsync.com/metrics}"

# 검사가 큐에 이만큼 쌓이면 워커가 소비하지 못하고 있다는 신호다. 큐 분리
# 사고(라우팅이 API에 없어 태스크가 조용히 쌓임)의 재발을 잡는 것이 목적.
QUEUED_ALERT="${AIM_QUEUED_ALERT:-3}"

mkdir -p "$STATE_DIR"

if [ ! -f "$WEBHOOK_FILE" ]; then
  echo "webhook 파일(${WEBHOOK_FILE})이 없어 경보를 보낼 수 없습니다." >&2
  exit 1
fi

source <(grep -E '^METRICS_TOKEN=' "$REPO_DIR/.env.production")
if [ -z "${METRICS_TOKEN:-}" ]; then
  echo "METRICS_TOKEN이 비어 있어 /metrics를 읽을 수 없습니다." >&2
  exit 1
fi

send_message() {
  curl -fsS -X POST -H "Content-Type: application/json" \
    -d "{\"content\": \"$1\"}" \
    "$(cat "$WEBHOOK_FILE")" >/dev/null
}

check_condition() {
  local name="$1" current="$2" threshold="$3" alert_text="$4" recovery_text="$5"
  local state_file="$STATE_DIR/$name.alert"

  if [ "$current" -ge "$threshold" ]; then
    if [ ! -f "$state_file" ]; then
      send_message "$alert_text" && touch "$state_file"
      echo "alert sent: $name ($current)"
    fi
  elif [ -f "$state_file" ]; then
    send_message "$recovery_text" && rm -f "$state_file"
    echo "recovery sent: $name ($current)"
  fi
}

# 스크레이프 실패 자체도 경보 대상이다 — 엔드포인트가 죽었는데 "임계 초과
# 없음"으로 조용하면, 이 감시가 지키는 모든 것이 같이 눈을 감는다.
if ! METRICS="$(curl -fsS --max-time 20 -H "Authorization: Bearer $METRICS_TOKEN" "$METRICS_URL")"; then
  check_condition "metrics-scrape" 1 1 \
    "🔴 AIM /metrics 스크레이프 실패 — API 다운 또는 토큰 불일치. 큐·인시던트 감시가 눈을 감았다." \
    "(unreachable)"
  exit 0
fi
check_condition "metrics-scrape" 0 1 "(unreachable)" "🟢 AIM /metrics 스크레이프 복구 — 서비스 감시 재개."

metric_value() {
  # 예: metric_value 'aim_check_runs_total{status="QUEUED"}' — 없으면 0.
  local line
  line=$(grep -F "$1" <<<"$METRICS" | head -1 || true)
  [ -n "$line" ] && printf '%.0f' "${line##* }" || echo 0
}

QUEUED=$(metric_value 'aim_check_runs_total{status="QUEUED"}')
check_condition "queued-runs" "$QUEUED" "$QUEUED_ALERT" \
  "🟠 AIM 검사 ${QUEUED}건이 큐에 정체 — 워커가 소비하지 못하고 있다. \`docker compose ps\`와 worker 로그 확인." \
  "🟢 AIM 검사 큐 정상화 (현재 ${QUEUED}건)."

CURRENT_INCIDENTS=$(metric_value 'aim_incidents_open{freshness="current"}')
check_condition "current-incidents" "$CURRENT_INCIDENTS" 1 \
  "🔴 조치 필요 인시던트 ${CURRENT_INCIDENTS}건 (최근 검사에서 확인됨) — 대시보드 확인." \
  "🟢 조치 필요 인시던트 0건 — 전부 해소."

echo "metrics ok: queued=$QUEUED current_incidents=$CURRENT_INCIDENTS"
