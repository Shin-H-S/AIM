#!/usr/bin/env bash
# VM 시크릿 번들의 오프박스(로컬 PC) 암호화 백업.
#
# 대상: 정규 백업(DB 덤프·아티팩트)에 **들어 있지 않은** 수동 재구성 파일들 —
# .env.production, deploy-token, scenario-secrets, ops-webhook, backup-par-url.
# VM 전체 유실 시 이 다섯이 없으면 복구 절차 B가 "값을 다시 찾아 다니는 일"이
# 된다. 이 스크립트는 그 구간을 "복호화 한 줄"로 줄인다.
#
# 사용법 (로컬 PC에서, VM이 아니라):
#   scripts/backup-secrets-offbox.sh            # 암호를 물어본다
#   AIM_SECRETS_PASSPHRASE=... scripts/backup-secrets-offbox.sh   # 비대화식
#
# 복호화(검증 겸):
#   openssl enc -d -aes-256-cbc -pbkdf2 -in <파일>.tar.gz.enc | tar -tzf -
#
# 평문 tar는 디스크에 쓰지 않는다 — VM의 tar 스트림을 파이프로 받아 즉시
# 암호화한다. 암호를 잃으면 이 백업도 잃는 것이다: 암호는 비밀번호 관리자에.
set -euo pipefail

SSH_HOST="${AIM_SSH_HOST:-aim-oci}"
OUT_DIR="${AIM_SECRETS_BACKUP_DIR:-$HOME/backups/aim-secrets}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$OUT_DIR/aim-secrets-$STAMP.tar.gz.enc"

if [ -z "${AIM_SECRETS_PASSPHRASE:-}" ]; then
  read -r -s -p "백업 암호(복호화에 필요 — 비밀번호 관리자에 보관): " AIM_SECRETS_PASSPHRASE
  echo
  [ -n "$AIM_SECRETS_PASSPHRASE" ] || { echo "빈 암호로는 백업하지 않는다." >&2; exit 1; }
fi
export AIM_SECRETS_PASSPHRASE

mkdir -p "$OUT_DIR"

# 파일 하나라도 빠지면 tar가 실패한다(의도) — "다 있는 줄 알았던 백업"이 최악이다.
ssh "$SSH_HOST" 'tar -czf - -C "$HOME" \
  AIM/.env.production \
  .config/aim/deploy-token \
  .config/aim/scenario-secrets/secrets.env \
  .config/aim/ops-webhook \
  .config/aim/backup-par-url' \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:AIM_SECRETS_PASSPHRASE -out "$OUT"

[ -s "$OUT" ] || { echo "백업 파일이 비었습니다: $OUT" >&2; rm -f "$OUT"; exit 1; }

# 라운드트립 검증 — 방금 만든 파일을 실제로 복호화해 목차를 읽는다.
# 복호화해 본 적 없는 암호화 백업은 백업이 아니다(restore-rehearsal과 같은 사상).
ENTRIES=$(openssl enc -d -aes-256-cbc -pbkdf2 -pass env:AIM_SECRETS_PASSPHRASE -in "$OUT" \
  | tar -tzf - | grep -c -v '/$')
if [ "$ENTRIES" -lt 5 ]; then
  echo "복호화 검증 실패: 항목 ${ENTRIES}개 (기대 5개 이상)" >&2
  exit 1
fi

echo "secrets backup ok: $OUT ($(du -h "$OUT" | cut -f1), 파일 ${ENTRIES}개, 복호화 검증 통과)"
echo "암호를 잃으면 이 백업도 잃는다 — 비밀번호 관리자에 보관할 것."
