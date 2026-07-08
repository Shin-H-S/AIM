import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from aim_api.models.project_api_token import ProjectApiToken

TOKEN_PREFIX = "aim_"


class ProjectApiTokenNotFoundError(Exception):
    """Raised when a token does not exist in the requested project."""


@dataclass(frozen=True)
class IssuedProjectApiToken:
    record: ProjectApiToken
    # 발급 시점에만 노출되는 원문. 저장소에는 해시만 남는다.
    plaintext: str


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def issue_token(session: Session, *, project_id: UUID, name: str) -> IssuedProjectApiToken:
    plaintext = TOKEN_PREFIX + secrets.token_urlsafe(32)
    record = ProjectApiToken(
        project_id=project_id,
        token_hash=hash_token(plaintext),
        name=name,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return IssuedProjectApiToken(record=record, plaintext=plaintext)


def authenticate_token(
    session: Session,
    *,
    project_id: UUID,
    plaintext: str,
) -> ProjectApiToken | None:
    record = session.scalar(
        select(ProjectApiToken).where(
            ProjectApiToken.token_hash == hash_token(plaintext),
            ProjectApiToken.project_id == project_id,
            ProjectApiToken.revoked_at.is_(None),
        )
    )
    if record is None:
        return None

    record.last_used_at = datetime.now(UTC)
    session.commit()
    session.refresh(record)
    return record


def list_tokens(session: Session, *, project_id: UUID) -> list[ProjectApiToken]:
    return list(
        session.scalars(
            select(ProjectApiToken)
            .where(ProjectApiToken.project_id == project_id)
            .order_by(ProjectApiToken.created_at.desc())
        )
    )


def revoke_token(session: Session, *, project_id: UUID, token_id: UUID) -> ProjectApiToken:
    record = session.get(ProjectApiToken, token_id)
    if record is None or record.project_id != project_id:
        raise ProjectApiTokenNotFoundError

    if record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        session.commit()
        session.refresh(record)

    return record
