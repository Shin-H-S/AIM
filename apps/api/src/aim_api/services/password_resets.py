import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.config import Settings, get_settings
from aim_api.models.password_reset_token import PasswordResetToken
from aim_api.models.user import User
from aim_api.security import hash_password
from aim_api.services.alert_delivery import (
    DEFAULT_FROM_EMAIL,
    EmailSender,
    build_smtp_email_sender,
)
from aim_api.services.users import get_user_by_email

logger = logging.getLogger(__name__)

RESET_EMAIL_SUBJECT = "[AIM] 비밀번호 재설정 안내"


class InvalidResetTokenError(Exception):
    """Raised when a reset token is unknown, expired, or already used."""


def hash_reset_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def request_password_reset(
    session: Session,
    *,
    email: str,
    settings: Settings | None = None,
    email_sender: EmailSender | None = None,
) -> None:
    """재설정 토큰을 발급하고 안내 메일을 보낸다.

    계정 존재 여부가 응답으로 드러나지 않도록 어떤 경우에도 조용히 반환하고,
    메일 발송 실패도 로그만 남긴다.
    """
    runtime_settings = settings or get_settings()
    user = get_user_by_email(session, email)
    if user is None or not user.is_active:
        return

    plaintext = secrets.token_urlsafe(32)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_reset_token(plaintext),
        expires_at=datetime.now(UTC)
        + timedelta(minutes=runtime_settings.password_reset_token_expire_minutes),
    )
    session.add(token)
    session.commit()

    resolved_sender = email_sender or build_smtp_email_sender(runtime_settings)
    if resolved_sender is None:
        logger.warning(
            "Password reset email skipped because SMTP is not configured.",
            extra={"user_id": str(user.id)},
        )
        return

    message = build_reset_email(
        recipient=user.email,
        plaintext_token=plaintext,
        from_email=runtime_settings.smtp_from_email or DEFAULT_FROM_EMAIL,
        web_base_url=runtime_settings.web_base_url,
        expire_minutes=runtime_settings.password_reset_token_expire_minutes,
    )

    try:
        resolved_sender.send_message(message)
    except Exception:
        logger.exception(
            "Failed to send password reset email.",
            extra={"user_id": str(user.id)},
        )


def build_reset_email(
    *,
    recipient: str,
    plaintext_token: str,
    from_email: str,
    web_base_url: str | None,
    expire_minutes: int,
) -> EmailMessage:
    lines = ["AIM 비밀번호 재설정을 요청하셨습니다.", ""]

    if web_base_url:
        base = web_base_url.rstrip("/")
        lines.append(f"아래 링크에서 새 비밀번호를 설정하세요 (유효 시간 {expire_minutes}분):")
        lines.append(f"{base}/password-reset/confirm?token={plaintext_token}")
    else:
        lines.append(f"재설정 화면에 아래 코드를 입력하세요 (유효 시간 {expire_minutes}분):")
        lines.append(plaintext_token)

    lines.extend(
        [
            "",
            "본인이 요청하지 않았다면 이 메일은 무시해도 됩니다.",
            "비밀번호는 변경되지 않습니다.",
        ]
    )

    message = EmailMessage()
    message["From"] = from_email
    message["To"] = recipient
    message["Subject"] = RESET_EMAIL_SUBJECT
    message.set_content("\n".join(lines))
    return message


def confirm_password_reset(
    session: Session,
    *,
    token: str,
    new_password: str,
) -> User:
    """토큰을 검증하고 비밀번호를 교체한다. 토큰은 1회만 사용할 수 있다."""
    record = session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_reset_token(token))
    )
    now = datetime.now(UTC)

    if record is None or record.used_at is not None or as_utc(record.expires_at) <= now:
        raise InvalidResetTokenError

    user = session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise InvalidResetTokenError

    user.password_hash = hash_password(new_password)
    record.used_at = now

    # 같은 사용자의 다른 미사용 토큰도 함께 무효화한다.
    for sibling in session.scalars(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
    ):
        sibling.used_at = now

    session.commit()
    session.refresh(user)
    return user


def as_utc(value: datetime) -> datetime:
    """SQLite는 tzinfo를 보존하지 않으므로 naive 값을 UTC로 간주한다."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)
