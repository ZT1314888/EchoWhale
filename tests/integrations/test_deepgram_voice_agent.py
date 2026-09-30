from __future__ import annotations

import httpx
import pytest

from api.common.exceptions import ConfigurationError
from api.common.exceptions import VoiceTokenError
from api.integrations.deepgram.voice_agent import DeepgramSettingsBuilder
from api.integrations.deepgram.voice_agent import DeepgramTokenIssuer
from api.models.message_model import Message
from api.models.session_model import Session


def test_token_issuer_rejects_blank_api_key() -> None:
    issuer = DeepgramTokenIssuer(api_key="   ")

    with pytest.raises(ConfigurationError, match="DEEPGRAM_API_KEY"):
        issuer.issue_token(ttl_seconds=600)


def test_token_issuer_wraps_sdk_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeGrantClient:
        class auth:
            class v1:
                class tokens:
                    @staticmethod
                    def grant(*, ttl_seconds: int):
                        raise httpx.LocalProtocolError("Illegal header value b'Token '")

    monkeypatch.setattr(
        "api.integrations.deepgram.voice_agent.DeepgramClient",
        lambda api_key: FakeGrantClient(),
    )
    issuer = DeepgramTokenIssuer(api_key="dg_test_key")

    with pytest.raises(VoiceTokenError, match="Deepgram token 获取失败"):
        issuer.issue_token(ttl_seconds=600)


def test_settings_builder_includes_native_think_provider_without_proxy_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api.integrations.deepgram.voice_agent.settings.deepgram_agent_listen_eot_threshold",
        0.7,
    )
    monkeypatch.setattr(
        "api.integrations.deepgram.voice_agent.settings.deepgram_agent_listen_eager_eot_threshold",
        0.4,
    )
    monkeypatch.setattr(
        "api.integrations.deepgram.voice_agent.settings.deepgram_agent_listen_eot_timeout_ms",
        6000,
    )
    monkeypatch.setattr(
        "api.integrations.deepgram.voice_agent.settings.deepgram_agent_listen_smart_format",
        False,
    )
    monkeypatch.setattr(
        "api.integrations.deepgram.voice_agent.settings.deepgram_agent_output_sample_rate",
        24000,
    )
    monkeypatch.setattr(
        "api.integrations.deepgram.voice_agent.settings.deepgram_agent_think_model",
        "gpt-4o-mini",
    )
    session = Session(
        id="sess_voice",
        user_id="user:user_123",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "menu"],
        messages=[
            Message(
                id="msg_1",
                role="assistant",
                text="Hi there, what can I get started for you today?",
            )
        ],
    )

    payload = DeepgramSettingsBuilder().build(session)

    assert payload["audio"]["input"]["sample_rate"] == 16000
    assert payload["audio"]["output"] == {
        "encoding": "linear16",
        "sample_rate": 24000,
        "container": "none",
    }
    assert payload["agent"]["listen"]["provider"] == {
        "type": "deepgram",
        "model": "flux-general-en",
        "version": "v2",
        "eot_threshold": 0.7,
        "eager_eot_threshold": 0.4,
    }
    assert payload["agent"]["think"]["provider"] == {
        "type": "open_ai",
        "model": "gpt-4o-mini",
    }
    assert "endpoint" not in payload["agent"]["think"]
    assert "coffee_shop" in payload["agent"]["think"]["prompt"]
    assert "barista" in payload["agent"]["think"]["prompt"]


def test_settings_builder_rejects_missing_think_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api.integrations.deepgram.voice_agent.settings.deepgram_agent_think_model",
        "   ",
    )
    session = Session(
        id="sess_voice",
        user_id="user:user_123",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[],
    )

    with pytest.raises(ConfigurationError, match="DEEPGRAM_AGENT_THINK_MODEL"):
        DeepgramSettingsBuilder().build(session)
