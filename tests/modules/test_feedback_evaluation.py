"""反馈评测台 always-on 单测（G8-FEEDBACK-1，与 test_coach_evaluation.py 同构）。

覆盖：五维硬规则正反直测（结构封闭集合 / 引用保真 / grammar 文本形态 /
more_natural 形态 / useful_words 数量形态）、mock 输出全样例通道、prompt 哈希
稳定性、fixture 载入校验、折叠函数 graceful_failure 分支与 judge 结果注入、
runner 逐案落盘与 provider 兜底、user prompt 单一装配点。

本地 .env 是 live 模式：凡跑回复链路的测试必须显式 pin
settings.model_runtime_mode = "mock"（journal 2026-10-02 教训），禁止打真 LLM。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from api.core.config import settings
from api.modules.feedback_engine.agent import FeedbackEngineAgent
from api.modules.feedback_engine.evaluation import (
    FeedbackEvaluationCase,
    FeedbackJudgeResult,
    build_feedback_evaluation_input,
    build_feedback_prompt_hash,
    evaluate_feedback_result,
    evaluate_feedback_result_hard_checks,
    load_feedback_evaluation_cases,
    run_feedback_evaluation,
)
from api.modules.feedback_engine.prompts.feedback_prompts import (
    FEEDBACK_PROMPT,
    build_feedback_user_prompt,
)
from api.modules.feedback_engine.schema import (
    FeedbackErrorItem,
    FeedbackInput,
    FeedbackResult,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "feedback_eval_cases.json"

HARD_CHECK_FIELDS = (
    "structure_pass",
    "quote_fidelity_pass",
    "grammar_text_pass",
    "more_natural_pass",
    "useful_words_pass",
)

LEARNER_MESSAGE = "Yesterday I go to the coffee shop with my friend."


def _error(
    *,
    category: str = "tense",
    original: str = "Yesterday I go",
    correction: str = "Yesterday I went",
    explanation: str = "Use past tense for finished actions.",
) -> FeedbackErrorItem:
    return FeedbackErrorItem(
        category=category,
        original=original,
        correction=correction,
        explanation=explanation,
    )


def _feedback(**overrides) -> FeedbackResult:
    payload = {
        "errors": [_error()],
        "grammar": "Yesterday I go -> Yesterday I went (Use past tense for finished actions.)",
        "more_natural": "Yesterday I went to the coffee shop with my friend.",
        "useful_words": ["went", "yesterday", "met up"],
        "cefr_level": "A2",
    }
    payload.update(overrides)
    return FeedbackResult.model_validate(payload)


def _case() -> FeedbackEvaluationCase:
    return FeedbackEvaluationCase(
        case_id="office_b1_tense",
        scene="office",
        learner_message=LEARNER_MESSAGE,
        vocab_candidates=["meeting", "deadline", "schedule"],
    )


def _checks(feedback: FeedbackResult, learner_message: str | None = None):
    """快捷执行硬规则校验器。"""
    return evaluate_feedback_result_hard_checks(
        feedback=feedback, learner_message=learner_message or LEARNER_MESSAGE
    )


# —— 硬规则五维正反直测 ——


def test_structure_dimension_enforces_closed_set_and_bounds() -> None:
    """结构维度：九类封闭集合、≤3 条、字段非空、explanation 词数上限。"""
    assert _checks(_feedback()).structure_pass is True
    assert _checks(_feedback(errors=[])).structure_pass is True
    assert _checks(_feedback(errors=[_error(category="vocabulary")])).structure_pass is False
    assert (
        _checks(_feedback(errors=[_error(), _error(), _error(), _error()])).structure_pass is False
    )
    assert _checks(_feedback(errors=[_error(original="  ")])).structure_pass is False
    assert _checks(_feedback(errors=[_error(correction="")])).structure_pass is False
    long_explanation = " ".join(["word"] * 41)
    assert _checks(_feedback(errors=[_error(explanation=long_explanation)])).structure_pass is False
    assert (
        _checks(_feedback(errors=[_error(explanation=" ".join(["word"] * 40))])).structure_pass
        is True
    )


def test_quote_fidelity_dimension_requires_real_quotation() -> None:
    """引用保真维度：original 必须出自学习者原句（strip + 大小写不敏感）。"""
    assert _checks(_feedback()).quote_fidelity_pass is True
    # 大小写与首尾空白是正常引用形态，不误报。
    assert (
        _checks(_feedback(errors=[_error(original="  yesterday i go ")])).quote_fidelity_pass
        is True
    )
    assert (
        _checks(
            _feedback(errors=[_error(original="Yesterday I went to the cinema")])
        ).quote_fidelity_pass
        is False
    )


def test_grammar_text_dimension_bounds_lines_and_quotes() -> None:
    """grammar 维度：非空、≤320 字符；有错误时行数对齐且每条 original 在文本中。"""
    assert _checks(_feedback()).grammar_text_pass is True
    assert (
        _checks(
            _feedback(grammar="Your meaning is clear. Keep practicing!", errors=[])
        ).grammar_text_pass
        is True
    )
    assert _checks(_feedback(grammar="", errors=[])).grammar_text_pass is False
    long_text = "x" * 321
    assert _checks(_feedback(grammar=long_text, errors=[])).grammar_text_pass is False
    # 行数与错误数不对齐：两条错误只写一行。
    two_errors = [_error(), _error(original="to the coffee shop", correction="to the café")]
    assert _checks(_feedback(errors=two_errors)).grammar_text_pass is False
    # 引用缺席：行数对齐但 grammar 文本漏引第二条 original。
    aligned = (
        "Yesterday I go -> Yesterday I went (past tense)\n" "fixed the second issue (preposition)"
    )
    assert _checks(_feedback(errors=two_errors, grammar=aligned)).grammar_text_pass is False


def test_more_natural_dimension_bounds_sentences_and_script() -> None:
    """more_natural 维度：非空、≤2 句、仅英语。"""
    assert _checks(_feedback()).more_natural_pass is True
    two = "Yesterday I went to a coffee shop with my friend. We ordered lattes."
    assert _checks(_feedback(more_natural=two)).more_natural_pass is True
    assert _checks(_feedback(more_natural="")).more_natural_pass is False
    three = "One. Two. Three."
    assert _checks(_feedback(more_natural=three)).more_natural_pass is False
    cjk = "昨天我和朋友去了咖啡店。"
    assert _checks(_feedback(more_natural=cjk)).more_natural_pass is False


def test_useful_words_dimension_bounds_count_and_shape() -> None:
    """useful_words 维度：数量 ∈ [2,4]、每项 1-4 个英文 token。"""
    assert _checks(_feedback()).useful_words_pass is True
    assert _checks(_feedback(useful_words=["went", "met up with"])).useful_words_pass is True
    assert _checks(_feedback(useful_words=["went"])).useful_words_pass is False
    assert _checks(_feedback(useful_words=["a", "b", "c", "d", "e"])).useful_words_pass is False
    assert (
        _checks(_feedback(useful_words=["a four word phrase here", "ok"])).useful_words_pass
        is False
    )
    assert _checks(_feedback(useful_words=["拿铁", "latte"])).useful_words_pass is False


def test_hard_pass_aggregates_all_dimensions() -> None:
    """hard_pass 聚合：任一维度失败即失败；failure_reasons 按声明序给出标签。"""
    checks = _checks(_feedback())
    assert checks.hard_pass is True
    assert checks.failure_reasons == []
    broken = _checks(_feedback(useful_words=["only-one"]))
    assert broken.hard_pass is False
    assert broken.failure_reasons == ["useful_words violate the count/shape contract"]


# —— prompt 哈希与单一装配点 ——


def test_prompt_hash_stable_and_binds_system_prompt() -> None:
    """反馈系统提示词是常量：同模板哈希稳定、12 位、与模板内容绑定。"""
    import hashlib

    assert build_feedback_prompt_hash() == build_feedback_prompt_hash()
    assert len(build_feedback_prompt_hash()) == 12
    expected = hashlib.sha256(FEEDBACK_PROMPT.encode("utf-8")).hexdigest()[:12]
    assert build_feedback_prompt_hash() == expected


def test_user_prompt_assembly_matches_live_contract_with_and_without_context() -> None:
    """user prompt 装配点：Scene 首行、注入块随后、vocab/message/收尾行序固定。"""
    payload = FeedbackInput(
        learner_message=LEARNER_MESSAGE,
        scene="office",
        vocab_candidates=["meeting", "deadline"],
        learner_context="Learner profile: estimated CEFR B1.",
    )
    lines = build_feedback_user_prompt(payload).splitlines()
    assert lines[0] == "Scene: office"
    assert lines[1] == "Learner profile: estimated CEFR B1."
    assert lines[2] == "Vocab candidates: meeting, deadline"
    assert lines[3] == f"Learner message: {LEARNER_MESSAGE}"
    assert lines[-1].startswith("Return strict JSON")
    # 无注入块：装配逐字节回落历史形态（不产生空行）。
    plain = build_feedback_user_prompt(
        FeedbackInput(learner_message=LEARNER_MESSAGE, scene="office")
    )
    assert "\n\n" not in plain
    assert plain.splitlines()[1] == "Vocab candidates: none"


# —— fixture 载入校验 ——


def test_fixture_loads_with_matrix_and_mock_channel_constraints() -> None:
    """fixture 约束锁定：8 案、4 场景、vocab 形态（0 或 2-4 项短英文短语）。"""
    cases = load_feedback_evaluation_cases(FIXTURE_PATH)
    assert len(cases) == 8
    assert {case.scene for case in cases} == {"coffee_shop", "office", "travel", "restaurant"}
    assert len({case.case_id for case in cases}) == len(cases)
    for case in cases:
        assert len(case.vocab_candidates) == 0 or 2 <= len(case.vocab_candidates) <= 4
        for word in case.vocab_candidates:
            assert 1 <= len(word.split()) <= 4
        assert case.learner_message.strip() == case.learner_message


def test_mock_channel_passes_hard_checks_for_all_fixtures(monkeypatch) -> None:
    """mock 输出全样例通道：always-on 回归网（零模型调用）。

    必须显式 pin mock——本地 .env 是 live 模式；fixture 约束（vocab 0/2-4 项、
    学习者消息 ≤2 句）保证 mock 反馈五维全过。
    """
    monkeypatch.setattr(settings, "model_runtime_mode", "mock")
    agent = FeedbackEngineAgent()
    for case in load_feedback_evaluation_cases(FIXTURE_PATH):
        feedback = asyncio.run(agent.run(build_feedback_evaluation_input(case)))
        checks = _checks(feedback, learner_message=case.learner_message)
        assert checks.hard_pass, f"{case.case_id}: {checks.failure_reasons} :: {feedback}"


# —— 折叠函数 ——


def test_evaluate_folds_reply_with_hard_checks_and_hash() -> None:
    """reply 折叠：硬规则逐项透传、judge 缺席时 final_pass 回落 hard_pass。"""
    result = evaluate_feedback_result(
        case=_case(),
        feedback=_feedback(),
        actual_outcome="reply",
        prompt_hash="abc123def456",
        judge_result=None,
    )
    assert result.case_id == "office_b1_tense"
    assert result.hard_pass is True
    assert result.final_pass is True
    assert result.judge_result is None
    assert result.judge_error is None
    assert result.actual_outcome == "reply"
    assert result.failure_reason == ""
    assert result.prompt_hash == "abc123def456"
    assert result.learner_context_present is False
    assert result.raw_output["cefr_level"] == "A2"


def test_evaluate_folds_graceful_failure_as_visible_failure() -> None:
    """graceful_failure：硬规则全 False、final_pass=False——通过率显形不丢样本。"""
    result = evaluate_feedback_result(
        case=_case(),
        feedback=None,
        actual_outcome="graceful_failure",
        prompt_hash="abc123def456",
        judge_result=None,
        failure_reason="graceful_failure: timeout",
    )
    assert result.actual_outcome == "graceful_failure"
    assert result.final_pass is False
    assert result.hard_pass is False
    assert all(not getattr(result, field) for field in HARD_CHECK_FIELDS)
    assert result.failure_reason == "graceful_failure: timeout"
    assert result.raw_output is None


def test_evaluate_applies_judge_veto_and_normalizes_dict() -> None:
    """judge 注入：dict 归一为模型；judge 否决 → final_pass=False 且 reason 取 judge。"""
    judge = {
        "final_pass": False,
        "correction_accuracy_pass": True,
        "naturalness_pass": False,
        "usefulness_pass": True,
        "reason": "rewrite is not more natural",
    }
    result = evaluate_feedback_result(
        case=_case(),
        feedback=_feedback(),
        actual_outcome="reply",
        prompt_hash="abc123def456",
        judge_result=judge,
    )
    assert isinstance(result.judge_result, dict)
    assert result.final_pass is False
    assert result.failure_reason == "rewrite is not more natural"
    # judge 通过 → final_pass 跟随 hard_pass。
    passing = evaluate_feedback_result(
        case=_case(),
        feedback=_feedback(),
        actual_outcome="reply",
        prompt_hash="abc123def456",
        judge_result=FeedbackJudgeResult(
            final_pass=True,
            correction_accuracy_pass=True,
            naturalness_pass=True,
            usefulness_pass=True,
            reason="ok",
        ),
    )
    assert passing.final_pass is True


def test_evaluate_requires_feedback_on_reply_outcome() -> None:
    with pytest.raises(ValueError, match="feedback is required"):
        evaluate_feedback_result(
            case=_case(),
            feedback=None,
            actual_outcome="reply",
            prompt_hash="x",
            judge_result=None,
        )


# —— judge 构造 ——


def test_judge_from_env_returns_none_for_mock_provider(monkeypatch) -> None:
    """provider 为 mock（或缺省回落 mock）时 judge 缺席：评测仍可跑，只缺 judge 维度。"""
    from api.modules.feedback_engine.evaluation import FeedbackJudge

    monkeypatch.setattr(settings, "text_primary_provider", "mock")
    assert FeedbackJudge.from_env() is None


def test_judge_from_env_builds_client_with_env_overrides(monkeypatch) -> None:
    from api.modules.feedback_engine.evaluation import FeedbackJudge

    monkeypatch.setenv("FEEDBACK_EVAL_JUDGE_PROVIDER", "openai")
    monkeypatch.setenv("FEEDBACK_EVAL_JUDGE_BASE_URL", "https://judge.example/v1")
    monkeypatch.setenv("FEEDBACK_EVAL_JUDGE_API_KEY", "judge-key")
    monkeypatch.setenv("FEEDBACK_EVAL_JUDGE_MODEL", "judge-model")
    judge = FeedbackJudge.from_env()
    assert judge is not None


# —— runner ——


class _CannedJsonProvider:
    """按案构造合法反馈 JSON 的假 provider（always-on 通道，零模型调用）。

    引用保真维度逐案绑定学习者消息：从 user prompt 解析 Learner message 行，
    引用其前两个 token 作为 original——保证八案全部过五维硬规则。
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append(user_prompt)
        assert system_prompt == FEEDBACK_PROMPT
        learner_line = next(
            line for line in user_prompt.splitlines() if line.startswith("Learner message: ")
        )
        learner = learner_line.removeprefix("Learner message: ")
        quoted = " ".join(learner.split()[:2])
        more_natural = learner if learner.endswith((".", "?", "!")) else f"{learner}."
        return json.dumps(
            {
                "errors": [
                    {
                        "category": "other",
                        "original": quoted,
                        "correction": quoted,
                        "explanation": "Placeholder fix for the replay channel.",
                    }
                ],
                "grammar": f"{quoted} -> {quoted} (Placeholder fix for the replay channel.)",
                "more_natural": more_natural,
                "useful_words": ["went", "yesterday", "met up"],
                "cefr_level": "A2",
            }
        )


class _ExplodingProvider:
    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("provider down")


@pytest.mark.anyio
async def test_runner_replays_all_cases_with_incremental_jsonl(tmp_path) -> None:
    """runner 逐案折叠并整文件重放落盘：中断时已完成样本不丢（落盘行数单调）。"""
    output_file = tmp_path / "results.jsonl"
    cases = load_feedback_evaluation_cases(FIXTURE_PATH)
    provider = _CannedJsonProvider()
    results = await run_feedback_evaluation(
        cases=cases,
        output_path=output_file,
        text_provider=provider,  # type: ignore[arg-type]
    )
    assert len(results) == len(cases) == len(provider.calls)
    assert all(result.hard_pass for result in results)
    assert all(result.final_pass for result in results)
    assert all(result.actual_outcome == "reply" for result in results)
    written = output_file.read_text(encoding="utf-8").splitlines()
    assert len(written) == len(cases)
    assert json.loads(written[0])["case_id"] == cases[0].case_id
    assert json.loads(written[-1])["case_id"] == cases[-1].case_id


@pytest.mark.anyio
async def test_runner_records_graceful_failure_on_provider_error(tmp_path) -> None:
    """provider 异常被兜住：产出 graceful_failure 行而不是炸掉整批评测。"""
    results = await run_feedback_evaluation(
        cases=load_feedback_evaluation_cases(FIXTURE_PATH)[:2],
        output_path=tmp_path / "results.jsonl",
        text_provider=_ExplodingProvider(),  # type: ignore[arg-type]
    )
    assert len(results) == 2
    assert all(result.actual_outcome == "graceful_failure" for result in results)
    assert all(result.final_pass is False for result in results)
    assert all("provider down" in result.failure_reason for result in results)
