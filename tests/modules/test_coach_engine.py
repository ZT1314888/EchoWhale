from __future__ import annotations

import pytest

from api.common.exceptions import ConfigurationError
from api.core.config import settings
from api.models.message_model import Message
from api.modules.coach_engine.evaluation import (
    evaluate_coach_reply_hard_checks,
    normalize_english_tokens,
)
from api.modules.coach_engine.prompts.coach_prompts import (
    COACH_LEARNER_LEVEL,
    COACH_SYSTEM_PROMPT,
    build_coach_system_prompt,
)
from api.modules.coach_engine.providers.chat_provider import (
    MockChatProvider,
    OpenAICompatibleChatProvider,
)
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


def _bare_learner_payload() -> CoachReplyInput:
    """无历史 + anchors/vocab 双空的最小输入（design 2.4 的两条复读路径）。"""
    return CoachReplyInput(
        scene="coffee_shop",
        role="barista",
        learner_message="I would like to order a large latte with extra foam",
        visual_anchors=[],
        vocab_candidates=[],
        recent_messages=[],
    )


@pytest.mark.anyio
async def test_mock_reply_bare_input_passes_all_hard_checks() -> None:
    """design 2.4：无历史 + 双空输入不再复读学习者原句，五维硬规则全过。"""
    payload = _bare_learner_payload()
    result = await MockChatProvider().reply(payload)

    # 注意 keyword-only 签名：reply_text= / learner_message=。
    checks = evaluate_coach_reply_hard_checks(
        reply_text=result.text, learner_message=payload.learner_message
    )
    assert checks.hard_pass, checks.failure_reasons
    # 中性短语开头 + 场景中性素材 + 追问收尾的三句形态保持不变。
    assert result.text.startswith("As your barista, I hear you. ")
    assert result.text.endswith("Would you like that hot or iced?")


@pytest.mark.anyio
async def test_mock_reply_bare_input_does_not_echo_learner_message() -> None:
    """design 2.4 独立断言：学习者原句不得作为连续子序列复现在回复中。"""
    payload = _bare_learner_payload()
    result = await MockChatProvider().reply(payload)

    learner_tokens = normalize_english_tokens(payload.learner_message)
    reply_tokens = normalize_english_tokens(result.text)
    width = len(learner_tokens)
    echoed = any(
        reply_tokens[index : index + width] == learner_tokens
        for index in range(len(reply_tokens) - width + 1)
    )
    assert not echoed


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
    # 角色接地行（eval_prompt_fixes 批次 design 2.1）：visual anchors 是眼前场景
    # 内的事物，绝不提及 images/photos/being unable to see。
    assert "never mention images, photos, or being unable to see" in COACH_SYSTEM_PROMPT


def test_build_coach_system_prompt_none_matches_constant_byte_for_byte() -> None:
    """无档案时默认提示词与存量常量逐字节一致：回退路径零回归。"""
    assert build_coach_system_prompt(None) == COACH_SYSTEM_PROMPT
    assert build_coach_system_prompt() == COACH_SYSTEM_PROMPT


def test_build_coach_system_prompt_overrides_level_with_dynamic_cefr() -> None:
    """有档案时动态估计覆盖静态水平行，模板其余约束行保持不动。"""
    prompt = build_coach_system_prompt("B2")

    assert "estimated CEFR B2" in prompt
    assert COACH_LEARNER_LEVEL not in prompt
    assert "English only" in prompt
    assert "at most 3 short sentences" in prompt
    # 模板非水平行逐字节不变：动态注入只替换 The learner is ... 一行。
    static_prompt = build_coach_system_prompt(None)
    assert prompt.replace("estimated CEFR B2", COACH_LEARNER_LEVEL) == static_prompt


@pytest.mark.anyio
async def test_live_chat_provider_appends_learner_context_block_to_user_prompt() -> None:
    """live 教练路径：动态 CEFR 覆盖系统提示词水平行，注入块追加在 scene 块后。"""
    provider = OpenAICompatibleChatProvider(
        base_url="https://llm.test",
        api_key="dummy",
        model="demo-model",
        timeout_seconds=30,
    )
    provider.client = CapturingClient()

    context = "Learner profile: estimated CEFR B1.\n" "Learner profile: 6 practice turns completed."
    await provider.reply(
        CoachReplyInput(
            scene="office",
            role="office staff",
            learner_message="I am here for a meeting.",
            learner_context=context,
            learner_cefr="B1",
        )
    )

    system_prompt, user_prompt = provider.client.calls[0]
    assert "estimated CEFR B1" in system_prompt
    assert COACH_LEARNER_LEVEL not in system_prompt
    # 注入块紧跟 scene 块之后（两形态位置契约）。
    assert user_prompt.index("Scene: office") < user_prompt.index("Learner profile:")
    assert context in user_prompt


@pytest.mark.anyio
async def test_live_chat_provider_omits_context_block_when_absent() -> None:
    """无档案时 user prompt 不含注入块：与历史形态逐字节一致。"""
    provider = OpenAICompatibleChatProvider(
        base_url="https://llm.test",
        api_key="dummy",
        model="demo-model",
        timeout_seconds=30,
    )
    provider.client = CapturingClient()

    await provider.reply(
        CoachReplyInput(
            scene="office",
            role="office staff",
            learner_message="I am here for a meeting.",
        )
    )

    system_prompt, user_prompt = provider.client.calls[0]
    assert system_prompt == COACH_SYSTEM_PROMPT
    assert "Learner profile:" not in user_prompt
