"""review_builder 展示名解析器与单源防护直测（review-copy-consumption Phase A）。

覆盖：resolve_scene_title / resolve_role_label 的优先级矩阵（LLM 有效/None/
空白/超长/含泄漏 × 已知/未知场景）、字段级独立性、no-raw-id 负向断言、
scene_display_fallback warning 观测、contains_identifier_variant 单源语义、
llm=None 时与确定性路径逐字节一致的回归。
"""

from __future__ import annotations

import logging

from api.modules.session_engine.review_builder import (
    REVIEW_COPY_MAX_CHARS,
    SCENE_COPY,
    contains_identifier_variant,
    get_role_label,
    get_scene_title,
    identifier_variants,
    resolve_role_label,
    resolve_scene_title,
)

LOGGER_NAME = "api.modules.session_engine.review_builder"


def _assert_no_identifier_leak(value: str, *identifiers: str) -> None:
    """负向断言：输出不得包含任何原始 id 变体（大小写不敏感子串）。"""
    lowered = value.lower()
    for identifier in identifiers:
        for variant in identifier_variants(identifier):
            assert variant not in lowered, f"leaked variant {variant!r} in {value!r}"


# ---------- resolve_scene_title 优先级矩阵 ----------


def test_resolve_scene_title_consumes_valid_llm_value() -> None:
    """有效 LLM 值（非空 ≤cap 无泄漏）直接消费：已知与未知场景同矩阵。"""
    assert resolve_scene_title("coffee_shop", "barista", "咖啡馆柜台点单") == "咖啡馆柜台点单"
    assert resolve_scene_title("gym", "fitness coach", "健身房力量训练") == "健身房力量训练"


def test_resolve_scene_title_none_matches_deterministic_path_byte_for_byte() -> None:
    """llm=None（mock/降级/旧行）静默走确定性路径，输出逐字节一致。"""
    for scene, role in (("coffee_shop", "barista"), ("gym", "fitness coach"), ("gym", None)):
        assert resolve_scene_title(scene, role, None) == get_scene_title(scene, role)
    # 已知场景断言值用 SCENE_COPY 实际文案，防止预设漂移被测试掩盖。
    assert resolve_scene_title("coffee_shop", "barista", None) == "咖啡店柜台点单"
    # 未知场景走 humanize 组合回退，绝不出原始 id。
    assert resolve_scene_title("gym", None, None) == "Gym 情景对话"


def test_resolve_scene_title_whitespace_only_falls_back(caplog) -> None:
    """纯空白等价于缺值：回退确定性路径并留 empty reason 观测。"""
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result = resolve_scene_title("coffee_shop", "barista", "   ")
    assert result == SCENE_COPY["coffee_shop"]["scene_title"]
    fallback_logs = [
        record for record in caplog.records if "scene_display_fallback" in record.getMessage()
    ]
    assert len(fallback_logs) == 1
    assert "field=scene_title" in fallback_logs[0].getMessage()
    assert "reason=empty" in fallback_logs[0].getMessage()


def test_resolve_scene_title_overlong_value_falls_back_instead_of_truncating(caplog) -> None:
    """超长回退而非截断：历史脏值宁可回退可信基线也不用半个 LLM 句。"""
    overlong = "咖" * (REVIEW_COPY_MAX_CHARS["scene_title"] + 1)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result = resolve_scene_title("gym", "fitness coach", overlong)
    assert result == get_scene_title("gym", "fitness coach")
    fallback_logs = [
        record for record in caplog.records if "scene_display_fallback" in record.getMessage()
    ]
    assert len(fallback_logs) == 1
    assert "reason=too_long" in fallback_logs[0].getMessage()


def test_resolve_scene_title_leaking_value_falls_back_with_negative_assertion(caplog) -> None:
    """含原始 scene/role id 变体的值按泄漏回退，输出经变体负向断言。

    变体级负向断言只对已知场景成立（预设文案天然不含 id 词面）；未知场景的
    确定性回退本身是 humanize 组合（"Gym · Fitness Coach 情景对话"），含大写
    id 词面是 PRD 认可的既有行为，负向断言改为"等于确定性回退且不等于裸 id"。
    """
    # coffee_shop 场景：裸下划线串、空格变体、role id 泄漏均判反。
    for llm_title in ("coffee_shop 柜台", "Coffee Shop 柜台", "barista 推荐"):
        with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
            result = resolve_scene_title("coffee_shop", "barista", llm_title)
        assert result == get_scene_title("coffee_shop", "barista")
        _assert_no_identifier_leak(result, "coffee_shop", "barista")
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result = resolve_scene_title("gym", "fitness coach", "gym 力量训练")
    assert result == get_scene_title("gym", "fitness coach")
    assert result == "Gym · Fitness Coach 情景对话"
    assert result != "gym"
    # 泄漏与超长同属"值存在但无效"：每次泄漏都留一条观测日志。
    leak_logs = [record for record in caplog.records if "reason=raw_id_leak" in record.getMessage()]
    assert len(leak_logs) == 4


# ---------- resolve_role_label 优先级矩阵 ----------


def test_resolve_role_label_matrix_mirrors_scene_title() -> None:
    """role_label 与 scene_title 同矩阵：有效消费、None 逐字节一致、无效回退。"""
    assert resolve_role_label("coffee_shop", "barista", "店员服务") == "店员服务"
    assert resolve_role_label("gym", "fitness coach", "教练指导") == "教练指导"
    assert resolve_role_label("coffee_shop", "barista", None) == "店员对话"
    assert resolve_role_label("gym", "fitness coach", None) == get_role_label(
        "gym", "fitness coach"
    )
    assert resolve_role_label("gym", "fitness coach", "   ") == "角色 · Fitness Coach"
    overlong = "店" * (REVIEW_COPY_MAX_CHARS["role_label"] + 1)
    assert resolve_role_label("gym", "fitness coach", overlong) == "角色 · Fitness Coach"
    # 泄漏变体：role id 裸串与空格变体均回退（"Fitness Coach 指导"是 role id 的
    # 变体，只对 fitness coach 场景成立；barista 场景用 Barista 系列判泄漏）。
    # 变体级负向断言只对已知场景成立（"店员对话"不含 id 词面）；未知场景回退
    # 本身是 humanize 组合（"角色 · Fitness Coach"），断言等于确定性回退即可。
    known_leaks = (
        ("coffee_shop", "barista", "Barista 服务"),
        ("coffee_shop", "barista", "barista 对话"),
    )
    for scene, role, llm_label in known_leaks:
        result = resolve_role_label(scene, role, llm_label)
        assert result == get_role_label(scene, role) == "店员对话"
        _assert_no_identifier_leak(result, scene, role)
    for llm_label in ("Fitness Coach 指导", "fitness_coach 指导"):
        result = resolve_role_label("gym", "fitness coach", llm_label)
        assert result == get_role_label("gym", "fitness coach")
        assert result == "角色 · Fitness Coach"
        assert result != "fitness coach"


# ---------- 字段级独立性 ----------


def test_scene_title_and_role_label_fallback_independently() -> None:
    """scene_title 有效而 role_label 泄漏 → 各走各的分支，互不牵连。"""
    scene_title = resolve_scene_title("gym", "fitness coach", "健身房力量训练")
    role_label = resolve_role_label("gym", "fitness coach", "Fitness Coach 指导")
    assert scene_title == "健身房力量训练"
    assert role_label == get_role_label("gym", "fitness coach")

    # 反向：role_label 有效而 scene_title 泄漏，同样互不牵连。
    scene_title = resolve_scene_title("gym", "fitness coach", "Gym 训练")
    role_label = resolve_role_label("gym", "fitness coach", "教练指导")
    assert scene_title == get_scene_title("gym", "fitness coach")
    assert role_label == "教练指导"


# ---------- warning 观测 ----------


def test_fallback_warning_only_when_llm_value_present_but_invalid(caplog) -> None:
    """None 静默（确定性路径常态，不刷日志）；泄漏与超长各留一条结构化 warning。"""
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        # None 路径：零日志。
        resolve_scene_title("gym", "fitness coach", None)
        resolve_role_label("gym", "fitness coach", None)
        assert not [
            record for record in caplog.records if "scene_display_fallback" in record.getMessage()
        ]
        # 泄漏一条。
        resolve_scene_title("gym", "fitness coach", "Gym 训练")
        # 超长一条。
        resolve_role_label("gym", "fitness coach", "店" * 41)
        warnings = [
            record for record in caplog.records if "scene_display_fallback" in record.getMessage()
        ]
    assert len(warnings) == 2
    first, second = warnings
    assert "field=scene_title" in first.getMessage()
    assert "reason=raw_id_leak" in first.getMessage()
    assert "field=role_label" in second.getMessage()
    assert "reason=too_long" in second.getMessage()


# ---------- contains_identifier_variant 单源语义 ----------


def test_contains_identifier_variant_matches_all_variants_case_insensitively() -> None:
    """原始串、下划线↔空格变体、大小写差异全部命中；干净中文不误报。"""
    assert contains_identifier_variant("coffee_shop 柜台", "coffee_shop")
    assert contains_identifier_variant("Coffee Shop 柜台", "coffee_shop")
    assert contains_identifier_variant("gym 训练", "gym")
    assert contains_identifier_variant("Barista 服务", "barista")
    assert contains_identifier_variant("fitness_coach 指导", "fitness coach")
    assert contains_identifier_variant("FITNESS COACH 指导", "fitness coach")
    assert not contains_identifier_variant("健身房力量训练", "gym", "fitness coach")
    assert not contains_identifier_variant("咖啡馆柜台点单", "coffee_shop", "barista")


def test_contains_identifier_variant_ignores_blank_identifiers() -> None:
    """空串变体剔除防子串恒真误判：空 id 不可能让任意值命中。"""
    assert not contains_identifier_variant("anything", "", " ")
    assert not contains_identifier_variant("", "gym")
    assert contains_identifier_variant("gym", "gym")


# ---------- 评测台单源回归 ----------


def test_evaluation_reuses_identifier_variants_from_review_builder() -> None:
    """评测台泄漏检测改 import 单源：两模块共享同一变体归集函数对象。"""
    from api.modules.session_engine import evaluation

    assert evaluation.identifier_variants is identifier_variants
    # 变体语义不变：正反例与评测台既有用例口径一致。
    assert identifier_variants("coffee_shop") == {"coffee_shop", "coffee shop"}
    assert identifier_variants("fitness coach") == {"fitness coach", "fitness_coach"}
    assert identifier_variants("") == set()
