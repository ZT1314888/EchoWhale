import asyncio
import contextlib
import hashlib
import hmac
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from uuid import uuid4

from api.common.enums import MediaUploadStatus
from api.common.exceptions import (
    EchoWhaleError,
    InvalidStateError,
    ModelProviderError,
    NotFoundError,
    SceneAnalysisUnavailableError,
    UnsupportedSceneImageError,
)
from api.common.exceptions import ValidationError as AppValidationError
from api.core.config import settings
from api.db.media_db import MediaLookup, build_media_repository
from api.db.scene_analysis_db import (
    SCENE_ANALYSIS_STATUS_READY,
    SceneAnalysisStore,
    build_scene_analysis_store,
)
from api.db.session_db import SessionRepository, build_session_repository
from api.integrations.deepgram import DeepgramSettingsBuilder, DeepgramTokenIssuer
from api.integrations.storage.r2 import R2StorageService
from api.models.message_model import Message
from api.models.review_model import SessionReview
from api.models.runtime_model import SessionEvent, VoiceSessionFact
from api.models.session_model import Session
from api.modules.coach_engine.service import CoachEngineService
from api.modules.feedback_engine.service import FeedbackEngineService
from api.modules.scene_engine.schema import SceneAnalysisResult, scene_result_from_snapshot
from api.modules.scene_engine.service import SceneEngineService
from api.modules.session_engine.review_builder import build_session_review
from api.modules.session_engine.sample_presets import get_sample_session_preset
from api.modules.session_engine.schema import (
    ReplyInput,
    SceneAnalysisPending,
    StartSessionInput,
    VoiceBootstrapResult,
    VoiceCompleteInput,
    VoiceCompleteResult,
)
from api.tasks.image_analysis import enqueue_scene_analysis

logger = logging.getLogger(__name__)


class SessionEngineAgent:
    def __init__(
        self,
        media_lookup: MediaLookup | None = None,
        session_repository: SessionRepository | None = None,
        read_url_signer: R2StorageService | None = None,
        scene_analysis_store: SceneAnalysisStore | None = None,
        scene_dispatcher: Callable[[str], bool] | None = None,
    ) -> None:
        """装配会话编排依赖，包括媒体、存储、三段 agent 和语音组件。"""
        self.media_lookup = media_lookup or build_media_repository()
        self.session_repository = session_repository or build_session_repository()
        self.read_url_signer = read_url_signer or R2StorageService()
        self.scene_analysis_store = scene_analysis_store or build_scene_analysis_store()
        self.scene_dispatcher = scene_dispatcher or enqueue_scene_analysis
        self.scene_engine = SceneEngineService()
        self.coach_engine = CoachEngineService()
        self.feedback_engine = FeedbackEngineService()
        self.voice_token_issuer = DeepgramTokenIssuer()
        self.voice_settings_builder = DeepgramSettingsBuilder()

    async def start(self, payload: StartSessionInput) -> Session | SceneAnalysisPending:
        """从样例场景或图片分析结果创建一条新会话；缓存未命中且已入队时返回挂起结果。"""
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

        if payload.media_id is None:
            raise AppValidationError("media_id is required to start an image session")
        media = await self.media_lookup.get_media(payload.media_id)
        # 归属校验必须先于上传状态检查、缓存查询与场景分析派发：
        # 跨用户请求一律收敛成 404 防存在性探测，且不得读场景缓存、
        # 不得触发视觉分析——否则会用他人图片泄漏场景描述并转嫁调用成本。
        if media.user_id != payload.user_id:
            raise NotFoundError(f"Media {media.id} not found")
        if media.upload_status != MediaUploadStatus.uploaded:
            raise InvalidStateError(f"Media {media.id} is not uploaded")

        cached_analysis = await self._load_cached_scene_analysis(media.id)
        if cached_analysis is not None:
            analysis = cached_analysis
        elif await self._dispatch_scene_analysis(media.id):
            return SceneAnalysisPending(media_id=media.id)
        else:
            analysis = await self._analyze_scene_media(media)
            await self._store_scene_analysis(media.id, analysis)
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

    async def _load_cached_scene_analysis(self, media_id: str) -> SceneAnalysisResult | None:
        """命中且版本一致的缓存直接复用，省掉重复的下载、质检与视觉调用。"""
        if not settings.scene_analysis_cache_enabled:
            return None
        snapshot = await self.scene_analysis_store.get(media_id)
        if snapshot is None or snapshot.status != SCENE_ANALYSIS_STATUS_READY:
            return None
        if snapshot.prompt_version != settings.scene_analysis_prompt_version:
            return None
        try:
            return scene_result_from_snapshot(snapshot)
        except (TypeError, ValueError) as exc:
            # 缓存行损坏时自愈：放弃命中，走重分析并覆写缓存。
            logger.warning(
                "scene_analysis_cache_snapshot_invalid media_id=%s error=%s", media_id, exc
            )
            return None

    async def _dispatch_scene_analysis(self, media_id: str) -> bool:
        """mock 模式与显式关闭异步时直接内联；入队成功返回 True。

        Redis/RQ 缺席由 dispatcher 吞掉并返回 False（内部已记 warning），
        调用方降级为内联分析，请求不失败。
        """
        if settings.model_runtime_mode.lower() != "live":
            return False
        if not settings.scene_analysis_async_enabled:
            return False
        await self.scene_analysis_store.save_pending(
            media_id, settings.scene_analysis_prompt_version
        )
        queued = await asyncio.to_thread(self.scene_dispatcher, media_id)
        if not queued:
            # 入队失败：留下失败痕迹供状态端点追溯，调用方随即内联重试。
            await self.scene_analysis_store.save_failure(
                media_id,
                settings.scene_analysis_prompt_version,
                error_code=1005,
            )
        return queued

    async def _analyze_scene_media(self, media) -> SceneAnalysisResult:
        signed_read_url, _ = await self.read_url_signer.async_create_signed_read_url(
            media.storage_key,
            expires_in=settings.r2_signed_url_ttl_seconds,
        )
        try:
            return await self.scene_engine.analyze(media.filename, signed_read_url)
        except UnsupportedSceneImageError:
            raise
        except EchoWhaleError as exc:
            raise SceneAnalysisUnavailableError() from exc

    async def _store_scene_analysis(self, media_id: str, analysis: SceneAnalysisResult) -> None:
        """内联路径的分析结果顺手写穿缓存，让下一次 start 直接命中。"""
        if not settings.scene_analysis_cache_enabled:
            return
        await self.scene_analysis_store.save_result(
            media_id,
            settings.scene_analysis_prompt_version,
            scene=analysis.scene,
            role=analysis.role,
            opener=analysis.opener,
            visual_anchors=list(analysis.visual_anchors),
            vocab_candidates=list(analysis.vocab_candidates),
            confidence=analysis.confidence,
        )

    async def get(self, session_id: str) -> Session:
        """读取完整会话。"""
        return await self.session_repository.get_session(session_id)

    async def get_session_head(self, session_id: str) -> Session:
        """只读取会话头部信息，避免历史消息分页场景过载。"""
        return await self.session_repository.get_session_head(session_id)

    async def reply(self, payload: ReplyInput) -> Session:
        """并发生成反馈与教练回复，再把这一轮消息原子化落库。

        读路径只取会话头 + 最近窗口消息，避免每轮全量拉取整个消息历史；
        写后的全量重读保留，作为响应契约的一部分。
        """
        session_head = await self.session_repository.get_session_head(payload.session_id)
        recent_messages = await self.session_repository.list_recent_messages(
            payload.session_id,
            limit=settings.llm_coach_window_size,
        )
        feedback_result, coach_result = await asyncio.gather(
            self.feedback_engine.review(
                payload.learner_message,
                session_head.scene,
                session_head.vocab_candidates,
            ),
            self.coach_engine.respond(
                scene=session_head.scene,
                role=session_head.role,
                learner_message=payload.learner_message,
                visual_anchors=session_head.visual_anchors,
                vocab_candidates=session_head.vocab_candidates,
                recent_messages=recent_messages,
            ),
            return_exceptions=True,
        )
        # 反馈和回复互不依赖，并发执行可以显著缩短单轮等待时间；
        # return_exceptions 确保一侧失败时不再取消另一侧已在计费的调用。
        _log_failed_branch("feedback", feedback_result)
        _log_failed_branch("coach", coach_result)
        feedback, coach_reply = _unwrap_gather_results(feedback_result, coach_result)

        learner_message, assistant_message, review = _build_reply_turn(
            session_head,
            recent_messages,
            learner_text=payload.learner_message,
            coach_text=coach_reply.text,
            feedback=feedback,
        )
        return await self.session_repository.save_reply_turn(
            session_head.id,
            learner_message,
            assistant_message,
            review,
        )

    async def stream_reply(self, payload: ReplyInput) -> AsyncIterator[tuple[str, object]]:
        """流式 reply：先回执 feedback，再逐 token 下发教练回复，全部成功后原子落库。

        语义与 reply() 一致：feedback 与 coach 并发启动，任一分支失败则整轮失败、
        不落任何消息；区别只在 coach 分支从整段调用换成"打开流 + 增量消费"。
        """
        session_head = await self.session_repository.get_session_head(payload.session_id)
        recent_messages = await self.session_repository.list_recent_messages(
            payload.session_id,
            limit=settings.llm_coach_window_size,
        )
        feedback_task = asyncio.create_task(
            self.feedback_engine.review(
                payload.learner_message,
                session_head.scene,
                session_head.vocab_candidates,
            )
        )
        try:
            coach_stream = await self.coach_engine.stream_respond(
                scene=session_head.scene,
                role=session_head.role,
                learner_message=payload.learner_message,
                visual_anchors=session_head.visual_anchors,
                vocab_candidates=session_head.vocab_candidates,
                recent_messages=recent_messages,
            )
        except BaseException:
            # 回复流打不开，这一轮已注定失败；不再等待另一侧已计费的反馈调用。
            feedback_task.cancel()
            with contextlib.suppress(BaseException):
                await feedback_task
            raise

        try:
            feedback = await feedback_task
            yield ("feedback", feedback)

            coach_chunks: list[str] = []
            async for delta in coach_stream.aiter_deltas():
                coach_chunks.append(delta)
                yield ("delta", delta)

            learner_message, assistant_message, review = _build_reply_turn(
                session_head,
                recent_messages,
                learner_text=payload.learner_message,
                coach_text="".join(coach_chunks),
                feedback=feedback,
            )
            session = await self.session_repository.save_reply_turn(
                session_head.id,
                learner_message,
                assistant_message,
                review,
            )
            yield ("session", session)
        finally:
            with contextlib.suppress(Exception):
                await coach_stream.aclose()

    async def get_review(self, session_id: str):
        """读取会话对应的复盘结果。"""
        return await self.session_repository.get_session_review(session_id)

    async def list_history_sessions_page(
        self,
        user_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Session], bool, str | None]:
        """把仓储层游标编码成可通过 API 透传的字符串。"""
        cursor_value = _decode_history_cursor(cursor)
        sessions, has_more, next_cursor_value = (
            await self.session_repository.list_user_sessions_page(
                user_id,
                limit=limit,
                cursor=cursor_value,
            )
        )
        next_cursor = _encode_history_cursor(next_cursor_value) if next_cursor_value else None
        return (sessions, has_more, next_cursor)

    async def list_history_reviews(self, session_ids: list[str]) -> dict[str, SessionReview]:
        """批量读取历史会话对应的复盘内容。"""
        if not session_ids:
            return {}
        return await self.session_repository.list_session_reviews_by_ids(session_ids)

    async def get_history_session_overview(
        self, session_id: str
    ) -> tuple[Session, SessionReview, int]:
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
        token, expires_in = await asyncio.to_thread(
            self.voice_token_issuer.issue_token,
            settings.deepgram_agent_token_ttl_seconds,
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
        feedback = await self.feedback_engine.review(
            last_learner_message,
            updated_session.scene,
            updated_session.vocab_candidates,
        )
        review = build_session_review(updated_session, feedback)
        existing_voice_fact = await self.session_repository.get_latest_voice_session_fact(
            payload.session_id
        )
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


def _build_reply_turn(
    session_head: Session,
    recent_messages: list[Message],
    *,
    learner_text: str,
    coach_text: str,
    feedback: object,
) -> tuple[Message, Message, SessionReview]:
    """组装一轮对话的两条消息与复盘；coach 文本为空按模型失败处理。"""
    coach_text = coach_text.strip()
    if not coach_text:
        raise ModelProviderError("Coach reply was empty")

    learner_message = Message(role="user", text=learner_text)
    assistant_message = Message(
        role="assistant",
        text=coach_text,
        feedback=feedback.model_dump(),
    )
    reviewed_session = session_head.model_copy(
        update={"messages": [*recent_messages, learner_message, assistant_message]}
    )
    review = build_session_review(reviewed_session, feedback)
    return (learner_message, assistant_message, review)


def _log_failed_branch(branch: str, result: object) -> None:
    """记录 gather 中失败分支的异常，避免静默吞掉可观测信息。"""
    if isinstance(result, BaseException):
        logger.warning(
            "session_reply_branch_failed branch=%s error=%s: %s",
            branch,
            type(result).__name__,
            result,
        )


def _unwrap_gather_results(*results: object) -> tuple:
    """从 return_exceptions 的 gather 结果中提取首个异常并统一上抛。"""
    errors = [result for result in results if isinstance(result, BaseException)]
    if not errors:
        return tuple(results)
    # 优先上抛业务异常，保持与全局异常处理器的既有契约一致。
    for error in errors:
        if isinstance(error, EchoWhaleError):
            raise error
    raise errors[0]


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
    """把分页游标编码成带签名防篡改的字符串。"""
    updated_at, session_id = value
    normalized = updated_at.astimezone(UTC)
    payload = f"{normalized.isoformat()}|{session_id}"
    return f"{payload}|{_sign_cursor_payload(payload)}"


def _decode_history_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    """验签并解回仓储层需要的时间戳和会话 ID，防止客户端伪造游标。"""
    if cursor is None:
        return None
    payload, _, signature = cursor.rpartition("|")
    if not payload or not signature:
        raise AppValidationError("Validation error")
    expected_signature = _sign_cursor_payload(payload)
    if not hmac.compare_digest(signature, expected_signature):
        raise AppValidationError("Validation error")
    timestamp, _, session_id = payload.partition("|")
    if not timestamp or not session_id:
        raise AppValidationError("Validation error")
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise AppValidationError("Validation error") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return (parsed, session_id)


def _sign_cursor_payload(payload: str) -> str:
    """用应用密钥给游标内容生成十六进制 HMAC 签名。"""
    return hmac.new(
        settings.auth_jwt_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
