"""운영자에게 보내는 내부 장애 알림.

사용자 대상 인시던트 알림(services/alert_delivery.py)과는 대상도 목적도 다르다.
이쪽은 **AIM 자신이 고장났을 때** 운영자에게 알린다. 지금까지 미처리 예외는
stdout으로 흘러가고 끝이라 아무도 몰랐다.

전송 실패가 원래 요청·태스크를 죽이면 안 된다 — 알림은 보조 수단이므로
어떤 예외도 삼키고 로그만 남긴다.

채널은 VM 헬스 경보(scripts/monitor-vm-health.sh)가 이미 쓰는 Discord/Slack
incoming webhook을 그대로 쓴다. 새 인프라를 들이지 않는다.
"""

import logging
from typing import Protocol

import httpx

from aim_api.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Discord는 2000자를 넘기면 거절한다. 알림 본문은 짧을수록 읽힌다.
MAX_OPS_ALERT_LENGTH = 1_500


class OpsAlertSender(Protocol):
    def send(self, *, url: str, payload: dict[str, str]) -> None:
        """운영 알림 payload를 incoming webhook으로 보낸다."""


class HttpxOpsAlertSender:
    def __init__(self, timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds

    def send(self, *, url: str, payload: dict[str, str]) -> None:
        response = httpx.post(
            url,
            json=payload,
            timeout=self._timeout_seconds,
            follow_redirects=False,
        )
        response.raise_for_status()


def build_ops_alert_content(
    *,
    title: str,
    detail: str,
    request_id: str | None,
) -> str:
    lines = [f"🚨 **{title}**"]
    if request_id:
        lines.append(f"request_id: `{request_id}`")
    lines.append(f"```\n{detail}\n```")

    content = "\n".join(lines)
    if len(content) > MAX_OPS_ALERT_LENGTH:
        content = content[: MAX_OPS_ALERT_LENGTH - 4] + "\n```"
    return content


def notify_ops(
    *,
    title: str,
    detail: str,
    request_id: str | None = None,
    settings: Settings | None = None,
    sender: OpsAlertSender | None = None,
) -> bool:
    """운영 알림을 보낸다. 보냈으면 True, 미설정이거나 실패하면 False.

    절대 예외를 밖으로 내보내지 않는다 — 알림이 실패했다고 원래 장애 처리
    흐름까지 깨지면 상황이 더 나빠진다.
    """
    runtime_settings = settings or get_settings()
    webhook_url = runtime_settings.ops_webhook_url
    if not webhook_url:
        return False

    resolved_sender = sender or HttpxOpsAlertSender(
        timeout_seconds=runtime_settings.alert_webhook_timeout_seconds
    )
    content = build_ops_alert_content(title=title, detail=detail, request_id=request_id)

    try:
        resolved_sender.send(url=webhook_url, payload={"content": content})
    except Exception:
        logger.warning("Failed to deliver an ops alert.", exc_info=True)
        return False

    return True
