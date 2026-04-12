import asyncio
import inspect
from datetime import datetime, timezone
from uuid import uuid4

from api.common.enums import MediaUploadStatus
from api.common.exceptions import EchoWhaleError
from api.common.exceptions import InvalidStateError
from api.common.exceptions import SceneAnalysisUnavailableError
from api.common.exceptions import UnsupportedSceneImageError
from api.common.exceptions import ValidationError as AppValidationError
from api.core.config import settings
from api.db.media_db import MediaLookup, build_media_repository
from api.db.session_db import SessionRepository, build_session_repository
from api.integrations.deepgram import DeepgramSettingsBuilder
from api.integrations.deepgram import DeepgramTokenIssuer
from api.integrations.storage.r2 import R2StorageService
from api.models.message_model import Message
from api.models.review_model import SessionReview
from api.models.runtime_model import SessionEvent
from api.models.runtime_model import VoiceSessionFact
from api.models.session_model import Session
from api.modules.coach_engine.service import CoachEngineService
from api.modules.feedback_engine.service import FeedbackEngineService
from api.modules.scene_engine.service import SceneEngineService
from api.modules.session_engine.review_builder import build_session_review
from api.modules.session_engine.sample_presets import get_sample_session_preset
from api.modules.session_engine.schema import (
    ReplyInput,
    StartSessionInput,
    VoiceBootstrapResult,
    VoiceCompleteInput,
    VoiceCompleteResult,
)


class SessionEngineAgent:
    def __init__(
        self,
        media_lookup: MediaLookup | None = None,
        session_repository: SessionRepository | None = None,
        read_url_signer: R2StorageService | None = None,
    ) -> None:
        """装配会话编排依赖，包括媒体、存储、三段 agent 和语音组件。"""
        self.media_lookup = media_lookup or build_media_repository()
        self.session_repository = session_repository or build_session_repository()
        self.read_url_signer = read_url_signer or R2StorageService()
        self.scene_engine = SceneEngineService()
        self.coach_engine = CoachEngineService()
        self.feedback_engine = FeedbackEngineService()
        self.voice_token_issuer = DeepgramTokenIssuer()
        self.voice_settings_builder = DeepgramSettingsBuilder()

    async def start(self, payload: StartSessionInput) -> Session:
        """从样例场景或图片分析结果创建一条新会话。"""
        if payload.sample_scene_id is not None:
            preset = get_sample_session_preset(payload.sample_scene_id)
            session = Session(
                id=f"sess_{uuid4().hex[:12]}",
                user_id=payload.user_id,
                media_id=None,
                scene=preset.scene,
                role=preset.role,
                opener=preset.opener,
                visual_anchors=list(preset.visual_anchors),
                vocab_candidates=list(preset.vocab_candidates),
                messages=[Message(role="assistant", text=preset.opener)],
            )
            return await self.session_repository.save_session(session)

        assert payload.media_id is not None
        media = await self.media_lookup.get_media(payload.media_id)
        if media.upload_status != MediaUploadStatus.uploaded:
            raise InvalidStateError(f"Media {media.id} is not uploaded")

        signed_read_url, _ = await self.read_url_signer.async_create_signed_read_url(
            media.storage_key,
            expires_in=settings.r2_signed_url_ttl_seconds,
        )
        try:
            analysis = await self.scene_engine.analyze(media.filename, signed_read_url)
        except UnsupportedSceneImageError:
            raise
        except EchoWhaleError as exc:
            raise SceneAnalysisUnavailableError() from exc
        session = Session(
            id=f"sess_{uuid4().hex[:12]}",
            user_id=payload.user_id,
            media_id=media.id,
            scene=analysis.scene,
            role=analysis.role,
            opener=analysis.opener,
            visual_anchors=analysis.visual_anchors,
            vocab_candidates=analysis.vocab_candidates,
            messages=[Message(role="assistant", text=analysis.opener)],
        )
        return await self.session_repository.save_session(session)

    async def get(self, session_id: str) -> Session:
        """读取完整会话。"""
        return await self.session_repository.get_session(session_id)

    async def get_session_head(self, session_id: str) -> Session:
        """只读取会话头部信息，避免历史消息分页场景过载。"""
        return await self.session_repository.get_session_head(session_id)

    async def reply(self, payload: ReplyInput) -> Session:
        """并发生成反馈与教练回复，再把这一轮消息原子化落库。"""
        session = await self.session_repository.get_session(payload.session_id)
        feedback, coach_reply = await asyncio.gather(
            self._review_with_context(
                learner_message=payload.learner_message,
                scene=session.scene,
                vocab_candidates=session.vocab_candidates,
            ),
            self._respond_with_context(
                scene=session.scene,
                role=session.role,
                learner_message=payload.learner_message,
                visual_anchors=session.visual_anchors,
                vocab_candidates=session.vocab_candidates,
                recent_messages=list(session.messages),
            ),
        )
        # 反馈和回复互不依赖，并发执行可以显著缩短单轮等待时间。
        learner_message = Message(role="user", text=payload.learner_message)

        assistant_message = Message(
            role="assistant",
            text=coach_reply.text,
            feedback=feedback.model_dump(),
        )
        updated_session = session.model_copy(
            update={"messages": [*session.messages, learner_message, assistant_message]}
        )
        review = build_session_review(updated_session, feedback)
        return await self.session_repository.save_reply_turn(
            session.id,
            learner_message,
            assistant_message,
            review,
        )

    async def get_review(self, session_id: str):
        """读取会话对应的复盘结果。"""
        return await self.session_repository.get_session_review(session_id)

    async def list_history_sessions(self, user_id: str) -> list[Session]:
        """列出用户全部历史会话。"""
        return await self.session_repository.list_user_sessions(user_id)

    async def list_history_sessions_page(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Session], bool, str | None]:
        """把仓储层游标编码成可通过 API 透传的字符串。"""
        cursor_value = _decode_history_cursor(cursor)
        sessions, has_more, next_cursor_value = await self.session_repository.list_user_sessions_page(
            user_id,
            limit=limit,
            cursor=cursor_value,
        )
        next_cursor = _encode_history_cursor(next_cursor_value) if next_cursor_value else None
        return (sessions, has_more, next_cursor)

    async def list_history_reviews(self, session_ids: list[str]) -> dict[str, SessionReview]:
        """批量读取历史会话对应的复盘内容。"""
        if not session_ids:
            return {}
        return await self.session_repository.list_session_reviews_by_ids(session_ids)

    async def get_history_session_overview(self, session_id: str) -> tuple[Session, SessionReview, int]:
        """并发聚合历史会话头信息、复盘和消息总数。"""
        session, review, total_messages = await asyncio.gather(
            self.get_session_head(session_id),
            self.get_review(session_id),
            self.session_repository.count_session_messages(session_id),
        )
        return (session, review, total_messages)

    async def list_history_session_messages_page(
        self,
        session_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Message], bool, str | None]:
        """分页读取单个会话的历史消息。"""
        return await self.session_repository.list_session_messages_page(
            session_id,
            limit=limit,
            cursor=cursor,
        )

    async def bootstrap_voice_session(self, session_id: str) -> VoiceBootstrapResult:
        """签发语音会话令牌，并记录语音链路已启动。"""
        session = await self.session_repository.get_session(session_id)
        token, expires_in = self.voice_token_issuer.issue_token(
            settings.deepgram_agent_token_ttl_seconds
        )
        bootstrap = VoiceBootstrapResult(
            session_id=session.id,
            deepgram_access_token=token,
            expires_in=expires_in,
            deepgram_ws_url=settings.deepgram_agent_base_url,
            agent_settings=self.voice_settings_builder.build(session),
            session=session,
        )
        await self.session_repository.save_voice_session_fact(
            VoiceSessionFact(
                session_id=session.id,
                status="active",
                transcript_turn_count=len(session.messages),
            )
        )
        await self.session_repository.save_session_event(
            SessionEvent(
                session_id=session.id,
                event_type="voice_bootstrapped",
                stage="voice_active",
                payload={
                    "expires_in": expires_in,
                    "output_sample_rate": settings.deepgram_agent_output_sample_rate,
                },
            )
        )
        return bootstrap

    async def complete_voice_session(self, payload: VoiceCompleteInput) -> VoiceCompleteResult:
        """把语音转写收束成文本会话，并补齐反馈、review 与运行时事件。"""
        session = await self.session_repository.get_session(payload.session_id)
        messages = _build_voice_messages(session, payload)
        updated_session = session.model_copy(
            update={
                "messages": messages,
            }
        )
        last_learner_message = _find_latest_user_content(payload)
        if last_learner_message is None:
            raise AppValidationError("Validation error")
        feedback = await self._review_with_context(
            learner_message=last_learner_message,
            scene=updated_session.scene,
            vocab_candidates=updated_session.vocab_candidates,
        )
        review = build_session_review(updated_session, feedback)
        existing_voice_fact = await self.session_repository.get_latest_voice_session_fact(payload.session_id)
        voice_fact = VoiceSessionFact(
            session_id=payload.session_id,
            status="completed",
            termination_reason=payload.termination_reason,
            transcript_turn_count=len(payload.conversation),
            client_diagnostics=dict(payload.client_diagnostics),
            started_at=(
                existing_voice_fact.started_at
                if existing_voice_fact is not None
                else updated_session.created_at
            ),
            completed_at=review.updated_at,
            updated_at=review.updated_at,
        )
        events = [
            SessionEvent(
                session_id=payload.session_id,
                event_type="voice_finalized",
                stage="review_ready",
                payload={
                    "termination_reason": payload.termination_reason,
                    "conversation_turn_count": len(payload.conversation),
                    "client_diagnostics": dict(payload.client_diagnostics),
                },
                created_at=review.updated_at,
            ),
            SessionEvent(
                session_id=payload.session_id,
                event_type="review_built",
                stage="review_ready",
                payload={"review_title": review.title},
                created_at=review.updated_at,
            ),
        ]
        stored_session, stored_review = await self.session_repository.finalize_voice_session(
            session=updated_session,
            review=review,
            voice_fact=voice_fact,
            events=events,
        )
        return VoiceCompleteResult(session=stored_session, review=stored_review)

    async def _review_with_context(
        self,
        *,
        learner_message: str,
        scene: str,
        vocab_candidates: list[str],
    ):
        """兼容不同版本的反馈 service 签名，稳定透传上下文。"""
        parameters = inspect.signature(self.feedback_engine.review).parameters
        if "vocab_candidates" in parameters:
            return await self.feedback_engine.review(learner_message, scene, vocab_candidates)
        if "labels" in parameters:
            return await self.feedback_engine.review(learner_message, scene, vocab_candidates)
        return await self.feedback_engine.review(learner_message, scene)

    async def _respond_with_context(
        self,
        *,
        scene: str,
        role: str,
        learner_message: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        recent_messages: list[Message],
    ):
        """兼容不同版本的教练 service 签名，优先传递更多上下文。"""
        parameters = inspect.signature(self.coach_engine.respond).parameters
        if "visual_anchors" in parameters and "vocab_candidates" in parameters:
            return await self.coach_engine.respond(
                scene=scene,
                role=role,
                learner_message=learner_message,
                visual_anchors=visual_anchors,
                vocab_candidates=vocab_candidates,
                recent_messages=recent_messages,
            )
        if "visual_anchors" in parameters:
            return await self.coach_engine.respond(
                scene=scene,
                role=role,
                learner_message=learner_message,
                visual_anchors=visual_anchors,
                recent_messages=recent_messages,
            )
        if "labels" in parameters or "recent_messages" in parameters:
            return await self.coach_engine.respond(
                scene=scene,
                role=role,
                learner_message=learner_message,
                labels=visual_anchors,
                recent_messages=recent_messages,
            )
        return await self.coach_engine.respond(scene, role, learner_message)


def _build_voice_messages(session: Session, payload: VoiceCompleteInput) -> list[Message]:
    """把语音转写拼回会话消息流，并去掉与已有消息重复的尾段。"""
    transcript: list[Message] = []
    for index, turn in enumerate(payload.conversation):
        if (
            index == 0
            and turn.role == "assistant"
            and session.messages
            and session.messages[0].role == "assistant"
            and turn.content == session.messages[0].text
        ):
            transcript.append(session.messages[0])
            continue
        transcript.append(
            Message(
                role=turn.role,
                text=turn.content,
            )
        )

    if not session.messages:
        return transcript

    remainder = list(transcript)
    if remainder and _message_signature(remainder[0]) == _message_signature(session.messages[0]):
        remainder = remainder[1:]

    # 语音链路会回传整段 transcript，这里按尾部重叠去重，避免重复入库。
    overlap = _find_tail_overlap(existing=session.messages, incoming=remainder)
    return [*session.messages, *remainder[overlap:]]


def _find_latest_user_content(payload: VoiceCompleteInput) -> str | None:
    """提取最后一条学习者发言，供反馈引擎生成最终复盘。"""
    for turn in reversed(payload.conversation):
        if turn.role == "user":
            return turn.content
    return None


def _find_tail_overlap(*, existing: list[Message], incoming: list[Message]) -> int:
    """寻找旧消息尾部与新 transcript 头部的最大重叠长度。"""
    max_overlap = min(len(existing), len(incoming))
    for size in range(max_overlap, 0, -1):
        existing_tail = existing[-size:]
        incoming_head = incoming[:size]
        if all(
            _message_signature(left) == _message_signature(right)
            for left, right in zip(existing_tail, incoming_head, strict=False)
        ):
            return size
    return 0


def _message_signature(message: Message) -> tuple[str, str]:
    """提取消息去重时使用的稳定签名。"""
    return (message.role, message.text)


def _encode_history_cursor(value: tuple[datetime, str]) -> str:
    """把分页游标编码成带 UTC 时间戳的字符串。"""
    updated_at, session_id = value
    normalized = updated_at.astimezone(timezone.utc)
    return f"{normalized.isoformat()}|{session_id}"


def _decode_history_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    """把 API 透传游标解回仓储层需要的时间戳和会话 ID。"""
    if cursor is None:
        return None
    timestamp, _, session_id = cursor.partition("|")
    if not timestamp or not session_id:
        raise AppValidationError("Validation error")
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise AppValidationError("Validation error") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed, session_id)
