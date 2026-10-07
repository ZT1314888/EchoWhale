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
from api.common.telemetry import TERMINAL_DEGRADED, traced_engine
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
from api.models.learner_profile_model import LearnerProfile
from api.models.message_model import Message
from api.models.review_model import SessionReview
from api.models.runtime_model import SessionEvent, VoiceSessionFact
from api.models.session_model import Session
from api.modules.coach_engine.service import CoachEngineService
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.feedback_engine.service import FeedbackEngineService
from api.modules.scene_engine.schema import SceneAnalysisResult, scene_result_from_snapshot
from api.modules.scene_engine.service import SceneEngineService
from api.modules.session_engine.learner_profile import (
    apply_turn_to_profile,
    build_learner_context_lines,
)
from api.modules.session_engine.review_builder import ReviewCopy, build_session_review
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
        # 永不发起调用；live 失败/超时由 _review_copy_for_turn 统一降级模板复盘。
        self.review_summarizer = ReviewSummarizerAgent()
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

    async def _load_learner_profile(self, user_id: str) -> LearnerProfile | None:
        """PK 点查学员档案；任何失败都降级为静态注入，绝不拖垮回复轮。

        点查是主键单行读（低成本）；失败只记 degraded warning 并返回 None，
        调用方回退 COACH_LEARNER_LEVEL 静态注入与空注入块。
        """
        try:
            return await self.learner_profile_repository.get(user_id)
        except Exception as exc:  # noqa: BLE001 - 档案读失败需降级续轮而非上抛
            logger.warning(
                "learner_profile_load_failed degraded=true user_id=%s error=%s: %s",
                user_id,
                type(exc).__name__,
                exc,
            )
            return None

    async def _learner_context_for_turn(
        self, session_head: Session
    ) -> tuple[str | None, str | None]:
        """渲染本轮的学员注入块与 CEFR 估计；visitor / 无档案 / 读失败回退 (None, None)。

        visitor 会话零查询直接回退：访客身份可轮换、键无界且无清理语义，
        不建档也不读档，避免无意义的点查。
        """
        if not session_head.user_id.startswith("user:"):
            return (None, None)
        profile = await self._load_learner_profile(session_head.user_id)
        if profile is None:
            return (None, None)
        return (build_learner_context_lines(profile), profile.cefr_estimate)

    async def _update_learner_profile_for_turn(
        self,
        session_head: Session,
        feedback: FeedbackResult,
    ) -> None:
        """把单轮反馈信号滚动累计进学员档案（增强分支，独立于消息落库事务）。

        门控：user_id 不以 user: 开头（visitor）直接返回，零日志噪音。
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
            profile = await self.learner_profile_repository.get(user_id)
            profile = apply_turn_to_profile(
                profile,
                user_id=user_id,
                scene=session_head.scene,
                feedback=feedback,
                scene_cap=settings.learner_profile_scene_cap,
                cefr_window=settings.learner_profile_cefr_window,
            )
            await self.learner_profile_repository.upsert(profile)
        except Exception as exc:  # noqa: BLE001 - 档案写失败需降级续轮而非上抛
            logger.warning(
                "learner_profile_update_failed degraded=true user_id=%s error=%s: %s",
                user_id,
                type(exc).__name__,
                exc,
            )

    async def reply(self, payload: ReplyInput) -> Session:
        """并发生成反馈与教练回复，再把这一轮消息原子化落库。

        失败语义分主次：反馈是增值能力，失败时降级为占位反馈，本轮照常返回与落库；
        教练回复是主价值，失败时整轮上抛、不落任何消息。
        读路径只取会话头 + 最近窗口消息，避免每轮全量拉取整个消息历史；
        写后的全量重读保留，作为响应契约的一部分。
        学员档案在会话头后点查一次（低成本 PK 读），注入块同时喂给反馈与
        教练分支；档案更新在消息落库成功之后独立执行（增强分支，可降级）。
        """
        session_head = await self.session_repository.get_session_head(payload.session_id)
        recent_messages = await self.session_repository.list_recent_messages(
            payload.session_id,
            limit=settings.llm_coach_window_size,
        )
        learner_context, learner_cefr = await self._learner_context_for_turn(session_head)
        # 两个分支各自打 engine span（design 2.3 终态映射）：feedback 异常按
        # degraded 记账（降级转换仍由下方 _resolve_feedback 完成），coach 异常按
        # failed 记账（主价值失败整轮上抛）。span 只记账，不改任何返回/异常语义。
        feedback_result, coach_result = await asyncio.gather(
            traced_engine(
                "feedback",
                self.feedback_engine.review(
                    payload.learner_message,
                    session_head.scene,
                    session_head.vocab_candidates,
                    learner_context=learner_context,
                ),
                session_id=session_head.id,
                on_exception=TERMINAL_DEGRADED,
            ),
            traced_engine(
                "coach",
                self.coach_engine.respond(
                    scene=session_head.scene,
                    role=session_head.role,
                    learner_message=payload.learner_message,
                    visual_anchors=session_head.visual_anchors,
                    vocab_candidates=session_head.vocab_candidates,
                    recent_messages=recent_messages,
                    learner_context=learner_context,
                    learner_cefr=learner_cefr,
                ),
                session_id=session_head.id,
            ),
            return_exceptions=True,
        )
        # 反馈和回复互不依赖，并发执行可以显著缩短单轮等待时间；
        # return_exceptions 确保一侧失败时不再取消另一侧已在计费的调用。
        # 先收敛反馈（失败即降级并留 degraded 日志），再检查教练分支：
        # 两侧同时失败时，教练异常原样上抛交全局处理器，反馈失败也已留在日志里。
        feedback_degraded = isinstance(feedback_result, Exception)
        feedback = _resolve_feedback(feedback_result)
        if isinstance(coach_result, BaseException):
            raise coach_result

        # 复盘 LLM 汇总（增强分支）：在教练分支确认成功之后有界等待，
        # 任何失败都降级为 None（模板复盘），不拖垮本轮。
        review_copy = await self._review_copy_for_turn(
            session_head,
            payload.learner_message,
            feedback,
            feedback_degraded=feedback_degraded,
        )
        learner_message, assistant_message, review = _build_reply_turn(
            session_head,
            recent_messages,
            learner_text=payload.learner_message,
            coach_text=coach_result.text,
            feedback=feedback,
            review_copy=review_copy,
        )
        stored_session = await self.session_repository.save_reply_turn(
            session_head.id,
            learner_message,
            assistant_message,
            review,
            review_copy=review_copy,
        )
        # 档案更新在消息落库成功之后（独立事务）：写失败只降级不影响已提交的回复轮。
        await self._update_learner_profile_for_turn(session_head, feedback)
        return stored_session

    async def stream_reply(self, payload: ReplyInput) -> AsyncIterator[tuple[str, object]]:
        """流式 reply：先回执 feedback，再逐 token 下发教练回复，成功后原子落库。

        反馈分支失败时降级为占位反馈继续：事件序 feedback → delta* → session 不变，
        本轮照常落库；教练分支失败（打不开流、中途断流、空输出）仍整轮失败、不落任何消息。
        """
        session_head = await self.session_repository.get_session_head(payload.session_id)
        recent_messages = await self.session_repository.list_recent_messages(
            payload.session_id,
            limit=settings.llm_coach_window_size,
        )
        learner_context, learner_cefr = await self._learner_context_for_turn(session_head)
        # 流式路径同样按 design 2.3 打 engine span；feedback 异常按 degraded 记账
        # （降级转换仍在 try/except 内完成），教练 span 只覆盖"开流"阶段——
        # span 若跨 async generator 的 yield 会把中间态泄漏进消费者上下文，
        # 明确不做，消费耗时由 server span 承载（observability.md 注明）。
        feedback_task = asyncio.create_task(
            traced_engine(
                "feedback",
                self.feedback_engine.review(
                    payload.learner_message,
                    session_head.scene,
                    session_head.vocab_candidates,
                    learner_context=learner_context,
                ),
                session_id=session_head.id,
                on_exception=TERMINAL_DEGRADED,
            )
        )
        try:
            coach_stream = await traced_engine(
                "coach",
                self.coach_engine.stream_respond(
                    scene=session_head.scene,
                    role=session_head.role,
                    learner_message=payload.learner_message,
                    visual_anchors=session_head.visual_anchors,
                    vocab_candidates=session_head.vocab_candidates,
                    recent_messages=recent_messages,
                    learner_context=learner_context,
                    learner_cefr=learner_cefr,
                ),
                session_id=session_head.id,
            )
        except BaseException:
            # 回复流打不开，这一轮已注定失败；不再等待另一侧已计费的反馈调用。
            feedback_task.cancel()
            with contextlib.suppress(BaseException):
                await feedback_task
            raise

        review_task: asyncio.Task[ReviewCopy | None] | None = None
        try:
            # 反馈是增值能力：失败时降级为占位反馈，事件序与落库照常。
            # 只捕获 Exception；CancelledError 等 BaseException 不吞，取消语义保持。
            feedback_degraded = False
            try:
                feedback = await feedback_task
            except Exception as exc:  # noqa: BLE001 - 反馈失败需降级续轮而非上抛
                feedback = _degraded_feedback_with_log(exc)
                feedback_degraded = True
            yield ("feedback", feedback)

            # 复盘与教练 delta 流并行生成（增强分支）：feedback 已降级时不起任务，
            # 对占位反馈做汇总没有意义；mock 模式下任务内部短路，不发起任何调用。
            if not feedback_degraded:
                review_task = asyncio.create_task(
                    self._review_copy_for_turn(
                        session_head,
                        payload.learner_message,
                        feedback,
                        feedback_degraded=False,
                    )
                )

            coach_chunks: list[str] = []
            async for delta in coach_stream.aiter_deltas():
                coach_chunks.append(delta)
                yield ("delta", delta)

            # 复盘收口只有一次：先有界等待任务产出，再同时喂给复盘构建与
            # 落库——重复 collect 会二次等待已取消的任务，CancelledError
            # （BaseException）会绕过降级处理器直接外抛。
            review_copy = await self._collect_review_task(
                session_head.id,
                review_task,
            )
            learner_message, assistant_message, review = _build_reply_turn(
                session_head,
                recent_messages,
                learner_text=payload.learner_message,
                coach_text="".join(coach_chunks),
                feedback=feedback,
                review_copy=review_copy,
            )
            session = await self.session_repository.save_reply_turn(
                session_head.id,
                learner_message,
                assistant_message,
                review,
                review_copy=review_copy,
            )
            # 档案更新在落库成功之后、session 事件下发之前：客户端拿到
            # session 事件时，本轮的档案累积已确定（增强分支失败只降级）。
            await self._update_learner_profile_for_turn(session_head, feedback)
            yield ("session", session)
        finally:
            with contextlib.suppress(Exception):
                await coach_stream.aclose()
            # 失败/提前关闭路径不留悬挂的复盘任务：教练分支中断时任务可能仍在
            # 飞行，显式取消，避免轮次结束后继续消耗配额或发起 LLM 调用。
            if review_task is not None and not review_task.done():
                review_task.cancel()

    async def _review_copy_for_turn(
        self,
        session_head: Session,
        learner_message: str,
        feedback: FeedbackResult,
        *,
        feedback_degraded: bool,
    ) -> ReviewCopy | None:
        """为单轮生成 LLM 复盘文案，外层统一打 engine.review span（design 2.3）。

        终态映射：copy 产出=ok；copy=None（mock 短路 / feedback 已降级 / 降级
        转换）=degraded；异常（含超时取消的 CancelledError）=degraded。span 只
        记账，吞异常与降级转换仍由 _produce_review_copy 既有代码完成。
        """
        return await traced_engine(
            "review",
            self._produce_review_copy(
                session_head,
                learner_message,
                feedback,
                feedback_degraded=feedback_degraded,
            ),
            session_id=session_head.id,
            on_exception=TERMINAL_DEGRADED,
            degraded_result=None,
        )

    async def _produce_review_copy(
        self,
        session_head: Session,
        learner_message: str,
        feedback: FeedbackResult,
        *,
        feedback_degraded: bool,
    ) -> ReviewCopy | None:
        """复盘 LLM 汇总本体（增强分支，Orchestration failure policy）。

        mock 模式短路零调用；feedback 已降级时对占位文案做汇总没有意义；
        live 路径有界等待，超时/失败/未配 provider 一律记 degraded warning 后
        返回 None，绝不拖垮回复轮。只捕获 Exception：CancelledError 照常传播，
        客户端断连语义不变。
        """
        if settings.model_runtime_mode.lower() != "live":
            return None
        if feedback_degraded:
            return None
        try:
            return await asyncio.wait_for(
                self.review_summarizer.summarize(
                    scene=session_head.scene,
                    role=session_head.role,
                    learner_message=learner_message,
                    feedback=feedback,
                ),
                timeout=settings.llm_review_wait_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - 复盘失败需降级续轮而非上抛
            logger.warning(
                "session_review_copy_failed degraded=true session_id=%s error=%s: %s",
                session_head.id,
                type(exc).__name__,
                exc,
            )
            return None

    async def _collect_review_task(
        self,
        session_id: str,
        review_task: asyncio.Task[ReviewCopy | None] | None,
    ) -> ReviewCopy | None:
        """有界等待流式路径的复盘任务；超时/失败取消任务并降级模板复盘。

        shield 保证 wait_for 超时只取消外层等待、内层任务由这里显式取消，
        不会出现双取消；wait_for 抛出的 TimeoutError（3.11+ 即内建
        TimeoutError）是 Exception 子类，与任务失败一并降级。
        """
        if review_task is None:
            return None
        try:
            return await asyncio.wait_for(
                asyncio.shield(review_task),
                timeout=settings.llm_review_wait_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - 复盘失败需降级续轮而非上抛
            review_task.cancel()
            logger.warning(
                "session_review_copy_failed degraded=true session_id=%s error=%s: %s",
                session_id,
                type(exc).__name__,
                exc,
            )
            return None

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
        learner_context, _learner_cefr = await self._learner_context_for_turn(session)
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
        """把语音转写收束成文本会话，并补齐反馈、review 与运行时事件。"""
        session = await self.session_repository.get_session(payload.session_id)
        messages = _build_voice_messages(session, payload)
        # _build_voice_messages 已完成尾段去重：结果 = 既有消息 + 新增尾巴。
        # 仓储只追加新增部分（append-only），既有消息行保持不动，
        # 避免收口期间与文本轮并发时覆盖/删除对方消息（Finding 8）。
        new_messages = messages[len(session.messages) :]
        updated_session = session.model_copy(
            update={
                "messages": messages,
            }
        )
        last_learner_message = _find_latest_user_content(payload)
        if last_learner_message is None:
            raise AppValidationError("Validation error")
        # 反馈是增值能力，与 reply/stream 同款 failure policy：失败降级占位反馈
        # （单一转换点 _degraded_feedback_with_log），收口照常落库与返回。
        # 只捕获 Exception：CancelledError 等取消语义不上吞。
        feedback_degraded = False
        try:
            feedback = await self.feedback_engine.review(
                last_learner_message,
                updated_session.scene,
                updated_session.vocab_candidates,
            )
        except Exception as exc:  # noqa: BLE001 - 反馈失败需降级续轮而非上抛
            feedback = _degraded_feedback_with_log(exc)
            feedback_degraded = True
        # 反馈已降级时复盘直接走 None 短路（对占位文案做汇总没有意义）；
        # 正常反馈路径失败/超时降级模板复盘（copy=None）。
        review_copy = await self._review_copy_for_turn(
            updated_session,
            last_learner_message,
            feedback,
            feedback_degraded=feedback_degraded,
        )
        # LLM 展示名在复盘产出后并入收口快照（design 2.2）：review_copy=None
        # （mock/复盘降级）时沿用 get_session 读出的既有列值，不回闪。
        if review_copy is not None:
            updated_session = updated_session.model_copy(
                update={
                    "llm_scene_title": review_copy.scene_title,
                    "llm_role_label": review_copy.role_label,
                }
            )
        review = build_session_review(updated_session, feedback, copy=review_copy)
        existing_voice_fact = await self.session_repository.get_latest_voice_session_fact(
            payload.session_id
        )
        voice_fact = VoiceSessionFact(
            session_id=payload.session_id,
            status="completed",
            termination_reason=payload.termination_reason,
            transcript_turn_count=len(payload.conversation),
            # 收口只置状态不改代数：token_generation 必须回带既有值，否则
            # upsert 清零会让 re-bootstrap 的代数从 1 重来、旧令牌重新"复活"
            # （审计 F12 的生命周期绑定语义）。
            token_generation=(
                existing_voice_fact.token_generation if existing_voice_fact is not None else 0
            ),
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
            new_messages=new_messages,
            review=review,
            voice_fact=voice_fact,
            events=events,
        )
        # 档案更新在语音收口成功之后（独立事务）：写失败只降级，不影响已提交的会话。
        await self._update_learner_profile_for_turn(updated_session, feedback)
        return VoiceCompleteResult(session=stored_session, review=stored_review)


def _build_reply_turn(
    session_head: Session,
    recent_messages: list[Message],
    *,
    learner_text: str,
    coach_text: str,
    feedback: FeedbackResult,
    review_copy: ReviewCopy | None = None,
) -> tuple[Message, Message, SessionReview]:
    """组装一轮对话的两条消息与复盘；coach 文本为空按模型失败处理。

    输出硬顶（Finding 11）：超长模型输出在 strip 与空判定之后截断，
    防止失控输出无限撑大 Text 列与响应体；截断是防滥用硬顶而非优雅降级，
    留 coach_reply_truncated warning 供观测。整包与流式路径共用本函数。
    """
    coach_text = coach_text.strip()
    if not coach_text:
        raise ModelProviderError("Coach reply was empty")

    max_chars = settings.llm_coach_output_max_chars
    if len(coach_text) > max_chars:
        logger.warning(
            "coach_reply_truncated session_id=%s length=%s max_chars=%s",
            session_head.id,
            len(coach_text),
            max_chars,
        )
        coach_text = coach_text[:max_chars]

    learner_message = Message(role="user", text=learner_text)
    assistant_message = Message(
        role="assistant",
        text=coach_text,
        feedback=feedback.model_dump(),
    )
    reviewed_session = session_head.model_copy(
        update={"messages": [*recent_messages, learner_message, assistant_message]}
    )
    review = build_session_review(reviewed_session, feedback, copy=review_copy)
    return (learner_message, assistant_message, review)


def _degraded_feedback() -> FeedbackResult:
    """构造反馈降级占位结果。

    每次新建实例而非共享单例，避免调用方意外改动可变字段互相影响；
    文案诚实标注本轮失败并预告下一轮恢复，前端按普通反馈卡片渲染即可。
    """
    return FeedbackResult(
        grammar="本轮反馈生成失败，请继续对话；下一轮反馈会照常返回。",
        more_natural="（本轮没有更自然表达建议）",
        useful_words=[],
    )


def _degraded_feedback_with_log(exc: Exception) -> FeedbackResult:
    """反馈分支失败的单一降级转换点：记 degraded warning 后返回占位反馈。

    沿用 session_reply_branch_failed 事件名并补充 degraded=true，
    运维可凭该标记区分"降级成功"与"正常生成"。
    """
    logger.warning(
        "session_reply_branch_failed branch=feedback degraded=true error=%s: %s",
        type(exc).__name__,
        exc,
    )
    return _degraded_feedback()


def _resolve_feedback(result: object) -> FeedbackResult:
    """把 gather 的 return_exceptions 结果收敛成 FeedbackResult。

    成功原样返回；Exception 降级为占位反馈让本轮继续；
    CancelledError 等 BaseException 原样上抛，不吞取消语义。
    """
    if isinstance(result, Exception):
        return _degraded_feedback_with_log(result)
    if isinstance(result, BaseException):
        raise result
    return result


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
