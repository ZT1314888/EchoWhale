from __future__ import annotations

import pytest

from api.common.exceptions import ConfigurationError
from api.common.exceptions import EchoWhaleError
from api.common.exceptions import UnsupportedSceneImageError
from api.modules.scene_engine.agent import SceneEngineAgent
from api.modules.scene_engine.providers.vision_provider import MockVisionProvider
from api.modules.scene_engine.schema import SceneAnalysisInput, SceneAnalysisResult
from api.modules.scene_engine.service import SceneEngineService


class FailingVisionProvider:
    async def analyze(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        raise EchoWhaleError("vision primary unavailable")


class SuccessfulVisionProvider:
    def __init__(self) -> None:
        self.calls: list[SceneAnalysisInput] = []

    async def analyze(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        self.calls.append(payload)
        return SceneAnalysisResult(
            scene="coffee_shop",
            role="barista",
            opener="Hi there, what can I get started for you today?",
            visual_anchors=["counter", "menu_board"],
            vocab_candidates=["latte", "size", "order"],
            confidence=0.91,
        )


class LowConfidenceVisionProvider:
    async def analyze(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        return SceneAnalysisResult(
            scene="coffee_shop",
            role="barista",
            opener="Hi there, what can I get started for you today?",
            visual_anchors=["counter"],
            vocab_candidates=["latte"],
            confidence=0.42,
        )


class InvalidStructuredVisionProvider:
    async def analyze(self, payload: SceneAnalysisInput) -> dict[str, object]:
        return {
            "scene": "coffee shop",
            "role": "barista",
            "opener": "Hi there, what can I get started for you today?",
            "visual_anchors": ["Counter", "", " Menu Board "],
            "vocab_candidates": ["Latte", "latte", ""],
            "confidence": 1.3,
        }


class EmptyVisualAnchorsVisionProvider:
    async def analyze(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        return SceneAnalysisResult(
            scene="coffee_shop",
            role="barista",
            opener="Hi there, what can I get started for you today?",
            visual_anchors=[],
            vocab_candidates=["latte"],
            confidence=0.92,
        )


class EmptyVocabCandidatesVisionProvider:
    async def analyze(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        return SceneAnalysisResult(
            scene="coffee_shop",
            role="barista",
            opener="Hi there, what can I get started for you today?",
            visual_anchors=["counter"],
            vocab_candidates=[],
            confidence=0.92,
        )


@pytest.mark.anyio
async def test_scene_engine_uses_fallback_provider_when_primary_fails() -> None:
    fallback = SuccessfulVisionProvider()
    agent = SceneEngineAgent(
        primary_provider=FailingVisionProvider(),
        fallback_provider=fallback,
    )

    result = await agent.run(
        SceneAnalysisInput(
            filename="mystery-upload.png",
            media_url="https://signed.test/media/demo-user/mystery-upload.png",
        )
    )

    assert result.scene == "coffee_shop"
    assert result.visual_anchors == ["counter", "menu_board"]
    assert result.vocab_candidates == ["latte", "size", "order"]
    assert result.labels == ["counter", "menu_board", "latte", "size", "order"]
    assert fallback.calls[0].media_url == "https://signed.test/media/demo-user/mystery-upload.png"


def test_scene_analysis_result_normalizes_dual_keyword_lists() -> None:
    result = SceneAnalysisResult.model_validate(
        {
            "scene": "Coffee Shop",
            "role": "  barista  ",
            "opener": "  Hi there, what can I get started for you today?  ",
            "visual_anchors": ["Counter", "counter", " Menu Board ", ""],
            "vocab_candidates": ["Latte", "latte", " Small size ", ""],
            "confidence": 0.91,
        }
    )

    assert result.scene == "coffee_shop"
    assert result.role == "barista"
    assert result.opener == "Hi there, what can I get started for you today?"
    assert result.visual_anchors == ["counter", "menu board"]
    assert result.vocab_candidates == ["latte", "small size"]
    assert result.labels == ["counter", "menu board", "latte", "small size"]


@pytest.mark.anyio
async def test_scene_engine_uses_fallback_provider_for_low_confidence_result() -> None:
    fallback = SuccessfulVisionProvider()
    agent = SceneEngineAgent(
        primary_provider=LowConfidenceVisionProvider(),
        fallback_provider=fallback,
    )

    result = await agent.run(
        SceneAnalysisInput(
            filename="coffee-shop.png",
            media_url="https://signed.test/media/demo-user/coffee-shop.png",
        )
    )

    assert result.confidence == 0.91
    assert fallback.calls[0].filename == "coffee-shop.png"


@pytest.mark.anyio
async def test_scene_engine_uses_fallback_provider_for_invalid_primary_output() -> None:
    fallback = SuccessfulVisionProvider()
    agent = SceneEngineAgent(
        primary_provider=InvalidStructuredVisionProvider(),
        fallback_provider=fallback,
    )

    result = await agent.run(
        SceneAnalysisInput(
            filename="coffee-shop.png",
            media_url="https://signed.test/media/demo-user/coffee-shop.png",
        )
    )

    assert result.scene == "coffee_shop"
    assert fallback.calls[0].filename == "coffee-shop.png"


@pytest.mark.anyio
async def test_scene_engine_uses_fallback_provider_for_empty_visual_anchors() -> None:
    fallback = SuccessfulVisionProvider()
    agent = SceneEngineAgent(
        primary_provider=EmptyVisualAnchorsVisionProvider(),
        fallback_provider=fallback,
    )

    result = await agent.run(
        SceneAnalysisInput(
            filename="coffee-shop.png",
            media_url="https://signed.test/media/demo-user/coffee-shop.png",
        )
    )

    assert result.visual_anchors == ["counter", "menu_board"]
    assert result.vocab_candidates == ["latte", "size", "order"]


@pytest.mark.anyio
async def test_scene_engine_uses_fallback_provider_for_empty_vocab_candidates() -> None:
    fallback = SuccessfulVisionProvider()
    agent = SceneEngineAgent(
        primary_provider=EmptyVocabCandidatesVisionProvider(),
        fallback_provider=fallback,
    )

    result = await agent.run(
        SceneAnalysisInput(
            filename="coffee-shop.png",
            media_url="https://signed.test/media/demo-user/coffee-shop.png",
        )
    )

    assert result.visual_anchors == ["counter", "menu_board"]
    assert result.vocab_candidates == ["latte", "size", "order"]


@pytest.mark.anyio
async def test_scene_engine_raises_when_both_providers_fail(monkeypatch) -> None:
    from api.core.config import settings

    # 关闭同 provider 重试，确保测试关注的是 failover 而非重试语义。
    monkeypatch.setattr(settings, "llm_max_retries_per_provider", 0)
    monkeypatch.setattr(settings, "llm_retry_backoff_seconds", 0)
    agent = SceneEngineAgent(
        primary_provider=FailingVisionProvider(),
        fallback_provider=FailingVisionProvider(),
    )

    with pytest.raises(EchoWhaleError, match="vision primary unavailable"):
        await agent.run(
            SceneAnalysisInput(
                filename="coffee-shop.png",
                media_url="https://signed.test/media/demo-user/coffee-shop.png",
            )
        )


@pytest.mark.anyio
async def test_scene_engine_raises_unsupported_image_when_all_providers_report_unusable_scene() -> None:
    agent = SceneEngineAgent(
        primary_provider=LowConfidenceVisionProvider(),
        fallback_provider=EmptyVocabCandidatesVisionProvider(),
    )

    with pytest.raises(UnsupportedSceneImageError) as exc_info:
        await agent.run(
            SceneAnalysisInput(
                filename="mystery-upload.png",
                media_url="https://signed.test/media/demo-user/mystery-upload.png",
            )
        )

    assert exc_info.value.data == {
        "reason": "scene_not_practice_ready",
        "retryable": False,
    }


@pytest.mark.anyio
async def test_mock_vision_provider_uses_reception_style_prompting_for_office_images() -> None:
    provider = MockVisionProvider()

    result = await provider.analyze(
        SceneAnalysisInput(
            filename="office-lobby.png",
            media_url="https://signed.test/media/demo-user/office-lobby.png",
        )
    )

    assert result.scene == "office"
    assert result.role == "office staff"
    assert "welcome" in result.opener.lower()
    assert "glass wall" in result.visual_anchors
    assert any(value in result.vocab_candidates for value in ["visitor", "meeting", "reception"])


def test_live_scene_engine_requires_real_provider_configuration(monkeypatch) -> None:
    from api.core.config import settings

    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    monkeypatch.setattr(settings, "vision_primary_provider", "")
    monkeypatch.setattr(settings, "vision_fallback_provider", "")

    with pytest.raises(ConfigurationError, match="real vision provider"):
        SceneEngineService()
