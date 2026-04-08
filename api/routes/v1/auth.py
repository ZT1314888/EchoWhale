from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from api.common.deps import get_refresh_token, require_authenticated_user
from api.common.responses import ApiResponse
from api.contracts.auth import (
    AuthSessionResponse,
    AuthUserResponse,
    EmailRequest,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from api.core.config import settings
from api.core.security import hash_action_token, hash_refresh_token
from api.models.user_model import User
from api.services.auth_rate_limit import AuthRateLimiter, get_auth_rate_limiter
from api.services.auth_service import AuthService, get_auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


def _with_refresh_cookie(response, refresh_token: str):
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.auth_refresh_token_ttl_seconds,
    )
    return response


def _build_rate_limit_key(request: Request, subject: str | None = None) -> str:
    client_host = request.client.host if request.client is not None else "unknown"
    if subject is None:
        return client_host
    return f"{client_host}:{subject}"


def _consume_rate_limit(
    *,
    request: Request,
    limiter: AuthRateLimiter,
    action: str,
    subject: str | None = None,
) -> None:
    limiter.consume(action=action, key=_build_rate_limit_key(request, subject))


@router.post("/register", response_model=ApiResponse[RegisterResponse])
def register(
    payload: RegisterRequest,
    request: Request,
    rate_limiter: AuthRateLimiter = Depends(get_auth_rate_limiter),
    auth_service: AuthService = Depends(get_auth_service),
) -> Any:
    _consume_rate_limit(
        request=request,
        limiter=rate_limiter,
        action="register",
        subject=payload.email,
    )
    user = auth_service.register(
        nickname=payload.nickname,
        email=payload.email,
        password=payload.password,
        ip_address=request.client.host if request.client is not None else "unknown",
    )
    return ApiResponse.success(data=RegisterResponse.from_user(user))


@router.post("/login", response_model=ApiResponse[AuthSessionResponse])
def login(
    payload: LoginRequest,
    request: Request,
    rate_limiter: AuthRateLimiter = Depends(get_auth_rate_limiter),
    auth_service: AuthService = Depends(get_auth_service),
) -> Any:
    _consume_rate_limit(
        request=request,
        limiter=rate_limiter,
        action="login",
        subject=payload.email,
    )
    session = auth_service.login(email=payload.email, password=payload.password)
    response = ApiResponse.success(data=AuthSessionResponse.from_session(session))
    return _with_refresh_cookie(response, session.refresh_token)


@router.post("/refresh", response_model=ApiResponse[AuthSessionResponse])
def refresh(
    request: Request,
    refresh_token: str = Depends(get_refresh_token),
    rate_limiter: AuthRateLimiter = Depends(get_auth_rate_limiter),
    auth_service: AuthService = Depends(get_auth_service),
) -> Any:
    _consume_rate_limit(
        request=request,
        limiter=rate_limiter,
        action="refresh",
        subject=hash_refresh_token(refresh_token),
    )
    session = auth_service.refresh(refresh_token=refresh_token)
    response = ApiResponse.success(data=AuthSessionResponse.from_session(session))
    return _with_refresh_cookie(response, session.refresh_token)


@router.get("/me", response_model=ApiResponse[AuthUserResponse])
def me(current_user: User = Depends(require_authenticated_user)) -> Any:
    return ApiResponse.success(data=AuthUserResponse.from_user(current_user))


@router.post("/resend-verification")
def resend_verification(
    payload: EmailRequest,
    request: Request,
    rate_limiter: AuthRateLimiter = Depends(get_auth_rate_limiter),
    auth_service: AuthService = Depends(get_auth_service),
):
    _consume_rate_limit(
        request=request,
        limiter=rate_limiter,
        action="resend_verification",
        subject=payload.email,
    )
    auth_service.resend_verification(
        email=payload.email,
        ip_address=request.client.host if request.client is not None else "unknown",
    )
    return ApiResponse.success_without_data()


@router.post("/verify-email")
def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    rate_limiter: AuthRateLimiter = Depends(get_auth_rate_limiter),
    auth_service: AuthService = Depends(get_auth_service),
):
    _consume_rate_limit(
        request=request,
        limiter=rate_limiter,
        action="verify_email",
        subject=payload.email,
    )
    auth_service.verify_email(email=payload.email, code=payload.code)
    return ApiResponse.success_without_data()


@router.post("/forgot-password")
def forgot_password(
    payload: EmailRequest,
    request: Request,
    rate_limiter: AuthRateLimiter = Depends(get_auth_rate_limiter),
    auth_service: AuthService = Depends(get_auth_service),
):
    _consume_rate_limit(
        request=request,
        limiter=rate_limiter,
        action="forgot_password",
        subject=payload.email,
    )
    auth_service.forgot_password(email=payload.email)
    return ApiResponse.success_without_data()


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    rate_limiter: AuthRateLimiter = Depends(get_auth_rate_limiter),
    auth_service: AuthService = Depends(get_auth_service),
):
    _consume_rate_limit(
        request=request,
        limiter=rate_limiter,
        action="reset_password",
        subject=hash_action_token(payload.token),
    )
    auth_service.reset_password(token=payload.token, password=payload.password)
    return ApiResponse.success_without_data()


@router.post("/logout")
def logout(
    refresh_token: str = Depends(get_refresh_token),
    auth_service: AuthService = Depends(get_auth_service),
):
    auth_service.logout(refresh_token=refresh_token)
    response = ApiResponse.success_without_data()
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response
