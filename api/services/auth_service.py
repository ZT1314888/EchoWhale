from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from api.common.exceptions import AuthenticationError, ValidationError
from api.core.config import settings
from api.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from api.db.auth_db import AuthRepository, build_auth_repository
from api.models.auth_model import AuthSession
from api.models.user_model import RefreshTokenRecordModel, User


class AuthService:
    def __init__(self, repository: AuthRepository | None = None) -> None:
        self.repository = repository or build_auth_repository()

    def register(self, *, nickname: str, email: str, password: str) -> User:
        normalized_email = self._normalize_email(email)
        self._validate_password(password)
        if self.repository.get_user_by_email(normalized_email) is not None:
            raise ValidationError("Email already registered")

        user = User(
            id=f"user_{uuid4().hex[:12]}",
            email=normalized_email,
            nickname=nickname.strip(),
        )
        self.repository.create_user(user=user, password_hash=hash_password(password))
        return user

    def login(self, *, email: str, password: str) -> AuthSession:
        normalized_email = self._normalize_email(email)
        credentials = self.repository.get_password_hash_by_email(normalized_email)
        if credentials is None:
            raise AuthenticationError("Invalid email or password")

        user, password_hash = credentials
        if not verify_password(password, password_hash):
            raise AuthenticationError("Invalid email or password")

        self.repository.update_last_login(user.id, datetime.now(timezone.utc))
        return self._issue_session(user)

    def get_current_user(self, *, access_token: str) -> User:
        payload = decode_access_token(access_token, secret=settings.auth_jwt_secret)
        return self.repository.get_user_by_id(payload["sub"])

    def refresh(self, *, refresh_token: str) -> AuthSession:
        token_hash = hash_refresh_token(refresh_token)
        stored_token = self.repository.get_refresh_token(token_hash)
        if stored_token is None or stored_token.revoked_at is not None:
            raise AuthenticationError("Authentication required")
        if self._as_utc(stored_token.expires_at) <= datetime.now(timezone.utc):
            raise AuthenticationError("Authentication required")

        self.repository.revoke_refresh_token(stored_token.id, datetime.now(timezone.utc))
        user = self.repository.get_user_by_id(stored_token.user_id)
        return self._issue_session(user)

    def logout(self, *, refresh_token: str) -> None:
        token_hash = hash_refresh_token(refresh_token)
        stored_token = self.repository.get_refresh_token(token_hash)
        if stored_token is None:
            raise AuthenticationError("Authentication required")
        self.repository.revoke_refresh_token(stored_token.id, datetime.now(timezone.utc))

    def _issue_session(self, user: User) -> AuthSession:
        refresh_token = generate_refresh_token()
        now = datetime.now(timezone.utc)
        self.repository.save_refresh_token(
            RefreshTokenRecordModel(
                id=f"rt_{uuid4().hex[:12]}",
                user_id=user.id,
                token_hash=hash_refresh_token(refresh_token),
                expires_at=now + timedelta(seconds=settings.auth_refresh_token_ttl_seconds),
                created_at=now,
            )
        )
        return AuthSession(
            access_token=create_access_token(
                subject=user.id,
                secret=settings.auth_jwt_secret,
                expires_in_seconds=settings.auth_access_token_ttl_seconds,
            ),
            refresh_token=refresh_token,
            user=user,
        )

    def _normalize_email(self, email: str) -> str:
        normalized = email.strip().lower()
        if not normalized:
            raise ValidationError("Email is required")
        return normalized

    def _validate_password(self, password: str) -> None:
        if len(password.strip()) < 8:
            raise ValidationError("Password must be at least 8 characters")

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def get_auth_service() -> AuthService:
    return AuthService()
