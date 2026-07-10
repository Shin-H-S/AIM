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

SERVICES=("$@")
if [ "${#SERVICES[@]}" -eq 0 ]; then
  SERVICES=(api worker beat web)
fi

compose() {
  docker compose --env-file .env.production -f infra/compose.yaml "$@"
}

git pull --ff-only
compose build "${SERVICES[@]}"
compose run --rm migrate
compose up -d "${SERVICES[@]}"
compose ps

TOKEN_FILE="${AIM_DEPLOY_TOKEN_FILE:-$HOME/.config/aim/deploy-token}"
AIM_PROJECT_ID="${AIM_DEPLOY_PROJECT_ID:-51de8dd3-0b84-4cda-8b71-3795e7e92a53}"
HOOK_URL="${AIM_DEPLOY_HOOK_URL:-https://api.qaaimsync.com/hooks/projects/${AIM_PROJECT_ID}/check-runs}"

if [ ! -f "$TOKEN_FILE" ]; then
  echo "deploy hook: 토큰 파일(${TOKEN_FILE})이 없어 검사 트리거를 건너뜁니다."
  exit 0
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
