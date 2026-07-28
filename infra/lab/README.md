# AIM Lab — 조사 에이전트 도그푸딩 실험대

조사 에이전트가 실제 장애를 제대로 판정하는지 검증하려면 장애를 일으켜야 하는데,
운영 서비스에는 실사용자가 있다. 이 실험대는 **고의로 망가뜨려도 아무도 다치지 않는
대상**을 따로 두기 위한 것이다.

- Caddy의 독립 사이트 블록(`{$AIM_LAB_HOSTNAME}`)이 이 디렉토리를 정적 서빙한다.
  웹·API 블록과 분리돼 있어 이 페이지가 깨져도 라우팅에 영향이 없다.
- 상태 전환은 파일 교체 한 줄이면 되고 배포·재시작이 필요 없다(정적 파일).

## 최초 설정 (1회)

1. **DNS**: `lab.qaaimsync.com` A 레코드 → 운영 VM IP (Cloudflare, 프록시 OFF).
2. **환경변수**: VM `.env.production` 에 `AIM_LAB_HOSTNAME=lab.qaaimsync.com` 추가 후
   `docker compose ... up -d caddy` (환경변수가 바뀌었으므로 컨테이너가 재생성된다).
   Caddyfile 내용만 바뀐 경우에는 `scripts/deploy.sh` 가 reload 해 준다 —
   설정을 디렉토리로 마운트하므로 `git pull` 이 파일을 교체해도 컨테이너에 그대로 보인다.
3. **AIM 프로젝트 등록**: 웹에서 `https://lab.qaaimsync.com/` 로 프로젝트를 만들고
   발급된 인증 토큰을 `index.html`·`variants/*.html` 의 `aim-verification` meta 에 넣는다
   (변형 페이지도 같은 토큰이어야 상태를 바꿔도 인증이 유지된다). 배포 후 인증.
4. **시나리오 등록**: 홈에서 로그인 폼을 확인하는 흐름.
   `navigate /` → `assert_element_exists #email` → `assert_element_exists #password`
   → `assert_element_exists button[type="submit"]`.

## 상태 전환 (VM에서)

```bash
cd ~/AIM/infra/lab
cp variants/ui-broken.html index.html        # UI 회귀: 폼 렌더 실패, 대체 경로 없음
cp variants/relocated-index.html index.html  # 시나리오 스테일: 폼이 /login.html 로 이사
git checkout -- index.html                   # 정상 복구
```

전환 후 AIM에서 해당 프로젝트를 수동 검사하면 시나리오가 실패하고, 인시던트가 열리면
조사 에이전트가 자동으로 붙는다. 검증이 끝나면 **반드시 정상으로 되돌린다.**

## 유형 구분의 핵심

두 변형은 겉으로 똑같이 "시나리오 스텝 실패"로 나타나지만 원인이 다르다 — 이 구분이
에이전트의 제품 가치다.

| | UI 회귀 (`ui-broken`) | 시나리오 스테일 (`relocated-index`) |
|---|---|---|
| 페이지 렌더 | 실패 흔적(에러 배너·콘솔 에러) | 정상 |
| 이동 흔적 | 없음 | 있음 (로그인 CTA → `/login.html`) |
| 올바른 조치 | 서비스 수정 | 시나리오 갱신 |
