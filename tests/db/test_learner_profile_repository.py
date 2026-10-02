"""user_learning_profiles 仓储直测：真仓储 + aiosqlite，防止 fake 盲区。"""

from __future__ import annotations

import pytest

from api.db.database import (
    create_all_tables_async,
    create_async_database_engine,
    create_async_session_factory,
)
from api.db.learner_profile_db import (
    SqlAlchemyLearnerProfileRepository,
    build_learner_profile_repository,
)
from api.models.learner_profile_model import LearnerProfile


def _profile(user_id: str = "user:learner", **overrides) -> LearnerProfile:
    fields: dict = {
        "user_id": user_id,
        "cefr_estimate": "B1",
        "error_type_counts": {"tense": 2, "article": 1},
        "scene_counts": {"office": 1, "coffee_shop": 3},
        "cefr_history": ["A2", "B1"],
        "practiced_turn_count": 3,
    }
    fields.update(overrides)
    return LearnerProfile(**fields)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def engine_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'profiles.db'}"


@pytest.mark.anyio
async def test_repository_first_read_returns_none_and_upsert_round_trips(engine_url) -> None:
    engine = create_async_database_engine(engine_url)
    await create_all_tables_async(engine)
    repository = SqlAlchemyLearnerProfileRepository(create_async_session_factory(engine))

    # 首访用户：PK 点查无行 → None（编排侧回退静态注入）。
    assert await repository.get("user:learner") is None

    await repository.upsert(_profile())
    loaded = await repository.get("user:learner")

    assert loaded is not None
    assert loaded.user_id == "user:learner"
    assert loaded.cefr_estimate == "B1"
    assert loaded.error_type_counts == {"tense": 2, "article": 1}
    # 场景 JSON 保持插入序 = 近期序（渲染与淘汰数学依赖该顺序）。
    assert loaded.scene_counts == {"office": 1, "coffee_shop": 3}
    assert list(loaded.scene_counts) == ["office", "coffee_shop"]
    assert loaded.cefr_history == ["A2", "B1"]
    assert loaded.practiced_turn_count == 3
    await engine.dispose()


@pytest.mark.anyio
async def test_repository_second_upsert_overwrites_single_row(engine_url) -> None:
    engine = create_async_database_engine(engine_url)
    await create_all_tables_async(engine)
    repository = build_learner_profile_repository(create_async_session_factory(engine))

    await repository.upsert(_profile())
    first = await repository.get("user:learner")
    assert first is not None

    updated = _profile(
        cefr_estimate="B2",
        error_type_counts={"tense": 3, "word_choice": 1},
        scene_counts={"coffee_shop": 4},
        cefr_history=["A2", "B1", "B2"],
        practiced_turn_count=4,
    )
    await repository.upsert(updated)

    from sqlalchemy import func, select

    from api.db.learner_profile_db import UserLearningProfileRecord

    async with create_async_session_factory(engine)() as db_session:
        total = await db_session.scalar(select(func.count()).select_from(UserLearningProfileRecord))
    assert total == 1

    reloaded = await repository.get("user:learner")
    assert reloaded is not None
    assert reloaded.cefr_estimate == "B2"
    assert reloaded.error_type_counts == {"tense": 3, "word_choice": 1}
    assert reloaded.scene_counts == {"coffee_shop": 4}
    assert reloaded.cefr_history == ["A2", "B1", "B2"]
    assert reloaded.practiced_turn_count == 4
    # created_at 保留首写时间语义：覆盖写只刷新 updated_at。
    assert reloaded.created_at == first.created_at
    await engine.dispose()


@pytest.mark.anyio
async def test_repository_upsert_returns_domain_model_with_timestamps(engine_url) -> None:
    engine = create_async_database_engine(engine_url)
    await create_all_tables_async(engine)
    repository = build_learner_profile_repository(create_async_session_factory(engine))

    stored = await repository.upsert(_profile())

    assert isinstance(stored, LearnerProfile)
    assert stored.created_at is not None
    assert stored.updated_at is not None
    await engine.dispose()
