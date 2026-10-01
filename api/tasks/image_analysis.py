"""场景分析的 RQ 任务与入队入口。

start() 在缓存未命中且启用异步时调用 enqueue_scene_analysis；worker 消费
run_scene_analysis_task 重签 R2 读 URL、跑完整分析链路并回写缓存。
Redis/RQ 缺席属于可预期降级：enqueue 捕获后返回 False，调用方内联重试。
"""

from __future__ import annotations

import asyncio
import logging

from api.common.exceptions import ConfigurationError, EchoWhaleError, UnsupportedSceneImageError
from api.core.config import settings
from api.db.database import create_async_database_engine, create_async_session_factory
from api.db.media_db import build_media_repository
from api.db.scene_analysis_db import build_scene_analysis_store
from api.integrations.queue.redis import RedisQueue
from api.integrations.storage.r2 import R2StorageService
from api.modules.scene_engine.service import SceneEngineService

logger = logging.getLogger(__name__)

SCENE_ANALYSIS_TASK = "api.tasks.image_analysis.run_scene_analysis_task"
SCENE_ANALYSIS_FAILURE_GENERIC = 1005
SCENE_ANALYSIS_FAILURE_UNSUPPORTED = 1007


def enqueue_scene_analysis(media_id: str) -> bool:
    """把场景分析投递到 RQ；队列不可用返回 False（调用方降级为内联分析）。"""
    try:
        queue = RedisQueue(queue_name=settings.scene_analysis_queue_name)
        queue.enqueue(SCENE_ANALYSIS_TASK, {"media_id": media_id})
    except (ConfigurationError, EchoWhaleError) as exc:
        # QueuePublishError 是 EchoWhaleError 子类；Redis 连接失败同属预期降级。
        logger.warning(
            "scene_analysis_enqueue_failed media_id=%s error=%s: %s",
            media_id,
            type(exc).__name__,
            exc,
        )
        return False
    return True


def run_scene_analysis_task(*, media_id: str) -> dict[str, str]:
    """RQ worker 同步入口：任务自建事件循环与数据库引擎，跑完即释放。"""
    return asyncio.run(_analyze_and_store(media_id))


async def _analyze_and_store(media_id: str) -> dict[str, str]:
    engine = create_async_database_engine(settings.database_url)
    try:
        session_factory = create_async_session_factory(engine)
        media_repository = build_media_repository(session_factory)
        store = build_scene_analysis_store(session_factory)
        prompt_version = settings.scene_analysis_prompt_version

        media = await media_repository.get_media(media_id)
        signer = R2StorageService()
        signed_url, _ = await signer.async_create_signed_read_url(
            media.storage_key,
            expires_in=settings.r2_signed_url_ttl_seconds,
        )
        try:
            result = await SceneEngineService().analyze(media.filename, signed_url)
        except UnsupportedSceneImageError:
            # 业务性不可用图：直接记失败，不消耗 RQ 重试预算。
            await store.save_failure(
                media_id,
                prompt_version,
                error_code=SCENE_ANALYSIS_FAILURE_UNSUPPORTED,
            )
            return {"media_id": media_id, "status": "failed"}
        except EchoWhaleError:
            await store.save_failure(
                media_id,
                prompt_version,
                error_code=SCENE_ANALYSIS_FAILURE_GENERIC,
            )
            raise
        except Exception:
            logger.exception("scene_analysis_task_crashed media_id=%s", media_id)
            await store.save_failure(
                media_id,
                prompt_version,
                error_code=SCENE_ANALYSIS_FAILURE_GENERIC,
            )
            raise

        await store.save_result(
            media_id,
            prompt_version,
            scene=result.scene,
            role=result.role,
            opener=result.opener,
            visual_anchors=list(result.visual_anchors),
            vocab_candidates=list(result.vocab_candidates),
            confidence=result.confidence,
        )
        return {"media_id": media_id, "status": "ready"}
    finally:
        await engine.dispose()
