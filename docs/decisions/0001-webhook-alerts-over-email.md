# 0001. 이메일 알림 제거, Slack/Discord webhook 알림 채택

- 상태: 채택 (2026-07-08)
- 결정자: 신현수

## 배경

초기 계획(AGENTS.md)은 "이메일 알림으로 시작하고 Slack은 나중에 추가"였다. 이에 따라 이메일 발송 파이프라인(pending alert 모델, SMTP 발송 worker task, FAILED 재시도 API, 웹 수신자 설정 UI)이 구현됐지만, 실제 발송은 운영 환경 SMTP 자격증명 설정이 필요해 계속 비활성 상태였다.

운영을 준비하며 다음 문제가 확인됐다.

- AIM의 타깃 사용자는 1인 개발자와 소규모 팀이고, 이들의 실시간 장애 인지 채널은 이메일이 아니라 Slack/Discord다. 이메일은 스팸함·지연 확인 등으로 "배포 직후 회귀를 빨리 안다"는 제품 가치와 맞지 않다.
- SMTP 발송은 발신 도메인 평판, 스팸 필터 대응, 자격증명 관리, 발송 실패 재시도 운영 등 1인 운영 규모 대비 부담이 크다.
- incoming webhook은 무료이고, 사용자 설정이 URL 한 줄 등록으로 끝나며, 전송 실패 판정도 HTTP 응답 코드로 단순하다.

## 결정

이메일 알림을 기획에서 제거하고, **프로젝트별로 등록하는 Slack/Discord incoming webhook**을 알림 채널로 채택한다.

- alert trigger 규칙, incident open/recovery 파이프라인, pending alert 저장 구조는 유지하고 **전달(delivery) 계층만 교체**한다.
- 프로젝트 설정에 webhook URL(1개 이상)을 등록하고, 등록된 URL로 alert payload를 전송한다.
- webhook URL도 사용자 입력 URL이므로 기존 SSRF-safe 검증을 동일하게 적용한다.

## 검토한 대안

1. **이메일 유지 + webhook 추가** — 채널 두 개의 설정 UI·전달 로직·재시도를 함께 유지해야 하고, SMTP 운영 부담이 해소되지 않는다. 기각.
2. **이메일 단일 유지(기존 계획)** — SMTP 설정 전까지 알림이 계속 비활성이고, 타깃 사용자의 실사용성이 낮다. 기각.
3. **Slack/Discord webhook 단일 채널** — 채택.

## 결과와 영향

- 운영 체크리스트에서 "SMTP 설정으로 email alert 활성화" 항목이 제거된다. `.env.production`의 `SMTP_*` 항목도 구현 전환 후 제거한다.
- 전환 구현 범위(별도 작업):
  1. 프로젝트별 webhook URL 등록 API·설정 UI (SSRF-safe 검증 포함)
  2. webhook 전달 worker task (실패 시 재시도 — 기존 FAILED 재시도 구조 재사용)
  3. 이메일 전용 경로 제거: SMTP 발송 task, email 수신자 설정 UI, 프로젝트의 email alert 필드 정리 migration
  4. README·배포 가이드 등 구현 상태 문서 갱신
- README 등 "현재 구현 상태" 문서는 코드가 전환되는 시점에 갱신한다. 이 문서는 계획 결정만 기록한다.
