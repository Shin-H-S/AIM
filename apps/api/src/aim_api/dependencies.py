from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.models.user import User
from aim_api.security import decode_access_token
from aim_api.services import users as user_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_db)],
) -> User:
    user_id = decode_access_token(token)
    if user_id is None:
        raise authentication_error()

    try:
        user = user_service.get_user_by_id(session, user_id)
    except user_service.UserNotFoundError as exc:
        raise authentication_error() from exc

    if not user.is_active:
        raise authentication_error()

    return user
