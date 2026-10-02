from __future__ import annotations

import json

import pytest

from api.common.exceptions import ConfigurationError
from api.core.config import settings
import api.modules.feedback_engine.agent as feedback_agent_module
from api.modules.feedback_engine.agent import FeedbackEngineAgent
from api.modules.feedback_engine.schema import FeedbackInput, FeedbackResult
from api.modules.feedback_engine.service import FeedbackEngineService


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
async def test_feedback_engine_uses_live_path_when_only_fallback_provider_is_live(monkeypatch) -> None:
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

    monkeypatch.setattr("api.integrations.llm.runtime.OpenAICompatibleClient", FakeOpenAICompatibleClient)

    result = await FeedbackEngineAgent().run(
        FeedbackInput(
            learner_message="I want a latte",
            scene="coffee_shop",
            vocab_candidates=["latte"],
        )
    )

    assert result.useful_words == ["latte"]
    assert called_base_urls == ["https://fallback.test"]
