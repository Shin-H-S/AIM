from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aim_api.models.user import User
from aim_api.schemas.auth import UserCreate
from aim_api.security import hash_password, verify_password


class UserAlreadyExistsError(Exception):
    """Raised when an email is already registered."""


class UserNotFoundError(Exception):
    """Raised when a user does not exist."""


def get_user_by_id(session: Session, user_id: UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise UserNotFoundError

    return user


def get_user_by_email(session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email.strip().lower())
    return session.scalar(statement)


def create_user(session: Session, payload: UserCreate) -> User:
    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
    )
    session.add(user)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise UserAlreadyExistsError from exc

    session.refresh(user)
    return user


def authenticate_user(session: Session, *, email: str, password: str) -> User | None:
    user = get_user_by_email(session, email)
    if user is None or not user.is_active:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user
