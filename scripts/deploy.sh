#!/usr/bin/env bash
# AIM 운영 VM 배포 스크립트.
# git pull 후 지정한 서비스를 재빌드·기동하고 migration을 적용한 뒤,
# 배포 훅으로 AIM 자신에 대한 검사를 자동 트리거한다(dogfooding).
#
# 사용법 (VM의 저장소 루트 기준):
#   scripts/deploy.sh              # api worker beat web 전체
#   scripts/deploy.sh web          # web만
#
# 배포 훅 토큰은 ~/.config/aim/deploy-token 에서 읽는다.
# 토큰 파일이 없으면 훅 호출만 건너뛰고 배포는 정상 진행된다.
set -euo pipefail

cd "$(dirname "$0")/.."

# 이 저장소에서 빌드해 배포하는 애플리케이션 서비스.
DEFAULT_SERVICES=(api worker worker-agent beat web)
# 이미지를 그대로 쓰는 서비스 — 배포 때 재빌드하지 않는다.
INFRA_SERVICES=(postgres redis caddy)

SERVICES=("$@")
if [ "${#SERVICES[@]}" -eq 0 ]; then
  SERVICES=("${DEFAULT_SERVICES[@]}")
fi

compose() {
  docker compose --env-file .env.production -f infra/compose.yaml "$@"
}

# compose에 새 서비스를 추가하고 이 목록에 넣는 것을 잊으면, 그 서비스는 배포되지
# 않은 채 조용히 빠진다. 큐를 소비하는 워커가 그렇게 빠지면 태스크가 실행되지
# 않고 쌓이기만 하는데, 어디에도 오류가 나지 않아 알아채기 어렵다.
UNKNOWN_SERVICES="$(
  comm -23 \
    <(compose config --services | sort) \
    <(printf '%s\n' "${DEFAULT_SERVICES[@]}" "${INFRA_SERVICES[@]}" | sort)
)"
if [ -n "$UNKNOWN_SERVICES" ]; then
  echo "배포 대상에 없는 compose 서비스가 있습니다: ${UNKNOWN_SERVICES}" >&2
  echo "scripts/deploy.sh의 DEFAULT_SERVICES 또는 INFRA_SERVICES에 추가하세요." >&2
  exit 1
fi

git pull --ff-only
compose build "${SERVICES[@]}"
compose run --rm migrate
compose up -d "${SERVICES[@]}"

# Caddyfile은 읽기 전용 바인드 마운트라 파일만 바뀌고 프로세스는 옛 설정을 그대로
# 들고 있다. reload는 무중단이고 인증서를 다시 받지도 않으므로 매번 해도 안전하다.
# 실패해도 배포 자체는 이미 끝났으므로 중단하지 않되, 조용히 넘어가면 보안 헤더가
# 적용되지 않은 사실을 모르게 되므로 크게 알린다.
if compose ps --status running --services 2>/dev/null | grep -qx caddy; then
  if compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile >/dev/null 2>&1; then
    echo "caddy: 설정 reload 완료."
  else
    echo "caddy: reload 실패 — Caddyfile 변경이 적용되지 않았을 수 있습니다." >&2
  fi
fi

compose ps

# 매 배포마다 buildkit 캐시가 쌓여 디스크를 채우지 않도록 상한을 두고 정리하고,
# 재빌드로 dangling이 된 옛 이미지도 제거한다. 정리 실패가 배포를 실패시키지는 않는다.
BUILD_CACHE_KEEP="${AIM_DEPLOY_BUILD_CACHE_KEEP:-8GB}"
docker builder prune --keep-storage "$BUILD_CACHE_KEEP" --force >/dev/null 2>&1 || true
docker image prune --force >/dev/null 2>&1 || true
echo "docker 정리: 빌드 캐시 상한 ${BUILD_CACHE_KEEP} 유지, dangling 이미지 제거 완료."

TOKEN_FILE="${AIM_DEPLOY_TOKEN_FILE:-$HOME/.config/aim/deploy-token}"
AIM_PROJECT_ID="${AIM_DEPLOY_PROJECT_ID:-51de8dd3-0b84-4cda-8b71-3795e7e92a53}"
HOOK_URL="${AIM_DEPLOY_HOOK_URL:-https://api.qaaimsync.com/hooks/projects/${AIM_PROJECT_ID}/check-runs}"

if [ ! -f "$TOKEN_FILE" ]; then
  echo "deploy hook: 토큰 파일(${TOKEN_FILE})이 없어 검사 트리거를 건너뜁니다."
  exit 0
fi

# 재기동 직후에는 컨테이너 워밍업(Next.js 첫 렌더 등) 때문에 Lighthouse 성능 점수에
# 노이즈가 생긴다. 잠시 대기해 배포 검사가 안정된 상태를 측정하게 한다. 0이면 생략.
WARMUP_SECONDS="${AIM_DEPLOY_WARMUP_SECONDS:-90}"
if [ "$WARMUP_SECONDS" -gt 0 ]; then
  echo "deploy hook: 워밍업 ${WARMUP_SECONDS}초 대기 후 검사를 트리거합니다."
  sleep "$WARMUP_SECONDS"
fi

DEPLOY_REF="$(git rev-parse --short HEAD)"
RESPONSE_FILE="$(mktemp)"
STATUS="$(curl -s -o "$RESPONSE_FILE" -w '%{http_code}' -X POST "$HOOK_URL" \
  -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
  -H "Content-Type: application/json" \
  -d "{\"deploy_ref\": \"${DEPLOY_REF}\"}")" || STATUS="000"

case "$STATUS" in
  201)
    echo "deploy hook: 배포 검사 시작됨 (deploy_ref=${DEPLOY_REF})"
    ;;
  409)
    echo "deploy hook: 이미 진행 중인 검사가 있어 건너뜁니다 (409)."
    ;;
  *)
    echo "deploy hook: 트리거 실패 (HTTP ${STATUS}) — $(cat "$RESPONSE_FILE" 2>/dev/null || true)"
    ;;
esac
rm -f "$RESPONSE_FILE"
