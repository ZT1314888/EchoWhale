"""user_learning_profiles 表：每认证用户一行的滚动学习档案（迁移 0013）。

写侧由 session_engine 编排更新（reply / stream / 语音收口三个时机，独立于
消息落库事务）；读侧只做 PK 点查并渲染提示词注入块。访客（visitor:*）不
建档：访客身份是可轮换的签名 cookie，键无界增长且没有合并/清理语义，
建档价值为零、清理成本无上限——门控在编排层（user_id 前缀判断）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.db.database import AsyncSessionFactory, Base, get_async_session_factory
from api.models.learner_profile_model import LearnerProfile


class LearnerProfileRepository(Protocol):
    async def get(self, user_id: str) -> LearnerProfile | None: ...

    async def upsert(self, profile: LearnerProfile) -> LearnerProfile: ...


class UserLearningProfileRecord(Base):
    __tablename__ = "user_learning_profiles"

    # owner 全串 user:<id>；users.id 为 String(64)，5 + 64 的列宽与 sessions 对齐。
    # 不加 FK：与 sessions.user_id 的既有约定一致（该列同时承载过 visitor 串的
    # 历史语义），本表只写 user: 串，由应用层前缀门控保证。
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # A1..C2 封闭集合值；无观测时为 None（注入侧回退静态水平描述）。
    cefr_estimate: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # ≤9 键：仅 9 类封闭错误集合的计数，模型幻觉 category 在写侧被防御性丢弃。
    error_type_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    # ≤learner_profile_scene_cap 键：插入序 = 近期序，超上限从头（最旧）淘汰。
    scene_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    # ≤learner_profile_cefr_window 项：最近 CEFR 观测窗口，供 median_low 滚动估计。
    cefr_history: Mapped[list[str]] = mapped_column(JSON, default=list)
    practiced_turn_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SqlAlchemyLearnerProfileRepository:
    def __init__(self, session_factory: AsyncSessionFactory | None = None) -> None:
        self._session_factory = session_factory or get_async_session_factory()

    async def get(self, user_id: str) -> LearnerProfile | None:
        """PK 点查：单行单事务，读不到（首访用户）返回 None。"""
        async with self._session_factory() as db_session:
            record = await db_session.get(UserLearningProfileRecord, user_id)
            if record is None:
                return None
            return _to_profile(record)

    async def upsert(self, profile: LearnerProfile) -> LearnerProfile:
        """覆盖写单行：档案更新是 read-modify-write 的写半程，单行单事务。"""
        now = datetime.now(UTC)
        async with self._session_factory() as db_session:
            record = await db_session.get(UserLearningProfileRecord, profile.user_id)
            if record is None:
                record = UserLearningProfileRecord(
                    user_id=profile.user_id,
                    created_at=profile.created_at,
                )
                db_session.add(record)
            record.cefr_estimate = profile.cefr_estimate
            record.error_type_counts = dict(profile.error_type_counts)
            record.scene_counts = dict(profile.scene_counts)
            record.cefr_history = list(profile.cefr_history)
            record.practiced_turn_count = profile.practiced_turn_count
            record.updated_at = now
            await db_session.commit()
            return _to_profile(record)


def _to_profile(record: UserLearningProfileRecord) -> LearnerProfile:
    """手写 record → 域模型映射（仓库约定：不用 ORM relationship 加载）。"""
    return LearnerProfile(
        user_id=record.user_id,
        cefr_estimate=record.cefr_estimate,
        error_type_counts=dict(record.error_type_counts or {}),
        scene_counts=dict(record.scene_counts or {}),
        cefr_history=list(record.cefr_history or []),
        practiced_turn_count=record.practiced_turn_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def build_learner_profile_repository(
    session_factory: AsyncSessionFactory | None = None,
) -> LearnerProfileRepository:
    return SqlAlchemyLearnerProfileRepository(session_factory)
