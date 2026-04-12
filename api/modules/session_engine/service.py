from __future__ import annotations

from pydantic import ValidationError as PydanticValidationError

from api.common.exceptions import NotFoundError
from api.common.exceptions import ValidationError
from api.models.message_model import Message
from api.models.session_model import Session
from api.db.media_db import MediaLookup
from api.db.session_db import SessionRepository
from api.integrations.storage.r2 import R2StorageService
from api.models.review_model import SessionReview
from api.modules.session_engine.agent import SessionEngineAgent
from api.modules.session_engine.schema import (
    ReplyInput,
    StartSessionInput,
    VoiceBootstrapResult,
    VoiceCompleteInput,
    VoiceCompleteResult,
)


class SessionEngineService:
    def __init__(
        self,
        media_lookup: MediaLookup | None = None,
        session_repository: SessionRepository | None = None,
        read_url_signer: R2StorageService | None = None,
    ) -> None:
        """装配会话编排 agent，对外暴露更稳定的服务层接口。"""
        self.agent = SessionEngineAgent(
            media_lookup=media_lookup,
            session_repository=session_repository,
            read_url_signer=read_url_signer,
        )

    async def start_session(
        self,
        user_id: str,
        media_id: str | None = None,
        sample_scene_id: str | None = None,
    ) -> Session:
        """创建新会话，并统一处理图片场景和样例场景入口。"""
        payload = StartSessionInput(
            user_id=user_id,
            media_id=media_id,
            sample_scene_id=sample_scene_id,
        )
        return await self.agent.start(payload)

    async def get_session(self, session_id: str, owner_id: str | None = None) -> Session:
        """读取会话并在服务层校验归属权。"""
        session = await self.agent.get(session_id)
        return self._ensure_owner(session, owner_id)

    async def reply_to_session(
        self,
        session_id: str,
        learner_message: str,
        owner_id: str | None = None,
    ) -> Session:
        """在确认所有权后，写入学习者回复并生成新一轮 assistant 消息。"""
        self._ensure_owner(await self.agent.get(session_id), owner_id)
        payload = ReplyInput(session_id=session_id, learner_message=learner_message)
        return await self.agent.reply(payload)

    async def get_session_review(self, session_id: str, owner_id: str | None = None) -> SessionReview:
        """读取会话复盘前先校验访问者是否拥有该会话。"""
        self._ensure_owner(await self.agent.get(session_id), owner_id)
        return await self.agent.get_review(session_id)

    async def list_history_sessions(self, user_id: str) -> list[Session]:
        """列出用户所有历史会话。"""
        return await self.agent.list_history_sessions(user_id)

    async def list_history_sessions_page(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Session], bool, str | None]:
        """按游标分页返回历史会话摘要。"""
        return await self.agent.list_history_sessions_page(
            user_id,
            limit=limit,
            cursor=cursor,
        )

    async def list_history_reviews(self, session_ids: list[str]) -> dict[str, SessionReview]:
        """批量读取指定历史会话的复盘结果。"""
        return await self.agent.list_history_reviews(session_ids)

    async def get_history_session_overview(
        self,
        user_id: str,
        session_id: str,
    ) -> tuple[Session, SessionReview, int]:
        """读取历史详情页所需的头信息、复盘和消息数量。"""
        session, review, total_messages = await self.agent.get_history_session_overview(session_id)
        self._ensure_owner(session, user_id)
        return (session, review, total_messages)

    async def list_history_session_messages(
        self,
        user_id: str,
        session_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Message], bool, str | None]:
        """分页读取历史会话消息，并在入口处拦截越权访问。"""
        session = await self.agent.get_session_head(session_id)
        self._ensure_owner(session, user_id)
        return await self.agent.list_history_session_messages_page(
            session_id,
            limit=limit,
            cursor=cursor,
        )

    async def get_history_session_detail(self, user_id: str, session_id: str) -> tuple[Session, SessionReview]:
        """返回历史会话详情页需要的会话体和复盘内容。"""
        session = self._ensure_owner(await self.agent.get(session_id), user_id)
        return (session, await self.agent.get_review(session_id))

    async def bootstrap_voice_session(
        self,
        session_id: str,
        owner_id: str | None = None,
    ) -> VoiceBootstrapResult:
        """在确认所有权后初始化实时语音会话。"""
        self._ensure_owner(await self.agent.get(session_id), owner_id)
        return await self.agent.bootstrap_voice_session(session_id)

    async def complete_voice_session(
        self,
        session_id: str,
        conversation,
        termination_reason: str,
        client_diagnostics: dict[str, object] | None = None,
        owner_id: str | None = None,
    ) -> VoiceCompleteResult:
        """校验语音完成请求并把 transcript 收束为最终 review。"""
        self._ensure_owner(await self.agent.get(session_id), owner_id)
        try:
            payload = VoiceCompleteInput(
                session_id=session_id,
                conversation=conversation,
                termination_reason=termination_reason,
                client_diagnostics=client_diagnostics or {},
            )
        except PydanticValidationError as exc:
            raise ValidationError("Validation error") from exc
        return await self.agent.complete_voice_session(payload)

    def _ensure_owner(self, session: Session, owner_id: str | None) -> Session:
        """把越权访问统一收敛成未找到，避免暴露会话存在性。"""
        if owner_id is None or session.user_id == owner_id:
            return session
        raise NotFoundError(f"Session {session.id} not found")
