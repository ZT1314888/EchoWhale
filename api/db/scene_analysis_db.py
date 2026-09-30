"""scene_analyses 表：按 media_id 缓存场景分析结果，支撑 start() 的缓存命中与异步回填。

一张 media 只保留一行（媒体主键即缓存主键）：
- status=pending 表示已入队等待 worker 分析；
- status=ready 携带完整分析载荷；
- status=failed 记录最近一次失败码，允许重新入队覆写。
prompt_version 随提示词演进，旧版本行自动视为未命中。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from api.db.database import AsyncSessionFactory, Base, get_async_session_factory


SCENE_ANALYSIS_STATUS_PENDING = "pending"
SCENE_ANALYSIS_STATUS_READY = "ready"
SCENE_ANALYSIS_STATUS_FAILED = "failed"


@dataclass(slots=True)
class SceneAnalysisSnapshot:
    """scene_analyses 行的内存快照，db 层不依赖上层 schema。"""

    media_id: str
    status: str
    prompt_version: str
    scene: str | None = None
    role: str | None = None
    opener: str | None = None
    visual_anchors: list[str] = field(default_factory=list)
    vocab_candidates: list[str] = field(default_factory=list)
    confidence: float | None = None
    error_code: int | None = None
    updated_at: datetime | None = None


class SceneAnalysisStore(Protocol):
    async def get(self, media_id: str) -> SceneAnalysisSnapshot | None: ...

    async def save_pending(self, media_id: str, prompt_version: str) -> None: ...

    async def save_result(
        self,
        media_id: str,
        prompt_version: str,
        *,
        scene: str,
        role: str,
        opener: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        confidence: float,
    ) -> None: ...

    async def save_failure(
        self,
        media_id: str,
        prompt_version: str,
        *,
        error_code: int,
    ) -> None: ...

    async def reset(self) -> None: ...


class SceneAnalysisRecord(Base):
    __tablename__ = "scene_analyses"

    media_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("media.id", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(16), index=True)
    prompt_version: Mapped[str] = mapped_column(String(32))
    scene: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    opener: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_anchors: Mapped[list[str]] = mapped_column(JSON, default=list)
    vocab_candidates: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SqlAlchemySceneAnalysisStore:
    def __init__(self, session_factory: AsyncSessionFactory | None = None) -> None:
        self._session_factory = session_factory or get_async_session_factory()

    async def get(self, media_id: str) -> SceneAnalysisSnapshot | None:
        async with self._session_factory() as db_session:
            record = await db_session.get(SceneAnalysisRecord, media_id)
            if record is None:
                return None
            return _to_snapshot(record)

    async def save_pending(self, media_id: str, prompt_version: str) -> None:
        await self._upsert(
            media_id,
            prompt_version,
            status=SCENE_ANALYSIS_STATUS_PENDING,
        )

    async def save_result(
        self,
        media_id: str,
        prompt_version: str,
        *,
        scene: str,
        role: str,
        opener: str,
        visual_anchors: list[str],
        vocab_candidates: list[str],
        confidence: float,
    ) -> None:
        await self._upsert(
            media_id,
            prompt_version,
            status=SCENE_ANALYSIS_STATUS_READY,
            scene=scene,
            role=role,
            opener=opener,
            visual_anchors=list(visual_anchors),
            vocab_candidates=list(vocab_candidates),
            confidence=float(confidence),
        )

    async def save_failure(
        self,
        media_id: str,
        prompt_version: str,
        *,
        error_code: int,
    ) -> None:
        await self._upsert(
            media_id,
            prompt_version,
            status=SCENE_ANALYSIS_STATUS_FAILED,
            error_code=int(error_code),
        )

    async def reset(self) -> None:
        async with self._session_factory() as db_session:
            await db_session.execute(delete(SceneAnalysisRecord))
            await db_session.commit()

    async def _upsert(
        self,
        media_id: str,
        prompt_version: str,
        *,
        status: str,
        scene: str | None = None,
        role: str | None = None,
        opener: str | None = None,
        visual_anchors: list[str] | None = None,
        vocab_candidates: list[str] | None = None,
        confidence: float | None = None,
        error_code: int | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with self._session_factory() as db_session:
            record = await db_session.get(SceneAnalysisRecord, media_id)
            if record is None:
                record = SceneAnalysisRecord(media_id=media_id, created_at=now)
                db_session.add(record)
            record.status = status
            record.prompt_version = prompt_version
            record.scene = scene
            record.role = role
            record.opener = opener
            record.visual_anchors = list(visual_anchors or [])
            record.vocab_candidates = list(vocab_candidates or [])
            record.confidence = confidence
            record.error_code = error_code
            record.updated_at = now
            await db_session.commit()


def _to_snapshot(record: SceneAnalysisRecord) -> SceneAnalysisSnapshot:
    return SceneAnalysisSnapshot(
        media_id=record.media_id,
        status=record.status,
        prompt_version=record.prompt_version,
        scene=record.scene,
        role=record.role,
        opener=record.opener,
        visual_anchors=list(record.visual_anchors or []),
        vocab_candidates=list(record.vocab_candidates or []),
        confidence=record.confidence,
        error_code=record.error_code,
        updated_at=record.updated_at,
    )


def build_scene_analysis_store(
    session_factory: AsyncSessionFactory | None = None,
) -> SceneAnalysisStore:
    return SqlAlchemySceneAnalysisStore(session_factory)
