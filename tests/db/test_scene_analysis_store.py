"""scene_analyses 仓储直测：真仓储 + 方言无关引擎（tests/support/engine.py），防止 fake 盲区。"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from api.common.enums import MediaUploadStatus
from api.db.database import create_all_tables_async, create_async_session_factory
from api.db.media_db import MediaRecord, SqlAlchemyMediaRepository
from api.db.scene_analysis_db import (
    SCENE_ANALYSIS_STATUS_FAILED,
    SCENE_ANALYSIS_STATUS_PENDING,
    SCENE_ANALYSIS_STATUS_READY,
    SqlAlchemySceneAnalysisStore,
    build_scene_analysis_store,
)
from api.models.media_model import Media
from tests.support.dialect import enforce_foreign_keys


def _media(media_id: str = "med_cache") -> Media:
    return Media(
        id=media_id,
        user_id="user:learner",
        filename="coffee-shop.png",
        content_type="image/png",
        file_size=1024,
        storage_key=f"media/user:learner/{media_id}.png",
        upload_status=MediaUploadStatus.uploaded,
    )


def _enable_sqlite_foreign_keys(engine) -> None:
    """方言感知 FK 强制：SQLite 装 PRAGMA，PG 天生强制（复用 dialect helper）。"""
    enforce_foreign_keys(engine)


async def _save_media_parent(engine) -> None:
    """scene_analyses.media_id 对 media 有 FK（PG 真实强制）：store 用例先落父行。"""
    await SqlAlchemyMediaRepository(create_async_session_factory(engine)).save_media(_media())


@pytest.mark.anyio
async def test_store_round_trip_pending_ready_and_failure(dialect_async_engine) -> None:
    engine = dialect_async_engine
    await create_all_tables_async(engine)
    store = SqlAlchemySceneAnalysisStore(create_async_session_factory(engine))
    await _save_media_parent(engine)

    assert await store.get("med_missing") is None

    await store.save_pending("med_cache", "v1")
    pending = await store.get("med_cache")
    assert pending is not None
    assert pending.status == SCENE_ANALYSIS_STATUS_PENDING
    assert pending.prompt_version == "v1"

    await store.save_result(
        "med_cache",
        "v1",
        scene="coffee_shop",
        role="barista",
        opener="Hi there!",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        confidence=0.9,
    )
    ready = await store.get("med_cache")
    assert ready is not None
    assert ready.status == SCENE_ANALYSIS_STATUS_READY
    assert ready.scene == "coffee_shop"
    assert ready.role == "barista"
    assert ready.opener == "Hi there!"
    assert ready.visual_anchors == ["counter"]
    assert ready.vocab_candidates == ["latte"]
    assert ready.confidence == pytest.approx(0.9)
    assert ready.error_code is None

    await store.save_failure("med_cache", "v1", error_code=1005)
    failed = await store.get("med_cache")
    assert failed is not None
    assert failed.status == SCENE_ANALYSIS_STATUS_FAILED
    assert failed.error_code == 1005
    # 失败覆写后旧结果字段被清空，避免状态端点输出矛盾的载荷。
    assert failed.scene is None

    await store.reset()
    assert await store.get("med_cache") is None
    await engine.dispose()


@pytest.mark.anyio
async def test_store_upsert_keeps_single_row_per_media(dialect_async_engine) -> None:
    engine = dialect_async_engine
    await create_all_tables_async(engine)
    store = SqlAlchemySceneAnalysisStore(create_async_session_factory(engine))
    await _save_media_parent(engine)

    await store.save_pending("med_cache", "v1")
    await store.save_result(
        "med_cache",
        "v2",
        scene="travel",
        role="local",
        opener="Where to?",
        visual_anchors=["sign"],
        vocab_candidates=["ticket"],
        confidence=0.8,
    )
    await store.save_result(
        "med_cache",
        "v2",
        scene="travel",
        role="local",
        opener="Where to?",
        visual_anchors=["sign"],
        vocab_candidates=["ticket"],
        confidence=0.8,
    )

    from sqlalchemy import func, select

    async with create_async_session_factory(engine)() as db_session:
        total = await db_session.scalar(
            select(func.count()).select_from(
                __import__(
                    "api.db.scene_analysis_db", fromlist=["SceneAnalysisRecord"]
                ).SceneAnalysisRecord
            )
        )
    assert total == 1
    latest = await store.get("med_cache")
    assert latest is not None
    assert latest.prompt_version == "v2"
    await engine.dispose()


@pytest.mark.anyio
async def test_store_rows_cascade_with_media_delete(dialect_async_engine) -> None:
    engine = dialect_async_engine
    _enable_sqlite_foreign_keys(engine)
    await create_all_tables_async(engine)
    session_factory = create_async_session_factory(engine)

    await SqlAlchemyMediaRepository(session_factory).save_media(_media())
    store = SqlAlchemySceneAnalysisStore(session_factory)
    await store.save_result(
        "med_cache",
        "v1",
        scene="office",
        role="colleague",
        opener="Hello!",
        visual_anchors=["desk"],
        vocab_candidates=["standup"],
        confidence=0.77,
    )
    assert await store.get("med_cache") is not None

    async with session_factory() as db_session:
        record = await db_session.get(MediaRecord, "med_cache")
        assert record is not None
        await db_session.delete(record)
        await db_session.commit()

    assert await store.get("med_cache") is None
    await engine.dispose()


@pytest.mark.anyio
async def test_store_snapshot_carries_updated_at(dialect_async_engine) -> None:
    engine = dialect_async_engine
    await create_all_tables_async(engine)
    store = build_scene_analysis_store(create_async_session_factory(engine))
    await _save_media_parent(engine)

    before = datetime.now(UTC)
    await asyncio.sleep(0)
    await store.save_pending("med_cache", "v1")
    snapshot = await store.get("med_cache")
    assert snapshot is not None
    assert snapshot.updated_at is not None
    # 时区回显方言差异显式分支：PG timestamptz 回读带 tzinfo（直接与 aware 的
    # before 比大小），SQLite 回读 naive（剥掉 before 的 tzinfo 再比）。
    if snapshot.updated_at.tzinfo is not None:
        assert snapshot.updated_at >= before
    else:
        assert snapshot.updated_at >= before.replace(tzinfo=None)
    await engine.dispose()
