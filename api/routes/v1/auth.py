from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.common.deps import get_refresh_token, require_authenticated_user
from api.common.responses import ApiResponse
from api.core.config import settings
from api.models.auth_model import AuthSession
from api.models.user_model import User
from api.services.auth_service import AuthService, get_auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    nickname: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthUserResponse(BaseModel):
    user_id: str
    email: str
    nickname: str

    @classmethod
    def from_user(cls, user: User) -> "AuthUserResponse":
        return cls(
            user_id=user.id,
            email=user.email,
            nickname=user.nickname,
        )


class AuthSessionResponse(BaseModel):
    access_token: str
    user: AuthUserResponse

    @classmethod
    def from_session(cls, session: AuthSession) -> "AuthSessionResponse":
        return cls(
            access_token=session.access_token,
            user=AuthUserResponse.from_user(session.user),
        )


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


@router.post("/register", response_model=ApiResponse[AuthSessionResponse])
def register(
    payload: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> Any:
    session = auth_service.register(
        nickname=payload.nickname,
        email=payload.email,
        password=payload.password,
    )
    response = ApiResponse.success(data=AuthSessionResponse.from_session(session))
    return _with_refresh_cookie(response, session.refresh_token)


@router.post("/login", response_model=ApiResponse[AuthSessionResponse])
def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> Any:
    session = auth_service.login(email=payload.email, password=payload.password)
    response = ApiResponse.success(data=AuthSessionResponse.from_session(session))
    return _with_refresh_cookie(response, session.refresh_token)


@router.post("/refresh", response_model=ApiResponse[AuthSessionResponse])
def refresh(
    refresh_token: str = Depends(get_refresh_token),
    auth_service: AuthService = Depends(get_auth_service),
) -> Any:
    session = auth_service.refresh(refresh_token=refresh_token)
    response = ApiResponse.success(data=AuthSessionResponse.from_session(session))
    return _with_refresh_cookie(response, session.refresh_token)


@router.get("/me", response_model=ApiResponse[AuthUserResponse])
def me(current_user: User = Depends(require_authenticated_user)) -> Any:
    return ApiResponse.success(data=AuthUserResponse.from_user(current_user))


@router.post("/logout")
def logout(
    current_user: User = Depends(require_authenticated_user),
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
