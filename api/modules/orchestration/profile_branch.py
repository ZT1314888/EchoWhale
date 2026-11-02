"""学员档案增强分支（多 Agent 升级 P0，自 session_engine/agent.py 原样迁入）。

P0 形态的「Memory Manager 前身」（02_target_architecture.md §3.3）：读路径
渲染跨轮注入块（失败→静态注入回退），写路径把单轮反馈滚动累计进档案
（失败→记日志降级）。P2 的 memory_events 事件化长期记忆在本类上扩展，
不改调用面。
"""

from __future__ import annotations

import logging

from api.core.config import settings
from api.db.learner_profile_db import LearnerProfileRepository
from api.models.learner_profile_model import LearnerProfile
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.session_engine.learner_profile import (
    apply_turn_to_profile,
    build_learner_context_lines,
)

logger = logging.getLogger(__name__)


class LearnerProfileBranch:
    """封装档案读（注入块渲染）与写（单轮滚动累计）两条增强分支。

    门控：user_id 不以 user: 开头（visitor）零查询直接回退——访客身份可轮换、
    键无界且无清理语义，不建档也不读档，避免无意义的点查与日志噪音。
    仓储在构造时注入（测试经构造器传 fake，无需构造后替换）。
    """

    def __init__(self, repository: LearnerProfileRepository) -> None:
        self._repository = repository

    async def load_profile(self, user_id: str) -> LearnerProfile | None:
        """PK 点查学员档案；任何失败都降级为静态注入，绝不拖垮回复轮。

        点查是主键单行读（低成本）；失败只记 degraded warning 并返回 None，
        调用方回退 COACH_LEARNER_LEVEL 静态注入与空注入块。
        """
        try:
            return await self._repository.get(user_id)
        except Exception as exc:  # noqa: BLE001 - 档案读失败需降级续轮而非上抛
            logger.warning(
                "learner_profile_load_failed degraded=true user_id=%s error=%s: %s",
                user_id,
                type(exc).__name__,
                exc,
            )
            return None

    async def context_for_turn(self, session_head: Session) -> tuple[str | None, str | None]:
        """渲染本轮的学员注入块与 CEFR 估计；visitor / 无档案 / 读失败回退 (None, None)。"""
        if not session_head.user_id.startswith("user:"):
            return (None, None)
        profile = await self.load_profile(session_head.user_id)
        if profile is None:
            return (None, None)
        return (build_learner_context_lines(profile), profile.cefr_estimate)

    async def update_for_turn(
        self,
        session_head: Session,
        feedback: FeedbackResult,
    ) -> None:
        """把单轮反馈信号滚动累计进学员档案（增强分支，独立于消息落库事务）。

        与 save_reply_turn / finalize_voice_session 是不同连接不同事务：
        档案写失败可独立回滚，消息已提交不受影响（Orchestration failure
        policy——主价值是回复轮，档案只是估算用途的增强状态）。
        只捕获 Exception：CancelledError 等 BaseException 不吞，取消语义保持。
        并发取舍（已知并接受）：同用户并发轮的 read-modify-write 非原子，
        最坏丢一次计数（last-write-wins）；单用户并发轮罕见，不值得为此上
        SELECT FOR UPDATE（还会拖 SQLite 测试兼容）。
        """
        user_id = session_head.user_id
        if not user_id.startswith("user:"):
            return
        try:
            profile = await self._repository.get(user_id)
            profile = apply_turn_to_profile(
                profile,
                user_id=user_id,
                scene=session_head.scene,
                feedback=feedback,
                scene_cap=settings.learner_profile_scene_cap,
                cefr_window=settings.learner_profile_cefr_window,
            )
            await self._repository.upsert(profile)
        except Exception as exc:  # noqa: BLE001 - 档案写失败需降级续轮而非上抛
            logger.warning(
                "learner_profile_update_failed degraded=true user_id=%s error=%s: %s",
                user_id,
                type(exc).__name__,
                exc,
            )
