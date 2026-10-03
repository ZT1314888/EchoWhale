"""教练评测台 always-on 单测（design.md 5.1）。

覆盖：五维硬规则正反直测（no_echo 含 <4 token 豁免与 4 token 边界）、mock 输出
全样例通道、prompt 哈希稳定性/敏感性与逐案绑定、fixture 载入校验、折叠函数
graceful_failure 分支与 judge 结果注入。

本地 .env 是 live 模式：凡跑回复链路的测试必须显式 pin
settings.model_runtime_mode = "mock"（journal 2026-10-02 教训），禁止打真 LLM。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api.core.config import settings
from api.modules.coach_engine.evaluation import (
    CoachJudgeResult,
    CoachReplyEvaluationCase,
    build_coach_prompt_hash,
    build_coach_reply_input,
    evaluate_coach_reply,
    evaluate_coach_reply_hard_checks,
    load_coach_evaluation_cases,
)
from api.modules.coach_engine.prompts.coach_prompts import build_coach_system_prompt
from api.modules.coach_engine.providers.chat_provider import MockChatProvider

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "coach_eval_cases.json"

HARD_CHECK_FIELDS = (
    "english_only_pass",
    "length_pass",
    "follow_up_pass",
    "meta_leak_pass",
    "no_echo_pass",
)


def _learner_message() -> str:
    """默认学习者消息：10 个 token，no_echo 维度的负样本要以它为基准。"""
    return "I would like to order a latte with extra foam please"


def _checks(reply_text: str, learner_message: str | None = None):
    """快捷执行硬规则校验器。"""
    return evaluate_coach_reply_hard_checks(
        reply_text=reply_text, learner_message=learner_message or _learner_message()
    )


def test_english_only_dimension_flags_cjk_hangul_kana() -> None:
    """仅英语维度：CJK / 谚文 / 假名任一字符出现即判反。"""
    assert _checks("Great progress! Would you like to try a short role-play?").english_only_pass
    for bad_text in (
        "做得好！Would you like to try again?",
        "잘했어요! Would you like to try again?",
        "がんばって! Would you like to try again?",
    ):
        assert _checks(bad_text).english_only_pass is False


def test_length_dimension_bounds_word_count() -> None:
    """长度维度：词数 <= 80 且非空；81 词判反，空串判反。"""
    assert _checks("Nice work! Would you like to try one more round?").length_pass is True
    assert _checks(" ".join(["word"] * 80) + "?").length_pass is True
    assert _checks(" ".join(["word"] * 81) + "?").length_pass is False
    assert _checks("").length_pass is False


def test_follow_up_dimension_requires_exactly_one_question_mark() -> None:
    """追问维度：'?' 恰好 1 个——存在且不叠加（提示词 one follow-up question）。"""
    assert _checks("Nice order! Would you like it hot or iced?").follow_up_pass is True
    assert _checks("Sure thing. No question in this reply.").follow_up_pass is False
    assert _checks("Hot or iced? And maybe a muffin too?").follow_up_pass is False


def test_meta_leak_dimension_flags_ai_self_disclosure() -> None:
    """meta 泄漏维度：黑名单覆盖场景台思路的教练侧扩展副本，大小写不敏感。"""
    assert _checks("Great choice! Shall we practice greetings first?").meta_leak_pass is True
    for bad_text in (
        "As an AI, I would start with greetings?",
        "As a language model, I suggest ordering first?",
        "I am an AI coach, and today we practice?",
        "I'm an AI, so let me model the dialogue?",
        "I cannot see the image, but from the anchors?",
        "I can't see the image clearly, yet we can try?",
        "This image shows a counter, shall we practice?",
    ):
        assert _checks(bad_text).meta_leak_pass is False, bad_text


def test_no_echo_dimension_matches_contiguous_token_sequence() -> None:
    """复读维度：学习者整句（>=4 token）作为连续子序列复现才判反。"""
    echoed = "I would like to order a latte with extra foam please. What size would you like?"
    assert _checks(echoed).no_echo_pass is False

    # 只复用零散词（话题词、短语片段）不构成整句复读，不误报。
    paraphrased = "Great pick! A latte with extra foam is a classic. What size would you like?"
    assert _checks(paraphrased).no_echo_pass is True


def test_no_echo_dimension_exempts_short_learner_messages() -> None:
    """短句豁免：<4 token 的应答（"yes please"）在回复中自然复现不算复读。"""
    two_tokens = _checks(
        "Yes please works perfectly. Ready to order something bigger?", "Yes please"
    )
    assert two_tokens.no_echo_pass is True
    # 边界：恰好 3 个 token 仍豁免，4 个 token 起整句复现即判反。
    three_tokens = _checks("Please give me that muffin. Anything else?", "give me that")
    assert three_tokens.no_echo_pass is True
    four_tokens = _checks(
        "Please give me that. Anything else for the table?", "please give me that"
    )
    assert four_tokens.no_echo_pass is False


@pytest.mark.anyio
async def test_mock_channel_passes_hard_checks_for_all_fixtures(monkeypatch) -> None:
    """mock 输出全样例通道：always-on 回归网。

    必须显式 pin mock——本地 .env 是 live 模式；fixture 约束（recent_messages
    末条非空、异于学习者原句、无问号）保证 mock 回复五维全过。
    """
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    provider = MockChatProvider()
    cases = load_coach_evaluation_cases(FIXTURE_PATH)

    for case in cases:
        result = await provider.reply(build_coach_reply_input(case))
        checks = evaluate_coach_reply_hard_checks(
            reply_text=result.text, learner_message=case.learner_message
        )
        assert checks.hard_pass, f"{case.case_id}: {checks.failure_reasons} :: {result.text}"


def test_prompt_hash_stable_sensitive_and_binds_per_case_system_prompt() -> None:
    """哈希绑定每组实际发送的系统提示词：B1/B2 天然不同；同输入稳定、异输入不同。"""
    b1_hash = build_coach_prompt_hash(build_coach_system_prompt("B1"))
    b2_hash = build_coach_prompt_hash(build_coach_system_prompt("B2"))

    assert b1_hash != b2_hash
    assert b1_hash == build_coach_prompt_hash(build_coach_system_prompt("B1"))
    assert build_coach_prompt_hash("x") != build_coach_prompt_hash("y")
    assert len(b1_hash) == 12


def test_fixture_load_contract() -> None:
    """fixture 载入校验：案例数、场景 x CEFR 矩阵与 mock 通道前提约束全部锁定。"""
    cases = load_coach_evaluation_cases(FIXTURE_PATH)

    assert len(cases) >= 8
    assert len({case.case_id for case in cases}) == len(cases)
    assert {"coffee_shop", "office", "restaurant", "travel"} <= {case.scene for case in cases}
    cefrs = {case.learner_cefr for case in cases}
    assert {"B1", "B2"} <= cefrs

    for case in cases:
        assert case.learner_message.strip()
        # mock 回复引用 recent_messages[-1].text：末条必须存在、不等于学习者
        # 原句（no_echo 维度）且不含问号（mock 追问恰好 1 个的前提）。
        assert case.recent_messages
        assert case.recent_messages[-1].text != case.learner_message
        assert "?" not in case.recent_messages[-1].text
        assert all(message.role in {"user", "assistant"} for message in case.recent_messages)
        assert case.learner_cefr in {"B1", "B2", None}

    # design.md 4.1 覆盖矩阵：B1 与 B2 各带 1 组 learner_context 注入块、
    # recent_messages 多轮 >=4 条、anchors/vocab 双空回退分支。
    assert any(case.learner_context and case.learner_cefr == "B1" for case in cases)
    assert any(case.learner_context and case.learner_cefr == "B2" for case in cases)
    assert any(len(case.recent_messages) >= 4 for case in cases)
    assert any(not case.visual_anchors and not case.vocab_candidates for case in cases)
    # 注入块必须保持服务端渲染形态（build_learner_context_lines 的行前缀）。
    for case in cases:
        if case.learner_context:
            assert all(
                line.startswith("Learner profile:") for line in case.learner_context.splitlines()
            )


def _fold_case() -> CoachReplyEvaluationCase:
    return CoachReplyEvaluationCase(
        case_id="fold-1",
        scene="coffee_shop",
        role="barista",
        learner_message="I would like to order a latte",
    )


GOOD_REPLY = "Nice choice! A latte is a classic pick. Would you like it hot or iced?"


def test_evaluate_coach_reply_happy_path_records_metadata() -> None:
    """折叠正常分支：五维布尔、judge dict 归一、元数据落行。"""
    result = evaluate_coach_reply(
        case=_fold_case(),
        reply_text=GOOD_REPLY,
        actual_outcome="reply",
        prompt_hash="hash-123",
        judge_result={
            "final_pass": True,
            "role_fit_pass": True,
            "cefr_fit_pass": True,
            "stretch_pass": True,
            "reason": "on-role and level-appropriate",
        },
    )

    assert result.prompt_hash == "hash-123"
    assert result.raw_output == {"text": GOOD_REPLY}
    assert result.learner_context_present is False
    assert result.actual_outcome == "reply"
    assert result.hard_pass is True
    assert result.judge_result is not None
    assert result.judge_result["final_pass"] is True
    assert result.final_pass is True
    assert result.failure_reason == ""


def test_evaluate_coach_reply_normalizes_judge_model_instance() -> None:
    """judge 结果以 CoachJudgeResult 实例传入时同样归一落行（runner to_thread 形态）。"""
    result = evaluate_coach_reply(
        case=_fold_case(),
        reply_text=GOOD_REPLY,
        actual_outcome="reply",
        prompt_hash="hash-123",
        judge_result=CoachJudgeResult(
            final_pass=True,
            role_fit_pass=True,
            cefr_fit_pass=True,
            stretch_pass=False,
            reason="no stretch",
        ),
    )

    assert result.judge_result is not None
    assert result.judge_result["stretch_pass"] is False
    # 硬规则全过且 judge.final_pass=True：stretch 只是子维度，不单独否决。
    assert result.final_pass is True


def test_evaluate_coach_reply_failing_judge_blocks_final_pass() -> None:
    """judge 否决时 final_pass=False 且 failure_reason 取 judge reason。"""
    result = evaluate_coach_reply(
        case=_fold_case(),
        reply_text=GOOD_REPLY,
        actual_outcome="reply",
        prompt_hash="hash-123",
        judge_result={
            "final_pass": False,
            "role_fit_pass": False,
            "cefr_fit_pass": True,
            "stretch_pass": True,
            "reason": "reply is off-role",
        },
    )

    assert result.hard_pass is True
    assert result.final_pass is False
    assert result.failure_reason == "reply is off-role"


def test_evaluate_coach_reply_first_hard_failure_reason_wins() -> None:
    """硬规则先于 judge：首个失败维度按声明序给出原因。"""
    result = evaluate_coach_reply(
        case=_fold_case(),
        reply_text="做得好。No question here.",
        actual_outcome="reply",
        prompt_hash="hash-123",
        judge_result={
            "final_pass": False,
            "role_fit_pass": False,
            "cefr_fit_pass": False,
            "stretch_pass": False,
            "reason": "reply is off-role",
        },
    )

    assert result.hard_pass is False
    assert result.final_pass is False
    assert result.failure_reason == "reply is not English only"


def test_evaluate_coach_reply_graceful_failure_branch() -> None:
    """折叠失败分支：五维全 False、final_pass=False、raw_output 为空。"""
    result = evaluate_coach_reply(
        case=_fold_case(),
        reply_text=None,
        actual_outcome="graceful_failure",
        prompt_hash="hash-404",
        judge_result=None,
        failure_reason="graceful_failure: provider exploded",
    )

    assert result.actual_outcome == "graceful_failure"
    assert result.raw_output is None
    for name in HARD_CHECK_FIELDS:
        assert getattr(result, name) is False
    assert result.hard_pass is False
    assert result.judge_result is None
    assert result.final_pass is False
    assert result.failure_reason == "graceful_failure: provider exploded"


def test_evaluate_coach_reply_requires_reply_text_on_reply_outcome() -> None:
    """actual_outcome="reply" 却缺回复文本是调用方 bug：显式报错而非静默折叠。"""
    with pytest.raises(ValueError, match="reply_text is required"):
        evaluate_coach_reply(
            case=_fold_case(),
            reply_text=None,
            actual_outcome="reply",
            prompt_hash="hash-123",
            judge_result=None,
        )
