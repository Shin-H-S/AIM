# AIM

AIM은 등록된 웹 서비스의 가용성, 품질, 핵심 사용자 흐름을 검사하고 이전 실행과 비교하여 배포 위험을 판단하도록 돕는 AI 기반 품질 평가·모니터링 플랫폼입니다.

현재는 MVP 기반 구조를 준비하는 단계이며 실행 가능한 애플리케이션은 아직 포함되어 있지 않습니다.

## MVP 방향

- HTTP 가용성, 응답 시간, 리다이렉트 및 SSL 검사
- Lighthouse 기반 성능·접근성·SEO·Best Practices 평가
- Playwright 기반 핵심 사용자 시나리오 검사
- 실행 결과와 아티팩트 저장
- 이전 실행 및 기준 실행과의 회귀 비교
- 결정론적 점수와 배포 위험 산정
- 수집한 근거에 기반한 AI 진단
- 임계값 위반 및 복구 이메일 알림

상세 제품 범위와 개발 규칙은 [AGENTS.md](AGENTS.md)를 기준으로 합니다.

## 저장소 구조

```text
apps/
  web/            Next.js 사용자 인터페이스
  api/            FastAPI HTTP API
  worker/         스캔 및 분석 백그라운드 작업
packages/
  contracts/      서비스 경계에서 공유하는 계약
infra/            로컬 개발 및 배포 인프라
migrations/       데이터베이스 마이그레이션
docs/
  architecture/   시스템 구조와 주요 흐름
  api/            API 계약
  decisions/      아키텍처 결정 기록
scripts/          반복 가능한 개발 자동화
tests/            저장소 수준 통합·E2E 테스트
```

각 영역은 실제 구현이 시작될 때 필요한 설정과 소스 코드를 추가합니다. 현재 README 파일들은 디렉터리의 책임과 경계를 기록하기 위한 것입니다.

## 개발 순서

1. FastAPI 애플리케이션 골격과 상태 확인 엔드포인트
2. PostgreSQL 연결 및 Alembic 설정
3. Next.js 애플리케이션 골격
4. 프로젝트 CRUD와 기본 인증
5. SSRF 방어를 포함한 URL 검증과 도메인 소유권 확인

실행 및 테스트 명령은 각 애플리케이션의 도구가 확정된 뒤 이 문서에 추가합니다.
