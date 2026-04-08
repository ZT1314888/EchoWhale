from __future__ import annotations

import re

from pydantic import BaseModel, field_validator

from api.models.auth_model import AuthSession
from api.models.user_model import User


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email_shape(value: str) -> str:
    normalized = value.strip()
    if not normalized or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid email format")
    return value


def _validate_present_password(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Password is required")
    return normalized


def _validate_present_nickname(value: str) -> str:
    if not value.strip():
        raise ValueError("Nickname is required")
    return value


def _validate_token(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Token is required")
    return normalized


def _validate_verification_code(value: str) -> str:
    normalized = value.strip()
    if not re.fullmatch(r"\d{6}", normalized):
        raise ValueError("Verification code must be 6 digits")
    return normalized


class RegisterRequest(BaseModel):
    nickname: str
    email: str
    password: str

    _validate_nickname = field_validator("nickname")(_validate_present_nickname)
    _validate_email = field_validator("email")(_validate_email_shape)
    _validate_password = field_validator("password")(_validate_present_password)


class LoginRequest(BaseModel):
    email: str
    password: str

    _validate_email = field_validator("email")(_validate_email_shape)
    _validate_password = field_validator("password")(_validate_present_password)


class EmailRequest(BaseModel):
    email: str

    _validate_email = field_validator("email")(_validate_email_shape)


class VerifyEmailRequest(BaseModel):
    email: str
    code: str

    _validate_email = field_validator("email")(_validate_email_shape)
    _validate_code = field_validator("code")(_validate_verification_code)


class ResetPasswordRequest(BaseModel):
    token: str
    password: str

    _validate_token = field_validator("token")(_validate_token)
    _validate_password = field_validator("password")(_validate_present_password)


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


class RegisterResponse(BaseModel):
    user_id: str
    email: str
    nickname: str

    @classmethod
    def from_user(cls, user: User) -> "RegisterResponse":
        return cls(
            user_id=user.id,
            email=user.email,
            nickname=user.nickname,
        )
