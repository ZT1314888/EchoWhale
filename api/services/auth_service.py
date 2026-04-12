from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlencode
from uuid import uuid4

from api.common.exceptions import (
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from api.core.config import settings
from api.core.security import (
    create_access_token,
    decode_access_token,
    generate_action_token,
    generate_refresh_token,
    hash_action_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from api.db.auth_db import AuthRepository, build_auth_repository
from api.models.auth_model import AuthSession
from api.models.auth_token_model import (
    AUTH_TOKEN_PURPOSE_PASSWORD_RESET,
    AuthActionTokenModel,
)
from api.models.user_model import RefreshTokenRecordModel, User
from api.services.auth_mail_queue import AuthMailQueuePublisher
from api.services.auth_mail_queue import get_auth_mail_queue_publisher
from api.services.email_verification_store import (
    EmailVerificationStore,
    get_email_verification_store,
)
from sqlalchemy.exc import IntegrityError


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthService:
    def __init__(
        self,
        repository: AuthRepository | None = None,
        mail_queue_publisher: AuthMailQueuePublisher | None = None,
        verification_store: EmailVerificationStore | None = None,
    ) -> None:
        self.repository = repository or build_auth_repository()
        self.mail_queue_publisher = mail_queue_publisher or get_auth_mail_queue_publisher()
        self.verification_store = verification_store or get_email_verification_store()

    def register(self, *, nickname: str, email: str, password: str, ip_address: str) -> User:
        normalized_email = self._normalize_email(email)
        normalized_nickname = self._normalize_nickname(nickname)
        normalized_password = self._normalize_password(password)
        if self.repository.get_user_by_email(normalized_email) is not None:
            raise ValidationError("Email already registered")

        user = User(
            id=f"user_{uuid4().hex[:12]}",
            email=normalized_email,
            nickname=normalized_nickname,
            status="pending_verification",
        )
        try:
            self.repository.create_user(
                user=user,
                password_hash=hash_password(normalized_password),
            )
        except IntegrityError as error:
            raise ValidationError("Email already registered") from error
        self._issue_email_verification(user, ip_address=ip_address)
        return user

    def login(self, *, email: str, password: str) -> AuthSession:
        normalized_email = self._normalize_email(email)
        credentials = self.repository.get_password_hash_by_email(normalized_email)
        if credentials is None:
            raise AuthenticationError("Invalid email or password")

        user, password_hash = credentials
        self._ensure_user_can_authenticate(user)
        if not verify_password(password, password_hash):
            raise AuthenticationError("Invalid email or password")

        self.repository.update_last_login(user.id, datetime.now(timezone.utc))
        return self._issue_session(user)

    def get_current_user(self, *, access_token: str) -> User:
        payload = decode_access_token(access_token, secret=settings.auth_jwt_secret)
        try:
            user = self.repository.get_user_by_id(payload["sub"])
        except NotFoundError as error:
            raise AuthenticationError("Authentication required") from error
        self._ensure_user_can_authenticate(user)
        return user

    def refresh(self, *, refresh_token: str) -> AuthSession:
        token_hash = hash_refresh_token(refresh_token)
        rotated_refresh_token = generate_refresh_token()
        now = datetime.now(timezone.utc)
        replacement_token = RefreshTokenRecordModel(
            id=f"rt_{uuid4().hex[:12]}",
            user_id="",
            token_hash=hash_refresh_token(rotated_refresh_token),
            expires_at=now + timedelta(seconds=settings.auth_refresh_token_ttl_seconds),
            created_at=now,
        )
        user_id = self.repository.rotate_refresh_token(
            token_hash=token_hash,
            replacement_token=replacement_token,
            revoked_at=now,
            now=now,
        )
        if user_id is None:
            raise AuthenticationError("Authentication required")

        try:
            user = self.repository.get_user_by_id(user_id)
        except NotFoundError as error:
            raise AuthenticationError("Authentication required") from error
        self._ensure_user_can_authenticate(user)
        replacement_token.user_id = user.id
        return AuthSession(
            access_token=create_access_token(
                subject=user.id,
                secret=settings.auth_jwt_secret,
                expires_in_seconds=settings.auth_access_token_ttl_seconds,
            ),
            refresh_token=rotated_refresh_token,
            user=user,
        )

    def resend_verification(self, *, email: str, ip_address: str) -> None:
        normalized_email = self._normalize_email(email)
        user = self.repository.get_user_by_email(normalized_email)
        if user is None or user.status != "pending_verification":
            return
        self._issue_email_verification(user, ip_address=ip_address)

    def verify_email(self, *, email: str, code: str) -> User:
        normalized_email = self._normalize_email(email)
        user = self.repository.get_user_by_email(normalized_email)
        if user is None:
            raise ValidationError("Verification code is invalid or expired")
        if user.status == "disabled":
            raise AuthenticationError("Authentication required")
        if user.status != "pending_verification":
            raise ValidationError("Verification code is invalid or expired")
        self.verification_store.consume_code(email=normalized_email, code=code.strip())
        activated_at = datetime.now(timezone.utc)
        self.repository.update_user_status(user.id, "active", activated_at)
        user.status = "active"
        user.updated_at = activated_at
        return user

    def forgot_password(self, *, email: str) -> None:
        normalized_email = self._normalize_email(email)
        user = self.repository.get_user_by_email(normalized_email)
        if user is None or user.status != "active":
            return
        self._issue_password_reset(user)

    def reset_password(self, *, token: str, password: str) -> None:
        normalized_password = self._normalize_password(password)
        stored_token = self._consume_auth_action_token(
            token=token,
            purpose=AUTH_TOKEN_PURPOSE_PASSWORD_RESET,
            error_message="Password reset link is invalid or expired",
        )
        user = self.repository.get_user_by_id(stored_token.user_id)
        self._ensure_user_is_active(user)
        updated_at = datetime.now(timezone.utc)
        self.repository.update_password_hash(
            user.id,
            hash_password(normalized_password),
            updated_at,
        )
        self.repository.revoke_all_refresh_tokens(user.id, updated_at)

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
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValidationError("Invalid email format")
        return normalized

    def _normalize_nickname(self, nickname: str) -> str:
        normalized = nickname.strip()
        if not normalized:
            raise ValidationError("Nickname is required")
        return normalized

    def _normalize_password(self, password: str) -> str:
        trimmed = password.strip()
        if not trimmed:
            raise ValidationError("Password is required")
        if len(trimmed) < 8:
            raise ValidationError("Password must be at least 8 characters")
        if not any(character.isalpha() for character in trimmed) or not any(
            character.isdigit() for character in trimmed
        ):
            raise ValidationError("Password must include letters and numbers")
        return trimmed

    def _ensure_user_can_authenticate(self, user: User) -> None:
        if user.status == "active":
            return
        if user.status == "pending_verification":
            raise PermissionDeniedError("Please verify your email before logging in")
        raise AuthenticationError("Authentication required")

    def _ensure_user_is_active(self, user: User) -> None:
        if user.status == "active":
            return
        raise AuthenticationError("Authentication required")

    def _consume_auth_action_token(
        self,
        *,
        token: str,
        purpose: str,
        error_message: str,
    ) -> AuthActionTokenModel:
        now = datetime.now(timezone.utc)
        stored_token = self.repository.consume_auth_action_token(
            token_hash=hash_action_token(token),
            purpose=purpose,
            consumed_at=now,
            now=now,
        )
        if stored_token is None:
            raise ValidationError(error_message)
        return stored_token

    def _issue_email_verification(self, user: User, *, ip_address: str) -> None:
        code = self.verification_store.issue_code(email=user.email, ip_address=ip_address)
        self.mail_queue_publisher.enqueue_verification_email(
            user_id=user.id,
            email=user.email,
            nickname=user.nickname,
            code=code,
        )

    def _issue_password_reset(self, user: User) -> None:
        token = generate_action_token()
        now = datetime.now(timezone.utc)
        self.repository.replace_auth_action_token(
            AuthActionTokenModel(
                id=f"prt_{uuid4().hex[:12]}",
                user_id=user.id,
                purpose=AUTH_TOKEN_PURPOSE_PASSWORD_RESET,
                token_hash=hash_action_token(token),
                expires_at=now + timedelta(hours=2),
                created_at=now,
            ),
            superseded_at=now,
        )
        self.mail_queue_publisher.enqueue_password_reset_email(
            user_id=user.id,
            email=user.email,
            nickname=user.nickname,
            reset_url=self._build_reset_password_url(token),
        )

    def _build_reset_password_url(self, token: str) -> str:
        base_url = settings.frontend_public_base_url.strip().rstrip("/")
        return f"{base_url}/reset-password?{urlencode({'token': token})}"

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def get_auth_service() -> AuthService:
    return AuthService()
