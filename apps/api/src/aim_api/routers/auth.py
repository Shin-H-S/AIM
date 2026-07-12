from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.user import User
from aim_api.schemas.auth import (
    AccessToken,
    PasswordResetConfirm,
    PasswordResetRequest,
    UserCreate,
    UserLogin,
    UserRead,
)
from aim_api.security import create_access_token
from aim_api.services import password_resets as password_reset_service
from aim_api.services import users as user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def signup(
    payload: UserCreate,
    session: Annotated[Session, Depends(get_db)],
) -> UserRead:
    if user_service.get_user_by_email(session, str(payload.email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        )

    try:
        user = user_service.create_user(session, payload)
    except user_service.UserAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        ) from exc

    return UserRead.model_validate(user)


@router.post("/login", response_model=AccessToken)
def login(
    payload: UserLogin,
    session: Annotated[Session, Depends(get_db)],
) -> AccessToken:
    user = user_service.authenticate_user(
        session,
        email=str(payload.email),
        password=payload.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AccessToken(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
def read_me(current_user: Annotated[User, Depends(get_current_user)]) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: Annotated[User, Depends(get_current_user)]) -> Response:
    _ = current_user
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    payload: PasswordResetRequest,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    # 계정 존재 여부를 응답으로 드러내지 않기 위해 항상 202를 반환한다.
    password_reset_service.request_password_reset(session, email=str(payload.email))
    return {"detail": "If the email is registered, a reset message has been sent."}


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    payload: PasswordResetConfirm,
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        password_reset_service.confirm_password_reset(
            session,
            token=payload.token,
            new_password=payload.new_password,
        )
    except password_reset_service.InvalidResetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token is invalid or expired.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
