"""复盘评测台 always-on 单测（design.md 5.1）。

覆盖：五维硬规则正反直测（含 scene id 变体 / 非预设场景 id 全变体）、结构契约
经真实 ReviewCopy.model_validate 路径的反向断言、prompt 哈希稳定性与敏感性、
fixture 载入校验、折叠函数 graceful_failure 分支。纯硬规则无网络调用。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.session_engine.evaluation import (
    ReviewCopyHardChecks,
    ReviewEvaluationCase,
    build_review_prompt_hash,
    evaluate_review_copy,
    evaluate_review_output,
    load_review_evaluation_cases,
)
from api.modules.session_engine.prompts.review_prompts import REVIEW_PROMPT
from api.modules.session_engine.review_builder import SCENE_COPY, ReviewCopy

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "review_eval_cases.json"

CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}
ERROR_CATEGORIES = {
    "grammar",
    "tense",
    "article",
    "preposition",
    "word_choice",
    "collocation",
    "register",
    "spelling",
    "other",
}


def _copy(**overrides: str) -> ReviewCopy:
    """合成一份五维全合规的中文复盘文案，单个测试只覆写需要违反的维度。"""
    fields = {
        "scene_title": "咖啡店柜台点单",
        "role_label": "店员对话",
        "highlight": "你把点单的主需求说清楚了，表达很完整。",
        "next_try": "下一轮先说主需求，再补一条口味或杯型细节。",
        "next_step": "下一轮试着在句尾加一句礼貌用语。",
    }
    fields.update(overrides)
    return ReviewCopy.model_validate(fields)


def _case(**overrides) -> ReviewEvaluationCase:
    """合成一组最小合规评测用例，单个测试只覆写需要变化的键。"""
    payload = {
        "case_id": "case-1",
        "scene": "coffee_shop",
        "role": "barista",
        "learner_message": "I want order a iced latte.",
        "feedback": FeedbackResult(
            grammar="I want order -> I would like to order",
            more_natural="Could I get an iced latte, please?",
            useful_words=["would like", "iced latte"],
            errors=[],
            cefr_level="B1",
        ),
        "unrelated_topic_keywords": ["问路", "地铁", "面试", "简历"],
    }
    payload.update(overrides)
    return ReviewEvaluationCase.model_validate(payload)


def test_chinese_dimension_flags_any_non_chinese_field() -> None:
    """中文维度：五个字段各至少 1 个 CJK 字符，任一字段纯英文即判反。"""
    checks = evaluate_review_copy(case=_case(), copy=_copy())
    assert checks.chinese_pass is True

    english_field = evaluate_review_copy(
        case=_case(),
        copy=_copy(next_try="Try to add a polite phrase at the end."),
    )
    assert english_field.chinese_pass is False
    assert "without Chinese characters" in english_field.failure_reasons[0]


def test_length_dimension_matches_review_prompt_soft_bounds() -> None:
    """长度维度逐字段对齐 REVIEW_PROMPT 软约束 40/40/120/80/80（含恰好达界）。

    生产 ReviewCopy validator 已按 cap 截断（eval_prompt_fixes 批次 design 2.3）：
    经 model_validate 构造的对象不可能超限，超限对象只能用 model_construct 绕过
    校验构造——长度维度由此退化为"生产护栏未被移除"的回归哨兵：若有人移除生产
    截断 validator，live 评测在此显形。
    """
    within = evaluate_review_copy(
        case=_case(),
        copy=_copy(scene_title="咖" * 40, highlight="好" * 120, next_step="下" * 80),
    )
    assert within.length_pass is True

    base = {
        "scene_title": "咖" * 40,
        "role_label": "店" * 40,
        "highlight": "好" * 120,
        "next_try": "试" * 80,
        "next_step": "步" * 80,
    }
    for field, over_value in (
        ("scene_title", "咖" * 41),
        ("highlight", "好" * 121),
        ("next_try", "试" * 81),
    ):
        over_copy = ReviewCopy.model_construct(**{**base, field: over_value})
        over_checks = evaluate_review_copy(case=_case(), copy=over_copy)
        assert over_checks.length_pass is False, field


def test_no_scene_id_dimension_covers_all_identifier_variants() -> None:
    """id 泄漏维度：原始串、下划线↔空格变体、大小写不敏感全部判反。"""
    nonpreset_clean = evaluate_review_copy(
        case=_case(scene="gym", role="fitness coach"),
        copy=_copy(scene_title="健身房力量训练", role_label="教练指导"),
    )
    assert nonpreset_clean.no_scene_id_pass is True

    # 非预设场景 id 全变体：裸 id、首字母大写、空格变体都算泄漏（gym 无下划线）。
    for title in ("Gym 情景对话", "gym 力量训练"):
        leaked = evaluate_review_copy(
            case=_case(scene="gym", role="fitness coach"),
            copy=_copy(scene_title=title, role_label="教练指导"),
        )
        assert leaked.no_scene_id_pass is False

    # 预设场景：原始下划线串与空格变体均判反，纯中文标题通过。
    assert evaluate_review_copy(case=_case(), copy=_copy()).no_scene_id_pass is True
    for title in ("coffee_shop 柜台", "Coffee Shop 柜台点单"):
        leaked = evaluate_review_copy(case=_case(), copy=_copy(scene_title=title))
        assert leaked.no_scene_id_pass is False

    role_leak = evaluate_review_copy(case=_case(), copy=_copy(role_label="Barista 服务"))
    assert role_leak.no_scene_id_pass is False


def test_topic_grounding_dimension_flags_unrelated_keywords() -> None:
    """无关话题维度：跨域关键词出现在任一字段即判编造，干净文案通过。"""
    leak = evaluate_review_copy(
        case=_case(unrelated_topic_keywords=["面试"]),
        copy=_copy(highlight="你为面试做的准备很充分，表达清晰。"),
    )
    assert leak.topic_grounding_pass is False

    clean = evaluate_review_copy(
        case=_case(unrelated_topic_keywords=["面试", "简历"]),
        copy=_copy(),
    )
    assert clean.topic_grounding_pass is True


def test_structure_contract_is_enforced_by_real_validation_path() -> None:
    """结构维度的反向断言走真实链路：缺键 / 空串 / 纯空白在 model_validate 即被拒。"""
    with pytest.raises(ValidationError):
        ReviewCopy.model_validate({"scene_title": "咖啡店", "role_label": "店员"})
    with pytest.raises(ValidationError):
        ReviewCopy.model_validate(
            {
                "scene_title": "咖啡店柜台点单",
                "role_label": "店员对话",
                "highlight": "   ",
                "next_try": "下一轮先说主需求。",
                "next_step": "下一轮试着补一句细节。",
            }
        )
    # 校验器收到的必然是已验证对象：structure_pass 在校验器内恒为 True。
    checks: ReviewCopyHardChecks = evaluate_review_copy(case=_case(), copy=_copy())
    assert checks.structure_pass is True


def test_review_prompt_hash_stable_and_sensitive() -> None:
    """哈希稳定性（同输入同值）与敏感性（提示词一改哈希即变）。"""
    base = build_review_prompt_hash()
    assert base == hashlib.sha256(REVIEW_PROMPT.encode("utf-8")).hexdigest()[:12]
    assert build_review_prompt_hash(REVIEW_PROMPT) == base
    assert build_review_prompt_hash(f"{REVIEW_PROMPT}\nExtra rule.") != base
    assert len(base) == 12


def test_review_prompt_demands_natural_chinese_display_names_and_bans_role_id() -> None:
    """展示名消费后（review-copy-consumption）的提示词子句 always-on 断言。

    scene_title / role_label 已进入生产消费（LLM 值优先）：提示词必须继续要求
    自然中文、禁止输出原始 role id（此前 role id 禁令未显式覆盖 role_label），
    并禁止编造给定场景与角色之外的画面外内容——这些子句是消费侧 resolver
    字段级回退之前的第一道防线，措辞回退（放松语义）会被这里拦下。
    """
    assert "must be natural Chinese" in REVIEW_PROMPT
    assert "base it on the given scene" in REVIEW_PROMPT
    assert "base it on the given coach role" in REVIEW_PROMPT
    assert "never output the raw scene id or role id" in REVIEW_PROMPT
    assert "never output the raw role id or scene id" in REVIEW_PROMPT
    assert "Do not invent scenery, characters, or events beyond the given scene and role." in (
        REVIEW_PROMPT
    )


def test_fixture_load_contract() -> None:
    """fixture 载入校验：案例数、场景矩阵、feedback 契约与黑名单约束全部锁定。"""
    cases = load_review_evaluation_cases(FIXTURE_PATH)

    assert len(cases) >= 5
    assert len({case.case_id for case in cases}) == len(cases)

    preset_scenes = {"coffee_shop", "office", "travel", "restaurant"}
    scenes = {case.scene for case in cases}
    assert preset_scenes <= scenes
    # 非预设场景组真实存在（不在 SCENE_COPY 内），专测 id 回退路径。
    non_preset = scenes - preset_scenes
    assert non_preset
    assert all(case.scene not in SCENE_COPY for case in cases if case.scene in non_preset)

    # feedback 全字段覆盖：errors 案例数达标、9 类封闭分类全取样、cefr 全在集合内。
    with_errors = [case for case in cases if case.feedback.errors]
    assert len(with_errors) >= 2
    sampled_categories = {error.category for case in cases for error in case.feedback.errors}
    assert sampled_categories == ERROR_CATEGORIES
    for case in cases:
        assert case.feedback.cefr_level in CEFR_LEVELS
        assert case.feedback.grammar.strip()
        assert case.feedback.more_natural.strip()
        assert case.feedback.useful_words
        assert 3 <= len(case.unrelated_topic_keywords) <= 5

    # 防误报约束：预设场景的黑名单词不得出现在该场景预设文案里（live 评测会
    # 自然产出预设词面的文案），否则 topic_grounding 维度必然假阳性。
    for case in cases:
        if case.scene in SCENE_COPY:
            preset_surface = "".join(str(value) for value in SCENE_COPY[case.scene].values())
            assert not any(keyword in preset_surface for keyword in case.unrelated_topic_keywords)


def test_evaluate_review_output_happy_path_records_metadata() -> None:
    """折叠正常分支：五维布尔、copy 落行、final_pass 与 failure_reason 语义。"""
    case = _case()
    copy = _copy()
    result = evaluate_review_output(
        case=case,
        copy=copy,
        actual_outcome="copy",
        prompt_hash="hash-123",
    )

    assert result.case_id == "case-1"
    assert result.prompt_hash == "hash-123"
    assert result.actual_outcome == "copy"
    assert result.raw_output == copy.model_dump()
    assert result.review_copy == copy.model_dump()
    assert result.hard_pass is True
    assert result.final_pass is True
    assert result.failure_reason == ""


def test_evaluate_review_output_first_failure_reason_wins() -> None:
    """多维度同时失败时取声明序首个原因（structure > chinese > length > id > topic）。"""
    result = evaluate_review_output(
        case=_case(unrelated_topic_keywords=["面试"]),
        # role_label 纯英文：chinese 判反且 "barista" 角色 id 泄漏；highlight 带
        # 黑名单词。声明序上 chinese 在前，折叠层必须取它。
        copy=_copy(role_label="Barista", highlight="面试准备很充分。"),
        actual_outcome="copy",
        prompt_hash="hash-123",
    )

    assert result.hard_pass is False
    assert result.final_pass is False
    assert result.failure_reason == "review copy contains a field without Chinese characters"


def test_evaluate_review_output_graceful_failure_branch() -> None:
    """折叠失败分支：五维全 False、final_pass=False、copy/raw_output 为空。"""
    result = evaluate_review_output(
        case=_case(),
        copy=None,
        actual_outcome="graceful_failure",
        prompt_hash="hash-404",
        failure_reason="graceful_failure: all providers failed",
    )

    assert result.actual_outcome == "graceful_failure"
    assert result.raw_output is None
    assert result.review_copy is None
    for name in (
        "structure_pass",
        "chinese_pass",
        "length_pass",
        "no_scene_id_pass",
        "topic_grounding_pass",
    ):
        assert getattr(result, name) is False
    assert result.hard_pass is False
    assert result.final_pass is False
    assert result.failure_reason == "graceful_failure: all providers failed"


def test_evaluate_review_output_requires_copy_on_copy_outcome() -> None:
    """actual_outcome="copy" 却缺 copy 是调用方 bug：显式报错而非静默折叠。"""
    with pytest.raises(ValueError, match="copy is required"):
        evaluate_review_output(
            case=_case(),
            copy=None,
            actual_outcome="copy",
            prompt_hash="hash-123",
        )
