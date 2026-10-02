"""三引擎 provider 构造链的 max_tokens 与用量 sink 接线断言（Finding 10a/10b）。

provider 构造期从 settings 读各自预算并把 sink 接进客户端，引擎（agent）无感知；
用 fake client 捕获构造参数验证接线，而不是发真实请求。
"""

from __future__ import annotations

from api.core.config import settings
from api.integrations.llm.runtime import ProviderSlotConfig, TextCompletionProvider
from api.modules.coach_engine.providers.chat_provider import OpenAICompatibleChatProvider
from api.modules.scene_engine.providers.vision_provider import OpenAICompatibleVisionProvider


class RecordingClient:
    """捕获构造参数的 fake client，代替真实 OpenAICompatibleClient。"""

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class FakeUsageSink:
    def record(
        self,
        *,
        model: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
    ) -> None: ...


def test_coach_provider_wires_coach_max_tokens_and_sink(monkeypatch) -> None:
    sink = FakeUsageSink()
    monkeypatch.setattr(
        "api.modules.coach_engine.providers.chat_provider.OpenAICompatibleClient",
        RecordingClient,
    )

    provider = OpenAICompatibleChatProvider(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=30,
        usage_sink=sink,
    )

    assert provider.client.kwargs["max_tokens"] == settings.llm_coach_max_tokens
    assert provider.client.kwargs["usage_sink"] is sink


def test_feedback_provider_wires_feedback_max_tokens_and_sink(monkeypatch) -> None:
    sink = FakeUsageSink()
    monkeypatch.setattr(
        "api.integrations.llm.runtime.OpenAICompatibleClient",
        RecordingClient,
    )

    provider = TextCompletionProvider(
        ProviderSlotConfig(
            provider="openai_compatible",
            base_url="https://llm.test",
            api_key="key",
            model="demo-model",
            timeout_seconds=30,
        ),
        max_tokens=settings.llm_feedback_max_tokens,
        usage_sink=sink,
    )

    assert provider._client.kwargs["max_tokens"] == settings.llm_feedback_max_tokens
    assert provider._client.kwargs["usage_sink"] is sink


def test_scene_provider_wires_scene_max_tokens_and_sink(monkeypatch) -> None:
    sink = FakeUsageSink()
    monkeypatch.setattr(
        "api.modules.scene_engine.providers.vision_provider.OpenAICompatibleClient",
        RecordingClient,
    )

    provider = OpenAICompatibleVisionProvider(
        base_url="https://llm.test",
        api_key="key",
        model="demo-model",
        timeout_seconds=30,
        usage_sink=sink,
    )

    assert provider.client.kwargs["max_tokens"] == settings.llm_scene_max_tokens
    assert provider.client.kwargs["usage_sink"] is sink


def test_providers_default_to_shared_usage_sink(monkeypatch) -> None:
    """未显式传 sink 时默认接入 lru_cache 单例账本（进程级共享一份）。"""
    from api.db.llm_usage_db import build_llm_usage_sink

    monkeypatch.setattr(
        "api.modules.coach_engine.providers.chat_provider.OpenAICompatibleClient",
        RecordingClient,
    )
    monkeypatch.setattr(
        "api.modules.scene_engine.providers.vision_provider.OpenAICompatibleClient",
        RecordingClient,
    )
    monkeypatch.setattr(
        "api.integrations.llm.runtime.OpenAICompatibleClient",
        RecordingClient,
    )

    coach = OpenAICompatibleChatProvider(
        base_url="https://llm.test", api_key="k", model="m", timeout_seconds=5
    )
    scene = OpenAICompatibleVisionProvider(
        base_url="https://llm.test", api_key="k", model="m", timeout_seconds=5
    )
    feedback = TextCompletionProvider(
        ProviderSlotConfig(
            provider="openai_compatible",
            base_url="https://llm.test",
            api_key="k",
            model="m",
            timeout_seconds=5,
        ),
    )

    default_sink = build_llm_usage_sink()
    assert coach.client.kwargs["usage_sink"] is default_sink
    assert scene.client.kwargs["usage_sink"] is default_sink
    assert feedback._client.kwargs["usage_sink"] is default_sink
