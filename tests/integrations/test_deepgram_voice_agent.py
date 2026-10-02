from __future__ import annotations

import httpx
import pytest

from api.common.exceptions import ConfigurationError, VoiceTokenError
from api.integrations.deepgram.voice_agent import (
    DeepgramSettingsBuilder,
    DeepgramTokenIssuer,
    build_voice_agent_prompt,
)
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


def _voice_prompt_session() -> Session:
    return Session(
        id="sess_voice_prompt",
        user_id="user:user_123",
        media_id="med_123",
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter"],
        vocab_candidates=["latte"],
        messages=[
            Message(
                id="msg_1", role="assistant", text="Hi there, what can I get started for you today?"
            ),
            Message(id="msg_2", role="user", text="Could I get an iced latte, please?"),
        ],
    )


def test_voice_agent_prompt_inserts_learner_context_before_history() -> None:
    """注入块（多行）整体插在历史行之前：行内内容与位置都有契约。"""
    context = (
        "Learner profile: estimated CEFR B1.\n"
        "Learner profile: frequent error categories so far: tense.\n"
        "Learner profile: 5 practice turns completed."
    )

    prompt = build_voice_agent_prompt(_voice_prompt_session(), learner_context=context)

    lines = prompt.splitlines()
    assert "Learner profile: estimated CEFR B1." in lines
    assert "Learner profile: frequent error categories so far: tense." in lines
    assert "Learner profile: 5 practice turns completed." in lines
    # 注入块整体位于 "Conversation so far:" 历史块之前。
    assert lines.index("Learner profile: estimated CEFR B1.") < lines.index("Conversation so far:")


def test_voice_agent_prompt_without_context_has_no_injection_lines() -> None:
    """无档案时语音提示词不含注入块：与历史形态逐字节一致。"""
    prompt = build_voice_agent_prompt(_voice_prompt_session())

    assert "Learner profile" not in prompt
    # 历史行与场景行照常存在。
    assert "Conversation so far:" in prompt
    assert "Scene: coffee_shop" in prompt


def test_voice_agent_prompt_injection_lines_never_carry_learner_transcript() -> None:
    """注入行守卫：注入块行不含学习者原文（原文只允许出现在 history 行）。

    learner_context 由服务端 build_learner_context_lines 渲染（封闭集合值 +
    整数）；本守卫锁定 build_voice_agent_prompt 不做任何"把用户文本带进注入
    行"的拼接——注入区行必须保持 Learner profile 前缀形态。
    """
    context = "Learner profile: estimated CEFR C1."
    prompt = build_voice_agent_prompt(_voice_prompt_session(), learner_context=context)

    context_region = prompt.split("Conversation so far:")[0]
    assert "Learner profile: estimated CEFR C1." in context_region
    # 学习者原文 "iced latte" 只出现在 history 区，不进注入区。
    assert "iced latte" not in context_region
    assert "iced latte" in prompt.split("Conversation so far:", 1)[1]


def test_settings_builder_passes_learner_context_into_think_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """settings builder 把注入块透传进 agent think prompt。"""
    monkeypatch.setattr(
        "api.integrations.deepgram.voice_agent.settings.deepgram_agent_think_model",
        "gpt-4o-mini",
    )
    session = _voice_prompt_session()

    payload = DeepgramSettingsBuilder().build(
        session, learner_context="Learner profile: estimated CEFR B1."
    )

    assert "Learner profile: estimated CEFR B1." in payload["agent"]["think"]["prompt"]
