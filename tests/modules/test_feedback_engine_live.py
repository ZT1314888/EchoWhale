"""反馈引擎离线评测（RUN_FEEDBACK_EVAL=1 门控，CI 默认跳过）。

与 test_scene_engine_live.py 同款约定：提示词是产品核心资产，
本地手动运行 `RUN_FEEDBACK_EVAL=1 uv run pytest tests/modules/test_feedback_engine_live.py`
做提示词回归；固定学习者输入集 → 断言输出结构与长度契约稳定。
依赖环境里已配置的 live 文本 provider（TEXT_PRIMARY_* / TEXT_FALLBACK_*）。
"""

from __future__ import annotations

import os

import pytest

from api.common.exceptions import ConfigurationError
from api.core.config import settings
from api.modules.feedback_engine.agent import FeedbackEngineAgent
from api.modules.feedback_engine.schema import FeedbackInput

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_FEEDBACK_EVAL") != "1",
    reason="Set RUN_FEEDBACK_EVAL=1 to run feedback_engine live evaluation.",
)

CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}
ERROR_CATEGORIES = {
    "grammar",
    "tense",
    "article",
    "preposition",
    "word_choice",
    "collocation",
    "register",
    "spelling",
    "other",
}

# 固定学习者输入集：覆盖无错误 / 时态错 / 冠词介词错 / 用词错 / 混合错误。
EVAL_INPUTS = [
    (
        "no_error",
        "I would like to order a cappuccino and a slice of cheesecake, please.",
    ),
    ("tense_error", "Yesterday I go to the coffee shop with my friend."),
    (
        "article_preposition_error",
        "I am living in Beijing since three year at a small apartment.",
    ),
    ("word_choice_error", "Can you borrow me your pen for one minute?"),
    (
        "mixed_error",
        "Yesterday I have ate a apple and drink a coffee in the morning at my home.",
    ),
]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "case_name,learner_message", EVAL_INPUTS, ids=[case[0] for case in EVAL_INPUTS]
)
async def test_feedback_engine_live_structure_contract(
    case_name: str, learner_message: str
) -> None:
    """固定学习者输入的结构与长度契约断言（提示词回归网）。"""
    del case_name  # 仅作为用例命名；断言对全部输入一视同仁。
    if settings.model_runtime_mode.strip().lower() != "live":
        pytest.fail(
            "MODEL_RUNTIME_MODE must be 'live' before running the feedback evaluation "
            "(mock mode would return template feedback and fail these assertions)."
        )

    agent = FeedbackEngineAgent()
    try:
        result = await agent.run(
            FeedbackInput(learner_message=learner_message, scene="coffee_shop", vocab_candidates=[])
        )
    except ConfigurationError as exc:
        pytest.fail(
            "Live text providers are not configured. Set TEXT_PRIMARY_* / TEXT_FALLBACK_* "
            "(PROVIDER / BASE_URL / API_KEY / MODEL) and MODEL_RUNTIME_MODE=live before "
            f"running the feedback evaluation. Original error: {exc}"
        )

    # 结构契约（与 FEEDBACK_PROMPT 契约及消费侧硬顶对齐，允许一定弹性）。
    assert 1 <= len(result.grammar) <= 400
    assert result.more_natural.strip()
    assert len(result.more_natural) <= 320
    assert result.more_natural.strip() != learner_message.strip()
    assert 0 <= len(result.useful_words) <= 5
    for word in result.useful_words:
        assert len(word.split()) <= 4
    assert result.cefr_level in CEFR_LEVELS
    assert len(result.errors) <= 3
    for error in result.errors:
        assert error.category in ERROR_CATEGORIES
        assert error.original.strip()
        assert error.correction.strip()
        assert error.explanation.strip()
        assert len(error.explanation) <= 200
