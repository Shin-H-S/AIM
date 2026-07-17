import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.config import Settings, get_settings
from aim_api.models.email_verification_token import EmailVerificationToken
from aim_api.models.user import User
from aim_api.services.alert_delivery import (
    DEFAULT_FROM_EMAIL,
    EmailSender,
    build_smtp_email_sender,
)
from aim_api.services.users import get_user_by_email

logger = logging.getLogger(__name__)

VERIFICATION_EMAIL_SUBJECT = "[AIM] 이메일 인증 안내"


class InvalidVerificationTokenError(Exception):
    """Raised when a verification token is unknown, expired, or already used."""


def hash_verification_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def start_email_verification(
    session: Session,
    *,
    user: User,
    settings: Settings | None = None,
    email_sender: EmailSender | None = None,
) -> None:
    """가입 직후 인증 토큰을 발급하고 안내 메일을 보낸다.

    SMTP가 없는 환경(로컬 개발·테스트)은 인증 메일을 보낼 방법이 없으므로 즉시
    인증 완료로 처리한다. 운영에서 SMTP 설정이 빠지면 인증이 조용히 꺼지는
    트레이드오프라 경고 로그를 남긴다. 메일 발송 실패는 로그만 남긴다 —
    사용자는 재발송으로 복구할 수 있다.
    """
    runtime_settings = settings or get_settings()
    resolved_sender = email_sender or build_smtp_email_sender(runtime_settings)
    if resolved_sender is None:
        user.email_verified_at = datetime.now(UTC)
        session.commit()
        logger.warning(
            "SMTP is not configured; new account marked verified without an email.",
            extra={"user_id": str(user.id)},
        )
        return

    _issue_and_send(session, user=user, settings=runtime_settings, sender=resolved_sender)


def request_email_verification(
    session: Session,
    *,
    email: str,
    settings: Settings | None = None,
    email_sender: EmailSender | None = None,
) -> None:
    """인증 메일을 재발송한다.

    계정 존재·인증 여부가 응답으로 드러나지 않도록 어떤 경우에도 조용히 반환한다.
    """
    runtime_settings = settings or get_settings()
    user = get_user_by_email(session, email)
    if user is None or not user.is_active or user.email_verified_at is not None:
        return

    resolved_sender = email_sender or build_smtp_email_sender(runtime_settings)
    if resolved_sender is None:
        logger.warning(
            "Verification email skipped because SMTP is not configured.",
            extra={"user_id": str(user.id)},
        )
        return

    _issue_and_send(session, user=user, settings=runtime_settings, sender=resolved_sender)


def _issue_and_send(
    session: Session,
    *,
    user: User,
    settings: Settings,
    sender: EmailSender,
) -> None:
    plaintext = secrets.token_urlsafe(32)
    token = EmailVerificationToken(
        user_id=user.id,
        token_hash=hash_verification_token(plaintext),
        expires_at=datetime.now(UTC)
        + timedelta(minutes=settings.email_verification_token_expire_minutes),
    )
    session.add(token)
    session.commit()

    message = build_verification_email(
        recipient=user.email,
        plaintext_token=plaintext,
        from_email=settings.smtp_from_email or DEFAULT_FROM_EMAIL,
        web_base_url=settings.web_base_url,
        expire_minutes=settings.email_verification_token_expire_minutes,
    )

    try:
        sender.send_message(message)
    except Exception:
        logger.exception(
            "Failed to send verification email.",
            extra={"user_id": str(user.id)},
        )


def build_verification_email(
    *,
    recipient: str,
    plaintext_token: str,
    from_email: str,
    web_base_url: str | None,
    expire_minutes: int,
) -> EmailMessage:
    expire_hours = max(expire_minutes // 60, 1)
    lines = ["AIM 가입을 환영합니다. 이메일 주소 인증이 필요합니다.", ""]

    if web_base_url:
        base = web_base_url.rstrip("/")
        lines.append(f"아래 링크를 열면 인증이 완료됩니다 (유효 시간 {expire_hours}시간):")
        lines.append(f"{base}/verify-email?token={plaintext_token}")
    else:
        lines.append(f"인증 화면에 아래 코드를 입력하세요 (유효 시간 {expire_hours}시간):")
        lines.append(plaintext_token)

    lines.extend(
        [
            "",
            "본인이 가입하지 않았다면 이 메일은 무시해도 됩니다.",
        ]
    )

    message = EmailMessage()
    message["From"] = from_email
    message["To"] = recipient
    message["Subject"] = VERIFICATION_EMAIL_SUBJECT
    message.set_content("\n".join(lines))
    return message


def confirm_email_verification(session: Session, *, token: str) -> User:
    """토큰을 검증하고 이메일을 인증 완료로 표시한다. 토큰은 1회만 사용할 수 있다."""
    record = session.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hash_verification_token(token)
        )
    )
    now = datetime.now(UTC)

    if record is None or record.used_at is not None or as_utc(record.expires_at) <= now:
        raise InvalidVerificationTokenError

    user = session.get(User, record.user_id)
    if user is None or not user.is_active:
        raise InvalidVerificationTokenError

    if user.email_verified_at is None:
        user.email_verified_at = now
    record.used_at = now

    # 같은 사용자의 다른 미사용 토큰도 함께 무효화한다.
    for sibling in session.scalars(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
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
