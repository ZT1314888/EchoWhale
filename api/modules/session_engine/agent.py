"""会话编排门面（多 Agent 升级 P0 · 拆分后形态）。

P0 起，`SessionEngineAgent` 是**门面**：对外契约（构造参数、公开方法签名、
返回/异常语义、OTel span 树）与拆分前逐字节一致；reply / 流式 / 语音收口的
编排水务迁入 `api/modules/orchestration/`（协议 + 注册表 + 失败策略 + 流程
模块），编排器按角色协议传参、门面在调用时解析引擎（晚绑定，测试可在构造后
替换引擎）。场景启动、语音 bootstrap 与历史游标属领域水务，留在本模块。
拆分映射见 docs/proposals/multi_agent_upgrade/02_target_architecture.md §3.3。
"""

import asyncio
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
    NotFoundError,
    SceneAnalysisUnavailableError,
    UnsupportedSceneImageError,
)
from api.common.exceptions import ValidationError as AppValidationError
from api.common.telemetry import traced_engine
from api.core.config import settings
from api.db.learner_profile_db import (
    LearnerProfileRepository,
    build_learner_profile_repository,
)
from api.db.media_db import MediaLookup, build_media_repository
from api.db.scene_analysis_db import (
    SCENE_ANALYSIS_STATUS_READY,
    SceneAnalysisStore,
    build_scene_analysis_store,
)
from api.db.session_db import SessionRepository, build_session_repository
from api.integrations.deepgram import (
    DeepgramSettingsBuilder,
    DeepgramThinkProxyTokenCodec,
    DeepgramTokenIssuer,
    ThinkProxyTokenIssuer,
    build_deepgram_think_proxy_url,
)
from api.integrations.storage.r2 import R2StorageService
from api.models.message_model import Message
from api.models.review_model import SessionReview
from api.models.runtime_model import SessionEvent, VoiceSessionFact
from api.models.session_model import Session
from api.modules.coach_engine.service import CoachEngineService
from api.modules.feedback_engine.service import FeedbackEngineService
from api.modules.orchestration import (
    AgentDescriptor,
    AgentRegistry,
    LearnerProfileBranch,
    run_reply_turn,
    run_voice_closeout,
    stream_reply_turn,
)
from api.modules.scene_engine.schema import SceneAnalysisResult, scene_result_from_snapshot
from api.modules.scene_engine.service import SceneEngineService
from api.modules.session_engine.review_summarizer import ReviewSummarizerAgent
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
        learner_profile_repository: LearnerProfileRepository | None = None,
        voice_think_token_issuer: ThinkProxyTokenIssuer | None = None,
    ) -> None:
        """装配会话编排依赖，包括媒体、存储、三段 agent 和语音组件。"""
        self.media_lookup = media_lookup or build_media_repository()
        self.session_repository = session_repository or build_session_repository()
        self.read_url_signer = read_url_signer or R2StorageService()
        self.scene_analysis_store = scene_analysis_store or build_scene_analysis_store()
        self.scene_dispatcher = scene_dispatcher or enqueue_scene_analysis
        # 学员档案仓储（增强状态）：读写失败只降级，绝不拖垮回复轮；
        # visitor 会话在编排层前缀门控排除，不产生任何档案读写。
        self.learner_profile_repository = (
            learner_profile_repository or build_learner_profile_repository()
        )
        self.scene_engine = SceneEngineService()
        self.coach_engine = CoachEngineService()
        self.feedback_engine = FeedbackEngineService()
        # LLM 复盘是增强分支（审计 Finding 20）：mock 模式下编排层短路、
        # 永不发起调用；live 失败/超时由 review_branch 统一降级模板复盘。
        self.review_summarizer = ReviewSummarizerAgent()
        # 学员档案增强分支（Memory Manager 的 P0 形态）：读=注入块渲染，
        # 写=单轮滚动累计；仓储经构造注入，读写失败独立降级。
        self.profile_branch = LearnerProfileBranch(self.learner_profile_repository)
        # Agent 协作层（P0）：主链路依赖在调用时解析（晚绑定，引擎可被测试
        # 替换）；注册表登记三个角色的描述符，P1/P2 新增 agent 实现
        # EnhancementAgent 后在此登记，新增全程不改编排器主干
        # （02_target_architecture.md §3.4 P0 用户故事）。
        self.agent_registry = AgentRegistry()
        self.agent_registry.register(
            AgentDescriptor(
                name="conversation_coach",
                role="角色化英文回复，i+1 难度，流式",
                failure_policy="整轮失败不落库，用户看到错误卡片重试",
                model_tier="大模型精算（TEXT_PRIMARY 流式，300 token 预算）",
            ),
            self.coach_engine,
        )
        self.agent_registry.register(
            AgentDescriptor(
                name="feedback_coach",
                role="Grammar / More Natural / Useful Words + 9 类错误归类 + CEFR 观测",
                failure_policy="降级占位反馈，本轮照常返回落库",
                model_tier="中档模型高频（JSON mode，400 token 预算）",
            ),
            self.feedback_engine,
        )
        self.agent_registry.register(
            AgentDescriptor(
                name="review_summarizer",
                role="单轮中文复盘文案",
                failure_policy="mock 短路 / 超时降级模板复盘",
                model_tier="小模型高频（300 token 预算，5s 有界）",
            ),
            self.review_summarizer,
        )
        self.voice_token_issuer = DeepgramTokenIssuer()
        # think 代理令牌签发器（审计 F12 Better fix）：bootstrap 时按会话代数
        # 签发并内嵌进 agent_settings.think.endpoint，代理侧校验代数一致性。
        self.voice_think_token_issuer = voice_think_token_issuer or DeepgramThinkProxyTokenCodec()
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
            # 内联场景分析打 engine.scene span：成功 ok，失败 failed（无降级路径，
            # SceneAnalysisUnavailableError / UnsupportedSceneImageError 整轮上抛）。
            analysis = await traced_engine("scene", self._analyze_scene_media(media))
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
        """并发生成反馈与教练回复并原子落库；编排水务见 orchestration.reply_flow。

        失败语义（由协作层承载，签名/异常与拆分前一致）：反馈失败降级占位，
        本轮照常返回与落库；教练失败整轮上抛、不落任何消息。
        """
        return await run_reply_turn(
            session_repository=self.session_repository,
            feedback_agent=self.feedback_engine,
            coach_agent=self.coach_engine,
            review_agent=self.review_summarizer,
            profile_branch=self.profile_branch,
            payload=payload,
        )

    async def stream_reply(self, payload: ReplyInput) -> AsyncIterator[tuple[str, object]]:
        """流式 reply（SSE：feedback → delta* → session）；编排见 orchestration.reply_flow。

        反馈失败降级占位继续（事件序不变、照常落库）；教练失败整轮失败不落库。
        """
        async for event in stream_reply_turn(
            session_repository=self.session_repository,
            feedback_agent=self.feedback_engine,
            coach_agent=self.coach_engine,
            review_agent=self.review_summarizer,
            profile_branch=self.profile_branch,
            payload=payload,
        ):
            yield event

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
        """签发语音会话令牌，并记录语音链路已启动。

        学员档案在此处点查一次并渲染进 agent think prompt；语音收口路径
        不构建提示词，只做档案更新。
        """
        session = await self.session_repository.get_session(session_id)
        learner_context, _learner_cefr = await self.profile_branch.context_for_turn(session)
        # 代数绑定（审计 F12 Better fix）：每次 bootstrap 递增 voice_session_facts
        # 的 token_generation，think 代理令牌携带该代数——voice/complete（转
        # completed）或再次 bootstrap（代数 +1）都会令先前签发的未过期令牌
        # 在代理校验链上失效，把可复用 bearer 的滥用窗口收敛到单次活跃会话内。
        existing_fact = await self.session_repository.get_latest_voice_session_fact(session_id)
        generation = (existing_fact.token_generation if existing_fact else 0) + 1
        token, expires_in = await asyncio.to_thread(
            self.voice_token_issuer.issue_token,
            settings.deepgram_agent_token_ttl_seconds,
        )
        # 仅当代理公网地址已配置才签发 think 令牌并内嵌 endpoint（Deepgram
        # BYO LLM 形态）；未配置时保持原生 open_ai provider 形态不变，bootstrap
        # 响应与历史版本逐字节一致。
        think_proxy_endpoint: dict[str, object] | None = None
        if settings.deepgram_agent_think_proxy_public_base_url.strip():
            think_token = await asyncio.to_thread(
                self.voice_think_token_issuer.issue,
                session.id,
                generation=generation,
            )
            think_proxy_endpoint = {
                "url": build_deepgram_think_proxy_url(),
                "headers": {"Authorization": f"Bearer {think_token}"},
            }
        bootstrap = VoiceBootstrapResult(
            session_id=session.id,
            deepgram_access_token=token,
            expires_in=expires_in,
            deepgram_ws_url=settings.deepgram_agent_base_url,
            agent_settings=self.voice_settings_builder.build(
                session,
                learner_context=learner_context,
                think_proxy_endpoint=think_proxy_endpoint,
            ),
            session=session,
        )
        await self.session_repository.save_voice_session_fact(
            VoiceSessionFact(
                session_id=session.id,
                status="active",
                transcript_turn_count=len(session.messages),
                token_generation=generation,
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
        """把语音转写收束成文本会话；编排水务见 orchestration.voice_flow。

        失败语义（由协作层承载，签名/异常与拆分前一致）：反馈失败降级占位、
        复盘失败降级模板复盘，收口照常落库；尾段去重与代数不变语义不变。
        """
        return await run_voice_closeout(
            session_repository=self.session_repository,
            feedback_agent=self.feedback_engine,
            review_agent=self.review_summarizer,
            profile_branch=self.profile_branch,
            payload=payload,
        )


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
