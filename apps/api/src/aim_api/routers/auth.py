from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from aim_api.database import get_db
from aim_api.dependencies import get_current_user, oauth2_scheme
from aim_api.models.user import User
from aim_api.schemas.auth import (
    AccessToken,
    EmailVerificationConfirm,
    EmailVerificationRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    UserCreate,
    UserLogin,
    UserRead,
)
from aim_api.security import create_access_token, decode_access_token
from aim_api.services import email_verification as email_verification_service
from aim_api.services import password_resets as password_reset_service
from aim_api.services import token_revocation
from aim_api.services import users as user_service
from aim_api.services.rate_limit import rate_limited

router = APIRouter(prefix="/auth", tags=["auth"])

# 비인증 엔드포인트의 IP당 분당 한도. 브루트포스·계정 남발·메일 폭탄 방지가 목적이며
# 정상 사용자는 도달하지 않는 수준으로 잡는다.
signup_rate_limit = rate_limited("auth-signup", limit=5)
login_rate_limit = rate_limited("auth-login", limit=10)
password_reset_request_rate_limit = rate_limited("password-reset-request", limit=5)
password_reset_confirm_rate_limit = rate_limited("password-reset-confirm", limit=10)
email_verification_request_rate_limit = rate_limited("email-verification-request", limit=5)
email_verification_confirm_rate_limit = rate_limited("email-verification-confirm", limit=10)


@router.post(
    "/signup",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(signup_rate_limit)],
)
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

    # SMTP가 설정된 환경에서는 인증 메일을 보내고, 없으면 즉시 인증 완료로 처리한다.
    email_verification_service.start_email_verification(session, user=user)

    return UserRead.model_validate(user)


@router.post("/login", response_model=AccessToken, dependencies=[Depends(login_rate_limit)])
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

    # 자격 증명이 맞아도 이메일 소유 확인 전에는 로그인시키지 않는다.
    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email is not verified.",
        )

    return AccessToken(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
def read_me(current_user: Annotated[User, Depends(get_current_user)]) -> UserRead:
    return UserRead.model_validate(current_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    current_user: Annotated[User, Depends(get_current_user)],
    token: Annotated[str, Depends(oauth2_scheme)],
) -> Response:
    _ = current_user
    # 남은 수명 동안 이 토큰을 서버 측에서도 무효화한다.
    claims = decode_access_token(token)
    if claims is not None:
        token_revocation.revoke_token(claims)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/password-reset/request",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(password_reset_request_rate_limit)],
)
def request_password_reset(
    payload: PasswordResetRequest,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    # 계정 존재 여부를 응답으로 드러내지 않기 위해 항상 202를 반환한다.
    password_reset_service.request_password_reset(session, email=str(payload.email))
    return {"detail": "If the email is registered, a reset message has been sent."}


@router.post(
    "/password-reset/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(password_reset_confirm_rate_limit)],
)
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


@router.post(
    "/email-verification/request",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(email_verification_request_rate_limit)],
)
def request_email_verification(
    payload: EmailVerificationRequest,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    # 계정 존재·인증 여부를 응답으로 드러내지 않기 위해 항상 202를 반환한다.
    email_verification_service.request_email_verification(session, email=str(payload.email))
    return {
        "detail": "If the email is registered and unverified, a verification message has been sent."
    }


@router.post(
    "/email-verification/confirm",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(email_verification_confirm_rate_limit)],
)
def confirm_email_verification(
    payload: EmailVerificationConfirm,
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        email_verification_service.confirm_email_verification(session, token=payload.token)
    except email_verification_service.InvalidVerificationTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token is invalid or expired.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
