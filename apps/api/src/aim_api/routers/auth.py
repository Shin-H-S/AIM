from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user
from aim_api.models.user import User
from aim_api.schemas.auth import AccessToken, UserCreate, UserLogin, UserRead
from aim_api.security import create_access_token
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
