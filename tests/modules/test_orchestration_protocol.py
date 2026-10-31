"""协作层（orchestration/）单测：协议、注册表、失败策略与纯函数编排水务。

多 Agent 升级 P0 验收标准 2 的新增单测（≥15 条）：链路级行为语义由
test_session_engine / test_session_stream / test_history_cursor 回归锁定，
本文件锁定协作层自身契约——注册表纪律、三值终态与 telemetry 对齐、
增强协议结构判定、降级占位文案与日志事件、回复轮组装硬顶、
语音转写去重、档案增强分支的降级边界。
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from api.common.exceptions import ModelProviderError
from api.common.telemetry import TERMINAL_DEGRADED, TERMINAL_FAILED, TERMINAL_OK
from api.core.config import settings
from api.models.learner_profile_model import LearnerProfile
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.orchestration import (
    AgentDescriptor,
    AgentRegistrationError,
    AgentRegistry,
    AgentRequest,
    AgentResult,
    EngineTerminalState,
    EnhancementAgent,
    LearnerProfileBranch,
    build_degraded_feedback,
    degraded_feedback_with_log,
    resolve_feedback,
)
from api.modules.orchestration.reply_flow import build_reply_turn
from api.modules.orchestration.voice_flow import (
    build_voice_messages,
    find_latest_user_content,
    find_tail_overlap,
)
from api.modules.session_engine.schema import (
    VoiceCompleteInput,
    VoiceConversationTurn,
)

# —— 测试替身 ——


class _DemoEnhancementAgent:
    """最小 EnhancementAgent 实现：P0 用户故事（实现协议 + 注册表登记）。"""

    name = "demo_enhancement"

    async def invoke(self, request: AgentRequest) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            outcome=EngineTerminalState.OK,
            payload=request.payload,
        )


class _NotAnAgent:
    """缺少 invoke 协议方法的对象，用于结构判定反例。"""


class _RaisingProfileRepository:
    """读写即炸的档案仓储：用于验证增强分支的降级边界（零上抛、visitor 零查询）。"""

    async def get(self, user_id: str):
        raise RuntimeError("db down")

    async def upsert(self, profile):
        raise RuntimeError("db down")


class _StubProfileRepository:
    def __init__(self, profile: LearnerProfile | None) -> None:
        self.profile = profile
        self.upserts: list[LearnerProfile] = []

    async def get(self, user_id: str):
        return self.profile

    async def upsert(self, profile) -> None:
        self.upserts.append(profile)


def _descriptor(name: str) -> AgentDescriptor:
    return AgentDescriptor(name=name, role="r", failure_policy="f")


def _feedback() -> FeedbackResult:
    return FeedbackResult(grammar="g", more_natural="m", useful_words=["w"])


def _session(user_id: str = "user:1") -> Session:
    return Session(
        id="sess_test",
        user_id=user_id,
        media_id=None,
        scene="咖啡店点单",
        role="barista",
        opener="Hi! What can I get you?",
        visual_anchors=[],
        vocab_candidates=[],
        messages=[Message(role="assistant", text="Hi! What can I get you?")],
    )


def _voice_payload(*turns: VoiceConversationTurn) -> VoiceCompleteInput:
    return VoiceCompleteInput(
        session_id="sess_test",
        conversation=list(turns),
        termination_reason="user_ended",
        client_diagnostics={},
    )


# —— 协议与注册表 ——


def test_enhancement_agent_protocol_is_structural():
    assert isinstance(_DemoEnhancementAgent(), EnhancementAgent)
    assert not isinstance(_NotAnAgent(), EnhancementAgent)


def test_enhancement_agent_invoke_round_trip():
    agent = _DemoEnhancementAgent()
    request = AgentRequest(agent_name=agent.name, session_id="sess_test", payload={"k": "v"})
    result = asyncio.run(agent.invoke(request))
    assert result.agent_name == "demo_enhancement"
    assert result.outcome is EngineTerminalState.OK
    assert result.payload == {"k": "v"}


def test_engine_terminal_state_matches_telemetry_constants():
    assert EngineTerminalState.OK.value == TERMINAL_OK
    assert EngineTerminalState.DEGRADED.value == TERMINAL_DEGRADED
    assert EngineTerminalState.FAILED.value == TERMINAL_FAILED


def test_registry_register_and_resolve():
    registry = AgentRegistry()
    impl = _DemoEnhancementAgent()
    registry.register(_descriptor("demo_enhancement"), impl)
    assert registry.resolve("demo_enhancement") is impl
    assert "demo_enhancement" in registry
    assert len(registry) == 1
    assert registry.names() == ["demo_enhancement"]


def test_registry_rejects_duplicate_registration():
    registry = AgentRegistry()
    registry.register(_descriptor("dup"), object())
    with pytest.raises(AgentRegistrationError, match="dup"):
        registry.register(_descriptor("dup"), object())


def test_registry_resolve_missing_raises_key_error():
    registry = AgentRegistry()
    with pytest.raises(KeyError, match="ghost"):
        registry.resolve("ghost")
    with pytest.raises(KeyError, match="ghost"):
        registry.descriptor("ghost")


def test_registry_descriptor_round_trip():
    registry = AgentRegistry()
    descriptor = AgentDescriptor(
        name="review_summarizer",
        role="单轮中文复盘文案",
        failure_policy="mock 短路 / 超时降级模板复盘",
    )
    registry.register(descriptor, object())
    assert registry.descriptor("review_summarizer") == descriptor


# —— 失败策略（反馈降级占位）——


def test_resolve_feedback_returns_success_result_unchanged():
    feedback = _feedback()
    assert resolve_feedback(feedback) is feedback


def test_resolve_feedback_converts_exception_into_placeholder(caplog):
    with caplog.at_level(logging.WARNING):
        feedback = resolve_feedback(RuntimeError("feedback provider down"))
    assert feedback == build_degraded_feedback()
    assert "session_reply_branch_failed" in caplog.text
    assert "degraded=true" in caplog.text


def test_resolve_feedback_reraises_base_exception():
    with pytest.raises(asyncio.CancelledError):
        resolve_feedback(asyncio.CancelledError())


def test_degraded_feedback_placeholder_copy_is_honest():
    feedback = build_degraded_feedback()
    assert feedback.grammar == "本轮反馈生成失败，请继续对话；下一轮反馈会照常返回。"
    assert feedback.more_natural == "（本轮没有更自然表达建议）"
    assert feedback.useful_words == []
    # 每次新建实例而非共享单例：调用方改动可变字段不互相影响。
    first, second = build_degraded_feedback(), build_degraded_feedback()
    assert first is not second


def test_degraded_feedback_with_log_records_branch_event(caplog):
    with caplog.at_level(logging.WARNING):
        result = degraded_feedback_with_log(ValueError("boom"))
    assert result == build_degraded_feedback()
    assert "branch=feedback" in caplog.text
    assert "ValueError" in caplog.text


# —— 回复轮组装（输出硬顶与空输出判定）——


def test_build_reply_turn_rejects_empty_coach_text():
    with pytest.raises(ModelProviderError):
        build_reply_turn(_session(), [], learner_text="hi", coach_text="   ", feedback=_feedback())


def test_build_reply_turn_truncates_oversized_coach_reply(monkeypatch, caplog):
    monkeypatch.setattr(settings, "llm_coach_output_max_chars", 10)
    with caplog.at_level(logging.WARNING):
        learner_message, assistant_message, review = build_reply_turn(
            _session(), [], learner_text="hi", coach_text="x" * 30, feedback=_feedback()
        )
    assert len(assistant_message.text) == 10
    assert "coach_reply_truncated" in caplog.text
    assert assistant_message.feedback == _feedback().model_dump()
    assert learner_message.role == "user"
    assert review is not None


def test_build_reply_turn_appends_messages_after_recent_window():
    recent = [Message(role="user", text="earlier")]
    learner_message, assistant_message, _review = build_reply_turn(
        _session(),
        recent,
        learner_text="a latte please",
        coach_text="Sure! One latte.",
        feedback=_feedback(),
    )
    assert learner_message.text == "a latte please"
    assert assistant_message.text == "Sure! One latte."
    assert assistant_message.feedback == _feedback().model_dump()


# —— 语音转写纯函数（拼接 / 尾段去重 / 收口输入提取）——


def test_find_latest_user_content_returns_last_user_turn():
    payload = _voice_payload(
        VoiceConversationTurn(role="assistant", content="hi there"),
        VoiceConversationTurn(role="user", content="a coffee please"),
        VoiceConversationTurn(role="assistant", content="sure"),
    )
    assert find_latest_user_content(payload) == "a coffee please"


def test_find_latest_user_content_returns_none_without_user_turn():
    # 生产入口的写侧防御（schema 校验）已拦掉无 user turn 的收口请求；
    # 这里用 model_construct 跳过校验，锁定纯函数自身的防御分支。
    payload = VoiceCompleteInput.model_construct(
        session_id="sess_test",
        conversation=[VoiceConversationTurn(role="assistant", content="hi there")],
        termination_reason="user_ended",
        client_diagnostics={},
    )
    assert find_latest_user_content(payload) is None


def test_find_tail_overlap_detects_partial_overlap():
    existing = [Message(role="user", text="a"), Message(role="assistant", text="b")]
    incoming = [Message(role="assistant", text="b"), Message(role="user", text="c")]
    assert find_tail_overlap(existing=existing, incoming=incoming) == 1


def test_find_tail_overlap_full_and_none():
    existing = [Message(role="user", text="a")]
    assert find_tail_overlap(existing=existing, incoming=[Message(role="user", text="a")]) == 1
    assert find_tail_overlap(existing=existing, incoming=[Message(role="user", text="z")]) == 0


def test_build_voice_messages_reuses_existing_opener_and_dedupes_tail():
    session = _session()  # messages[0] = assistant 开场白
    payload = _voice_payload(
        VoiceConversationTurn(role="assistant", content="Hi! What can I get you?"),
        VoiceConversationTurn(role="user", content="a latte"),
        VoiceConversationTurn(role="assistant", content="One latte coming up."),
    )
    messages = build_voice_messages(session, payload)
    assert [message.text for message in messages] == [
        "Hi! What can I get you?",
        "a latte",
        "One latte coming up.",
    ]


def test_build_voice_messages_without_overlap_appends_all():
    session = _session()
    payload = _voice_payload(
        VoiceConversationTurn(role="user", content="totally new line"),
    )
    messages = build_voice_messages(session, payload)
    assert [message.text for message in messages] == [
        "Hi! What can I get you?",
        "totally new line",
    ]


# —— 学员档案增强分支（读失败/写失败降级，visitor 门控）——


def test_profile_branch_visitor_session_skips_profile_query():
    # 若分支错误发起查询，抛错的仓储会直接炸掉用例——零查询即通过。
    branch = LearnerProfileBranch(_RaisingProfileRepository())
    visitor_session = _session(user_id="visitor:rotate-me")
    assert asyncio.run(branch.context_for_turn(visitor_session)) == (None, None)
    asyncio.run(branch.update_for_turn(visitor_session, _feedback()))


def test_profile_branch_update_for_turn_degrades_on_repository_failure(caplog):
    branch = LearnerProfileBranch(_RaisingProfileRepository())
    with caplog.at_level(logging.WARNING):
        asyncio.run(branch.update_for_turn(_session(), _feedback()))
    assert "learner_profile_update_failed" in caplog.text
    assert "degraded=true" in caplog.text


def test_profile_branch_context_returns_lines_and_cefr():
    profile = LearnerProfile(user_id="user:1", cefr_estimate="A2")
    branch = LearnerProfileBranch(_StubProfileRepository(profile))
    lines, cefr = asyncio.run(branch.context_for_turn(_session()))
    assert cefr == "A2"
    assert lines is not None


def test_profile_branch_context_degrades_to_none_on_read_failure(caplog):
    branch = LearnerProfileBranch(_RaisingProfileRepository())
    with caplog.at_level(logging.WARNING):
        context = asyncio.run(branch.context_for_turn(_session()))
    assert context == (None, None)
    assert "learner_profile_load_failed" in caplog.text
