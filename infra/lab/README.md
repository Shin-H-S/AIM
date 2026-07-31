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

## ssl 장애 실험 (`ssl-lab`)

ssl 유형은 위의 HTML 교체로는 못 만든다 — 인증서는 Caddy가 쥐고 있기 때문이다.
그래서 **같은 정적 페이지를 서빙하는 두 번째 호스트네임**(`ssl-lab.qaaimsync.com`)을
두고, 그쪽의 TLS 설정 파일을 교체하는 방식으로 상태를 전환한다.

lab 본체와 호스트를 분리하는 이유: ssl을 망가뜨리면 도메인 인증(meta 태그 fetch)도
같이 막힌다. 인증은 **정상 상태에서** 마쳐 두고, 그 다음 인증서만 망가뜨려야
"인증된 프로젝트가 ssl만 깨진" 상태가 성립한다.

### 최초 설정 (1회)

1. **DNS**: `ssl-lab.qaaimsync.com` A 레코드 → 운영 VM IP (Cloudflare, 프록시 OFF —
   프록시가 켜져 있으면 Cloudflare의 인증서가 보여서 실험이 성립하지 않는다).
2. **환경변수**: VM `.env.production` 에 `AIM_SSL_LAB_HOSTNAME=ssl-lab.qaaimsync.com`
   추가 후 caddy 재생성(`docker compose ... up -d caddy`).
3. **AIM 프로젝트 등록·인증**: 정상 상태(공인 인증서)에서 `https://ssl-lab.qaaimsync.com/`
   프로젝트를 만들고 lab과 같은 방식으로 인증한다. 시나리오는 등록하지 않아도 된다 —
   ssl 검사는 URL만 있으면 돈다.

### 상태 전환 (VM에서)

```bash
cd ~/AIM
cp infra/caddy/variants/ssl-lab-tls-broken.caddy infra/caddy/ssl-lab-tls.caddy   # 장애: 내부 CA 인증서
docker exec -w /etc/caddy aim-caddy-1 caddy reload
git checkout -- infra/caddy/ssl-lab-tls.caddy                                    # 정상 복구
docker exec -w /etc/caddy aim-caddy-1 caddy reload
```

전환 후 수동 검사를 돌리면 ssl 검사가 `SSL certificate verification failed.` 로
실패하고, 인시던트가 열리면 에이전트가 붙는다. **기대 판정: SSL_INVALID**
(근거에 ssl 검사 실패 사유가 인용되어야 한다). 끝나면 반드시 정상으로 되돌린다.

### 이 실험이 덮는 범위

내부 CA 인증서 = "신뢰 체인 검증 실패" 경로다. ssl 검사의 또 다른 분기인
"신뢰되는 체인인데 만료됨"은 공인 CA가 서명한 만료 인증서가 필요해 실험대에서
재현할 수 없다 — 다만 코드상 두 분기는 같은 `is_valid=False` + 사유 문자열로
수렴하므로, 에이전트 관점의 검증 범위로는 이 실험으로 충분하다.
