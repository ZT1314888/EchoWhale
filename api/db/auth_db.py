from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, mapped_column

from api.common.exceptions import NotFoundError
from api.db.database import Base, SessionFactory, get_session_factory
from api.models.user_model import RefreshTokenRecordModel, User


class AuthRepository(Protocol):
    def create_user(self, *, user: User, password_hash: str) -> User: ...

    def get_user_by_email(self, email: str) -> User | None: ...

    def get_user_by_id(self, user_id: str) -> User: ...

    def get_password_hash_by_email(self, email: str) -> tuple[User, str] | None: ...

    def update_last_login(self, user_id: str, logged_in_at: datetime) -> None: ...

    def save_refresh_token(self, token: RefreshTokenRecordModel) -> RefreshTokenRecordModel: ...

    def get_refresh_token(self, token_hash: str) -> RefreshTokenRecordModel | None: ...

    def revoke_refresh_token(self, token_id: str, revoked_at: datetime) -> None: ...


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserCredentialRecord(Base):
    __tablename__ = "user_credentials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(512))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RefreshTokenRecord(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SqlAlchemyAuthRepository:
    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def create_user(self, *, user: User, password_hash: str) -> User:
        with self._session_factory() as session:
            session.add(
                UserRecord(
                    id=user.id,
                    email=user.email,
                    nickname=user.nickname,
                    status=user.status,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                )
            )
            # 先落父 users 记录，避免严格 FK 校验数据库先写 credentials。
            session.flush()
            session.add(
                UserCredentialRecord(
                    id=f"cred_{user.id}",
                    user_id=user.id,
                    provider="password",
                    password_hash=password_hash,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                )
            )
            session.commit()
        return user

    def get_user_by_email(self, email: str) -> User | None:
        with self._session_factory() as session:
            record = session.scalar(select(UserRecord).where(UserRecord.email == email))
            if record is None:
                return None
            return _to_user(record)

    def get_user_by_id(self, user_id: str) -> User:
        with self._session_factory() as session:
            record = session.get(UserRecord, user_id)
            if record is None:
                raise NotFoundError(f"User {user_id} not found")
            return _to_user(record)

    def get_password_hash_by_email(self, email: str) -> tuple[User, str] | None:
        with self._session_factory() as session:
            record = session.scalar(select(UserRecord).where(UserRecord.email == email))
            if record is None:
                return None
            credential = session.scalar(
                select(UserCredentialRecord).where(
                    UserCredentialRecord.user_id == record.id,
                    UserCredentialRecord.provider == "password",
                )
            )
            if credential is None:
                return None
            return (_to_user(record), credential.password_hash)

    def update_last_login(self, user_id: str, logged_in_at: datetime) -> None:
        with self._session_factory() as session:
            credential = session.scalar(
                select(UserCredentialRecord).where(
                    UserCredentialRecord.user_id == user_id,
                    UserCredentialRecord.provider == "password",
                )
            )
            if credential is None:
                raise NotFoundError(f"Credentials for user {user_id} not found")
            credential.last_login_at = logged_in_at
            credential.updated_at = logged_in_at
            session.commit()

    def save_refresh_token(self, token: RefreshTokenRecordModel) -> RefreshTokenRecordModel:
        with self._session_factory() as session:
            session.merge(
                RefreshTokenRecord(
                    id=token.id,
                    user_id=token.user_id,
                    token_hash=token.token_hash,
                    expires_at=token.expires_at,
                    revoked_at=token.revoked_at,
                    created_at=token.created_at,
                )
            )
            session.commit()
        return token

    def get_refresh_token(self, token_hash: str) -> RefreshTokenRecordModel | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(RefreshTokenRecord).where(RefreshTokenRecord.token_hash == token_hash)
            )
            if record is None:
                return None
            return RefreshTokenRecordModel(
                id=record.id,
                user_id=record.user_id,
                token_hash=record.token_hash,
                expires_at=record.expires_at,
                revoked_at=record.revoked_at,
                created_at=record.created_at,
            )

    def revoke_refresh_token(self, token_id: str, revoked_at: datetime) -> None:
        with self._session_factory() as session:
            record = session.get(RefreshTokenRecord, token_id)
            if record is None:
                raise NotFoundError(f"Refresh token {token_id} not found")
            record.revoked_at = revoked_at
            session.commit()


def build_auth_repository(session_factory: SessionFactory | None = None) -> AuthRepository:
    return SqlAlchemyAuthRepository(session_factory)


def _to_user(record: UserRecord) -> User:
    return User(
        id=record.id,
        email=record.email,
        nickname=record.nickname,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
