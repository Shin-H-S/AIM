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

# git pull은 이 스크립트 자신도 바꾼다. 그런데 pull 이후의 나머지 줄은 이미
# 실행 중인 옛 내용이라, 스크립트를 고친 배포는 **그 변경이 적용되지 않은 채**
# 돌아간다. 2026-07-28 배포에서 실제로 이것 때문에 worker-agent가 빠진 채
# 배포됐다(서비스 목록이 pull 이전에 평가됨).
#
# 그래서 pull을 가장 먼저 하고 즉시 새 스크립트로 자신을 교체한다. 인자는 그대로
# 넘기고, 환경변수로 재진입을 표시해 무한 루프를 막는다. exec을 pull 바로 뒤에
# 두는 이유는 bash가 스크립트를 청크 단위로 읽기 때문이다 — 파일이 바뀐 뒤
# 더 읽을 일이 없어야 실행이 뒤틀리지 않는다.
if [ "${AIM_DEPLOY_REEXECED:-}" != "1" ]; then
  git pull --ff-only
  export AIM_DEPLOY_REEXECED=1
  exec "$0" "$@"
fi

# 이 저장소에서 빌드해 배포하는 애플리케이션 서비스.
DEFAULT_SERVICES=(api worker worker-agent beat web)
# 이미지를 그대로 쓰는 서비스 — 배포 때 재빌드하지 않는다.
INFRA_SERVICES=(postgres redis caddy)

SERVICES=("$@")
DEPLOY_EVERYTHING=0
if [ "${#SERVICES[@]}" -eq 0 ]; then
  SERVICES=("${DEFAULT_SERVICES[@]}")
  DEPLOY_EVERYTHING=1
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

compose build "${SERVICES[@]}"
compose run --rm migrate

# 전체 배포에서는 인프라 서비스까지 compose 정의에 수렴시킨다. 빌드는 하지 않지만
# `up -d`는 정의가 바뀐 컨테이너만 재생성하고 나머지는 건드리지 않는다.
#
# 이게 없으면 compose.yaml에서 인프라 서비스의 정의를 바꿔도 배포에 반영되지
# 않는다. Caddyfile을 디렉토리 마운트로 바꿨을 때 실제로 그랬다 — 배포는
# 성공했는데 caddy는 옛 마운트를 그대로 들고 있었고, 그 경로는 이미 사라진
# 뒤라 컨테이너가 재시작되면 뜨지 못하는 상태였다(2026-07-28).
#
# 서비스를 명시해 부른 경우(`deploy.sh web`)는 그 서비스만 건드린다.
if [ "$DEPLOY_EVERYTHING" -eq 1 ]; then
  compose up -d "${SERVICES[@]}" "${INFRA_SERVICES[@]}"
else
  compose up -d "${SERVICES[@]}"
fi

# Caddy는 설정 디렉토리를 마운트하므로 pull한 Caddyfile이 컨테이너에 그대로 보인다.
# reload는 무중단이고 인증서를 다시 받지도 않으므로 매번 해도 안전하다.
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
