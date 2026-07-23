"""조사 에이전트의 원인 분류 체계 (7유형).

라벨은 코드로 채점 가능해야 하므로 서술이 아니라 닫힌 enum으로 확정한다.
유형 5(UI_REGRESSION)와 6(SCENARIO_STALE)의 구분이 제품 가치의 핵심이다 —
"서비스가 깨졌다"와 "테스트가 낡았다"는 조치가 정반대인데 겉보기 증상
(시나리오 스텝 실패)은 동일하기 때문이다.
"""

from enum import StrEnum


class RootCause(StrEnum):
    """검사 실패·인시던트의 근본 원인 분류."""

    SERVICE_DOWN = "service_down"
    SSL_INVALID = "ssl_invalid"
    SERVER_SLOW = "server_slow"
    FRONTEND_REGRESSION = "frontend_regression"
    UI_REGRESSION = "ui_regression"
    SCENARIO_STALE = "scenario_stale"
    MEASUREMENT_NOISE = "measurement_noise"


# 알림·UI에 쓰는 짧은 한글 라벨.
ROOT_CAUSE_LABELS: dict[RootCause, str] = {
    RootCause.SERVICE_DOWN: "서비스 다운",
    RootCause.SSL_INVALID: "SSL 무효",
    RootCause.SERVER_SLOW: "서버 지연",
    RootCause.FRONTEND_REGRESSION: "프런트 성능 회귀",
    RootCause.UI_REGRESSION: "UI 파손",
    RootCause.SCENARIO_STALE: "시나리오 스테일",
    RootCause.MEASUREMENT_NOISE: "측정 노이즈",
}

ROOT_CAUSE_DESCRIPTIONS: dict[RootCause, str] = {
    RootCause.SERVICE_DOWN: "서비스 다운·네트워크 불달 — 가용성 검사 자체가 실패",
    RootCause.SSL_INVALID: "SSL 인증서 만료·무효",
    RootCause.SERVER_SLOW: "서버 응답 지연 — 임계값 대비 응답시간 초과",
    RootCause.FRONTEND_REGRESSION: "프런트 성능 회귀 — Lighthouse 성능 점수 하락",
    RootCause.UI_REGRESSION: "UI 회귀 — 서비스 변경으로 요소·흐름이 실제로 파손",
    RootCause.SCENARIO_STALE: "시나리오 정의 스테일 — 서비스는 정상이나 테스트 정의가 낡음",
    RootCause.MEASUREMENT_NOISE: "측정 노이즈·일시적 외부 요인 — 재검사 시 재현되지 않음",
}
