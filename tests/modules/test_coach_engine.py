from __future__ import annotations

import pytest

from api.common.exceptions import ConfigurationError
from api.core.config import settings
from api.models.message_model import Message
from api.modules.coach_engine.prompts.coach_prompts import COACH_LEARNER_LEVEL, COACH_SYSTEM_PROMPT
from api.modules.coach_engine.providers.chat_provider import OpenAICompatibleChatProvider
from api.modules.coach_engine.schema import CoachReplyInput
from api.modules.coach_engine.service import CoachEngineService


@pytest.mark.anyio
async def test_coach_engine_uses_recent_messages_and_visual_anchors_to_build_reply(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    service = CoachEngineService()

    result = await service.respond(
        scene="coffee_shop",
        role="barista",
        learner_message="I would like a latte",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "order"],
        recent_messages=[
            Message(role="assistant", text="Hi there, what can I get started for you today?"),
            Message(role="user", text="I would like a latte"),
        ],
    )

    assert "counter" in result.text.lower()
    assert "menu board" in result.text.lower()


class CapturingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def async_complete_text(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return "Hello! Please take a seat on the sofa while you wait."


@pytest.mark.anyio
async def test_live_chat_provider_includes_grounded_context_and_vocab_candidates() -> None:
    provider = OpenAICompatibleChatProvider(
        base_url="https://llm.test",
        api_key="dummy",
        model="demo-model",
        timeout_seconds=30,
    )
    provider.client = CapturingClient()

    result = await provider.reply(
        CoachReplyInput(
            scene="office",
            role="office staff",
            learner_message="I am here for a meeting.",
            visual_anchors=["glass wall", "purple sofa", "logo"],
            vocab_candidates=["visitor", "meeting", "welcome"],
            recent_messages=[
                Message(role="assistant", text="Hello! Welcome to our office."),
                Message(role="user", text="I am here for a meeting."),
            ],
        )
    )

    assert "sofa" in result.text.lower()
    system_prompt, user_prompt = provider.client.calls[0]
    assert "grounded in the visible evidence" in system_prompt
    assert "Vocab candidates: visitor, meeting, welcome" in user_prompt
    assert "Plausible scenario expansion" in user_prompt


def test_live_coach_engine_requires_real_provider_configuration(monkeypatch) -> None:
    monkeypatch.setattr(settings, "model_runtime_mode", "live")
    monkeypatch.setattr(settings, "text_primary_provider", "")
    monkeypatch.setattr(settings, "text_fallback_provider", "")

    with pytest.raises(ConfigurationError, match="real text provider"):
        CoachEngineService()


def test_coach_system_prompt_declares_learner_level_and_constraints() -> None:
    """提示词守卫：水平注入位、仅英语约束与长度约束必须显式存在（审计 Finding 20）。"""
    assert COACH_LEARNER_LEVEL == "intermediate (CEFR B1)"
    # 注入位常量必须出现在系统提示词中（后续任务只改常量为动态取值）。
    assert COACH_LEARNER_LEVEL in COACH_SYSTEM_PROMPT
    assert "CEFR" in COACH_SYSTEM_PROMPT
    assert "English only" in COACH_SYSTEM_PROMPT
    assert "at most 3 short sentences" in COACH_SYSTEM_PROMPT
