from __future__ import annotations

import json

import pytest

from api.common.exceptions import ConfigurationError
from api.core.config import settings
from api.modules.feedback_engine.agent import FeedbackEngineAgent
from api.modules.feedback_engine.prompts.feedback_prompts import FEEDBACK_PROMPT
from api.modules.feedback_engine.schema import FeedbackInput, FeedbackResult
from api.modules.feedback_engine.service import FeedbackEngineService


def _configure_live_text_providers(monkeypatch) -> None:
    """把 live 文本主备槽位指向假客户端会命中的配置。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    monkeypatch.setattr(settings, "text_primary_provider", "openai_compatible")
    monkeypatch.setattr(settings, "text_primary_base_url", "https://primary.test")
    monkeypatch.setattr(settings, "text_primary_api_key", "primary-key")
    monkeypatch.setattr(settings, "text_primary_model", "primary-model")
    monkeypatch.setattr(settings, "text_fallback_provider", "openai_compatible")
    monkeypatch.setattr(settings, "text_fallback_base_url", "https://fallback.test")
    monkeypatch.setattr(settings, "text_fallback_api_key", "fallback-key")
    monkeypatch.setattr(settings, "text_fallback_model", "fallback-model")


@pytest.mark.anyio
async def test_feedback_engine_prioritizes_vocab_candidates_as_useful_words(monkeypatch) -> None:
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    service = FeedbackEngineService()

    result = await service.review(
        learner_message="I want a hot drink and a small snack",
        scene="coffee_shop",
        vocab_candidates=["latte", "croissant", "order"],
    )

    assert result.useful_words == ["latte", "croissant", "order"]


@pytest.mark.anyio
async def test_feedback_engine_falls_back_to_scene_words_when_vocab_candidates_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    service = FeedbackEngineService()

    result = await service.review(
        learner_message="I need help with my schedule",
        scene="office",
        vocab_candidates=[],
    )

    assert result.useful_words == ["deadline", "update", "priority"]


@pytest.mark.anyio
async def test_feedback_engine_uses_live_path_when_only_fallback_provider_is_live(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    monkeypatch.setattr(settings, "text_primary_provider", "mock")
    monkeypatch.setattr(settings, "text_fallback_provider", "openai_compatible")

    agent = FeedbackEngineAgent()

    async def fake_run_live(payload: FeedbackInput) -> FeedbackResult:
        return FeedbackResult(
            grammar=f"live:{payload.scene}",
            more_natural="A more natural sentence.",
            useful_words=["latte"],
        )

    monkeypatch.setattr(agent, "_run_live", fake_run_live)

    result = await agent.run(
        FeedbackInput(
            learner_message="I want a latte",
            scene="coffee_shop",
            vocab_candidates=[],
        )
    )

    assert result.grammar == "live:coffee_shop"


@pytest.mark.anyio
async def test_feedback_engine_live_mode_requires_real_provider_configuration(monkeypatch) -> None:
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    monkeypatch.setattr(settings, "text_primary_provider", "")
    monkeypatch.setattr(settings, "text_fallback_provider", "")

    agent = FeedbackEngineAgent()

    with pytest.raises(ConfigurationError, match="real text provider"):
        await agent.run(
            FeedbackInput(
                learner_message="I want a latte",
                scene="coffee_shop",
                vocab_candidates=[],
            )
        )


@pytest.mark.anyio
async def test_feedback_engine_live_mode_uses_only_configured_real_clients(monkeypatch) -> None:
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    monkeypatch.setattr(settings, "text_primary_provider", "mock")
    monkeypatch.setattr(settings, "text_primary_base_url", "")
    monkeypatch.setattr(settings, "text_primary_api_key", "")
    monkeypatch.setattr(settings, "text_primary_model", "")
    monkeypatch.setattr(settings, "text_fallback_provider", "openai_compatible")
    monkeypatch.setattr(settings, "text_fallback_base_url", "https://fallback.test")
    monkeypatch.setattr(settings, "text_fallback_api_key", "fallback-key")
    monkeypatch.setattr(settings, "text_fallback_model", "fallback-model")

    called_base_urls: list[str] = []

    class FakeOpenAICompatibleClient:
        def __init__(
            self,
            *,
            base_url: str,
            api_key: str,
            model: str,
            timeout_seconds: int,
            json_mode: bool = False,
            stream_include_usage: bool = False,
            max_tokens: int | None = None,
            usage_sink=None,
        ) -> None:
            self.base_url = base_url

        async def async_complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
            called_base_urls.append(self.base_url)
            return json.dumps(
                {
                    "grammar": "grammar",
                    "more_natural": "more natural",
                    "useful_words": ["latte"],
                }
            )

    monkeypatch.setattr(
        "api.integrations.llm.runtime.OpenAICompatibleClient", FakeOpenAICompatibleClient
    )

    result = await FeedbackEngineAgent().run(
        FeedbackInput(
            learner_message="I want a latte",
            scene="coffee_shop",
            vocab_candidates=["latte"],
        )
    )

    assert result.useful_words == ["latte"]
    assert called_base_urls == ["https://fallback.test"]


@pytest.mark.anyio
async def test_feedback_engine_live_populates_errors_and_cefr_level(monkeypatch) -> None:
    """live 输出包含结构化错误与 CEFR 标注时新字段落位，既有字段语义不变。"""
    _configure_live_text_providers(monkeypatch)

    class FakeOpenAICompatibleClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def async_complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
            return json.dumps(
                {
                    "grammar": "I want -> I'd like (polite requests)",
                    "more_natural": "I'd like a latte, please.",
                    "useful_words": ["latte", "order"],
                    "errors": [
                        {
                            "category": "tense",
                            "original": "I want",
                            "correction": "I'd like",
                            "explanation": "Polite requests use would like instead of want.",
                        }
                    ],
                    "cefr_level": "b1",
                }
            )

    monkeypatch.setattr(
        "api.integrations.llm.runtime.OpenAICompatibleClient", FakeOpenAICompatibleClient
    )

    result = await FeedbackEngineAgent().run(
        FeedbackInput(learner_message="I want a latte", scene="coffee_shop", vocab_candidates=[])
    )

    assert result.cefr_level == "B1"
    assert len(result.errors) == 1
    assert result.errors[0].category == "tense"
    assert result.errors[0].original == "I want"
    assert result.errors[0].correction == "I'd like"
    assert result.errors[0].explanation.startswith("Polite requests")
    assert result.grammar.startswith("I want")
    assert result.more_natural == "I'd like a latte, please."


@pytest.mark.anyio
async def test_feedback_engine_live_defaults_when_model_omits_new_keys(monkeypatch) -> None:
    """模型省略新键时新字段走默认空态，契约只加不改。"""
    _configure_live_text_providers(monkeypatch)

    class FakeOpenAICompatibleClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def async_complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
            return json.dumps(
                {
                    "grammar": "grammar",
                    "more_natural": "more natural",
                    "useful_words": ["latte"],
                }
            )

    monkeypatch.setattr(
        "api.integrations.llm.runtime.OpenAICompatibleClient", FakeOpenAICompatibleClient
    )

    result = await FeedbackEngineAgent().run(
        FeedbackInput(learner_message="I want a latte", scene="coffee_shop", vocab_candidates=[])
    )

    assert result.errors == []
    assert result.cefr_level is None
    assert result.useful_words == ["latte"]


@pytest.mark.anyio
async def test_feedback_engine_live_normalizes_invalid_cefr_level_to_none(monkeypatch) -> None:
    """模型幻觉 CEFR 值（不在 A1..C2 封闭集合）防御为 None。"""
    _configure_live_text_providers(monkeypatch)

    class FakeOpenAICompatibleClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def async_complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
            return json.dumps(
                {
                    "grammar": "grammar",
                    "more_natural": "more natural",
                    "useful_words": ["latte"],
                    "cefr_level": "  Z9  ",
                }
            )

    monkeypatch.setattr(
        "api.integrations.llm.runtime.OpenAICompatibleClient", FakeOpenAICompatibleClient
    )

    result = await FeedbackEngineAgent().run(
        FeedbackInput(learner_message="I want a latte", scene="coffee_shop", vocab_candidates=[])
    )

    assert result.cefr_level is None


def test_feedback_prompt_declares_structured_contract() -> None:
    """提示词契约守卫：分类封闭集合、CEFR 标注与长度约束必须显式存在。"""
    categories = [
        "grammar",
        "tense",
        "article",
        "preposition",
        "word_choice",
        "collocation",
        "register",
        "spelling",
        "other",
    ]
    for category in categories:
        assert category in FEEDBACK_PROMPT
    assert "cefr_level" in FEEDBACK_PROMPT
    assert "A1" in FEEDBACK_PROMPT
    assert "C2" in FEEDBACK_PROMPT
    assert "at most 3 items" in FEEDBACK_PROMPT
    assert "320 characters" in FEEDBACK_PROMPT
    assert "at most 2 sentences" in FEEDBACK_PROMPT
    assert "2 to 4" in FEEDBACK_PROMPT
    assert "strict JSON" in FEEDBACK_PROMPT


@pytest.mark.anyio
async def test_feedback_engine_live_user_prompt_carries_learner_context(monkeypatch) -> None:
    """live 反馈路径：学员注入块追加进 user prompt（scene 块之后）。"""
    _configure_live_text_providers(monkeypatch)
    captured: list[str] = []

    class FakeOpenAICompatibleClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def async_complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
            captured.append(user_prompt)
            return json.dumps({"grammar": "g", "more_natural": "m", "useful_words": ["latte"]})

    monkeypatch.setattr(
        "api.integrations.llm.runtime.OpenAICompatibleClient", FakeOpenAICompatibleClient
    )

    context = "Learner profile: estimated CEFR B1.\nLearner profile: 6 practice turns completed."
    await FeedbackEngineAgent().run(
        FeedbackInput(
            learner_message="I want a latte",
            scene="coffee_shop",
            vocab_candidates=[],
            learner_context=context,
        )
    )

    user_prompt = captured[0]
    assert "Learner profile: estimated CEFR B1." in user_prompt
    assert "Learner profile: 6 practice turns completed." in user_prompt
    # 注入块紧跟 scene 块之后。
    assert user_prompt.index("Scene: coffee_shop") < user_prompt.index("Learner profile:")


@pytest.mark.anyio
async def test_feedback_engine_live_user_prompt_omits_context_when_absent(monkeypatch) -> None:
    """无档案时 live user prompt 不含注入块：与历史形态逐字节一致。"""
    _configure_live_text_providers(monkeypatch)
    captured: list[str] = []

    class FakeOpenAICompatibleClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def async_complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
            captured.append(user_prompt)
            return json.dumps({"grammar": "g", "more_natural": "m", "useful_words": ["latte"]})

    monkeypatch.setattr(
        "api.integrations.llm.runtime.OpenAICompatibleClient", FakeOpenAICompatibleClient
    )

    await FeedbackEngineAgent().run(
        FeedbackInput(learner_message="I want a latte", scene="coffee_shop", vocab_candidates=[])
    )

    assert "Learner profile:" not in captured[0]


@pytest.mark.anyio
async def test_feedback_engine_mock_path_ignores_learner_context(monkeypatch) -> None:
    """mock 路径忽略注入块：输出与历史 mock 形态一致，不含任何注入内容。"""
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    service = FeedbackEngineService()

    result = await service.review(
        learner_message="I want a hot drink",
        scene="coffee_shop",
        vocab_candidates=["latte"],
        learner_context="Learner profile: estimated CEFR B1.\nLearner profile: 6 practice turns completed.",
    )

    assert (
        result.grammar
        == "Your meaning is clear. Add articles and complete sentence endings when possible."
    )
    assert result.useful_words == ["latte"]
    assert "Learner profile" not in result.grammar
    assert "Learner profile" not in result.more_natural
