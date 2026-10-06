"""learner_profile 纯函数直测：更新数学（计数/封顶/median_low）、注入渲染与展示选择。"""

from __future__ import annotations

from api.models.learner_profile_model import LearnerProfile
from api.modules.feedback_engine.schema import FeedbackErrorItem, FeedbackResult
from api.modules.session_engine.learner_profile import (
    ERROR_CATEGORIES,
    apply_turn_to_profile,
    build_learner_context_lines,
    select_display_error_types,
    select_display_scenes,
)


def _feedback(
    *,
    categories: list[str] | None = None,
    cefr_level: str | None = None,
) -> FeedbackResult:
    """构造带指定错误类别与 CEFR 观测的反馈；原文内容对档案数学无意义。"""
    errors = [
        FeedbackErrorItem(
            category=category,
            original=f"frag-{index}",
            correction="fixed",
            explanation="One sentence.",
        )
        for index, category in enumerate(categories or [])
    ]
    return FeedbackResult(
        grammar="Keep going.",
        more_natural="A more natural sentence.",
        useful_words=["latte"],
        errors=errors,
        cefr_level=cefr_level,
    )


def _apply(
    profile: LearnerProfile | None = None,
    scene: str = "coffee_shop",
    *,
    categories: list[str] | None = None,
    cefr_level: str | None = None,
    scene_cap: int = 12,
    cefr_window: int = 10,
) -> LearnerProfile:
    return apply_turn_to_profile(
        profile,
        user_id="user:learner",
        scene=scene,
        feedback=_feedback(categories=categories, cefr_level=cefr_level),
        scene_cap=scene_cap,
        cefr_window=cefr_window,
    )


def test_first_turn_builds_empty_profile_and_counts_turn() -> None:
    profile = _apply()

    assert profile.user_id == "user:learner"
    assert profile.error_type_counts == {}
    assert profile.scene_counts == {"coffee_shop": 1}
    assert profile.practiced_turn_count == 1
    assert profile.cefr_estimate is None
    assert profile.cefr_history == []


def test_error_categories_accumulate_and_hallucinated_ones_are_dropped() -> None:
    """封闭集合内的 category 累加计数；模型幻觉 category 防御性丢弃。"""
    profile = _apply(categories=["tense", "tense", "article"])
    profile = _apply(profile, categories=["tense"])

    assert profile.error_type_counts == {"tense": 3, "article": 1}


def test_scene_cap_evicts_oldest_scene() -> None:
    """第 13 个场景触发封顶：从头淘汰最旧场景，保留窗口内最近 12 个。"""
    profile: LearnerProfile | None = None
    for index in range(13):
        profile = _apply(profile, scene=f"scene_{index}")

    assert profile is not None
    assert list(profile.scene_counts) == [f"scene_{index}" for index in range(1, 13)]
    assert all(count == 1 for count in profile.scene_counts.values())


def test_repeated_scene_refreshes_recency_and_accumulates_count() -> None:
    """重复场景 pop 后重插尾部（近期序）且计数累加，而非挤掉别的场景。"""
    profile = _apply(scene="coffee_shop")
    profile = _apply(profile, scene="office")
    profile = _apply(profile, scene="coffee_shop")

    assert list(profile.scene_counts) == ["office", "coffee_shop"]
    assert profile.scene_counts["coffee_shop"] == 2
    assert profile.scene_counts["office"] == 1


def test_cefr_median_low_odd_window_picks_middle_level() -> None:
    profile: LearnerProfile | None = None
    for level in ("A1", "B1", "C2"):
        profile = _apply(profile, cefr_level=level)

    assert profile is not None
    assert profile.cefr_history == ["A1", "B1", "C2"]
    # 序数 [1, 3, 6] 的下中位是 3 → B1（结果恒为已观测级别）。
    assert profile.cefr_estimate == "B1"


def test_cefr_median_low_even_window_takes_lower_middle() -> None:
    profile = _apply(cefr_level="B1")
    profile = _apply(profile, cefr_level="B2")

    # 偶数窗口 [3, 4] 取下中位 3 → B1，不产生分数级别。
    assert profile.cefr_estimate == "B1"


def test_cefr_window_full_evicts_oldest_observation() -> None:
    """窗口满后淘汰最旧观测：估计随近期表现滚动，不被远古轮次钉死。"""
    profile = _apply(cefr_level="A1", cefr_window=3)
    profile = _apply(profile, cefr_level="A1", cefr_window=3)
    profile = _apply(profile, cefr_level="C2", cefr_window=3)
    assert profile.cefr_estimate == "A1"  # [1, 1, 6] → 下中位 1

    profile = _apply(profile, cefr_level="B2", cefr_window=3)
    # 窗口 [A1, C2, B2] → 序数 [1, 6, 4] → 下中位 4 → B2。
    assert profile.cefr_history == ["A1", "C2", "B2"]
    assert profile.cefr_estimate == "B2"


def test_cefr_none_leaves_estimate_untouched_but_counts_turn_and_scene() -> None:
    """mock 反馈 cefr_level=None：estimate/history 不动，轮数与场景照常累计。"""
    profile = _apply(cefr_level="B1")
    profile = _apply(profile, scene="office", cefr_level=None)

    assert profile.cefr_estimate == "B1"
    assert profile.cefr_history == ["B1"]
    assert profile.practiced_turn_count == 2
    assert profile.scene_counts == {"coffee_shop": 1, "office": 1}


def test_invalid_cefr_level_never_enters_history() -> None:
    """非法 CEFR 幻觉值先被 FeedbackResult validator 归一为 None，不进窗口。"""
    profile = _apply(cefr_level="Z9")

    assert profile.cefr_history == []
    assert profile.cefr_estimate is None


def test_build_learner_context_lines_renders_bounded_deterministic_block() -> None:
    profile = LearnerProfile(
        user_id="user:learner",
        cefr_estimate="B1",
        error_type_counts={"tense": 3, "article": 5, "other": 5, "spelling": 1},
        practiced_turn_count=7,
    )

    assert build_learner_context_lines(profile) == (
        "Learner profile: estimated CEFR B1.\n"
        "Learner profile: frequent error categories so far: article, other, tense.\n"
        "Learner profile: 7 practice turns completed."
    )


def test_build_learner_context_lines_none_for_empty_profile() -> None:
    """空档案（无任何观测）返回 None：调用方回退静态注入。"""
    assert build_learner_context_lines(None) is None
    assert build_learner_context_lines(LearnerProfile(user_id="user:learner")) is None


def test_injected_lines_never_contain_learner_text_or_scene_names() -> None:
    """注入行守卫：学习者原文与场景名绝不进注入块（注入面不扩大）。"""
    learner_text = "Yesterday I have ate a apple in the cozy coffee shop near my home"
    profile = _apply(
        scene="coffee_shop_with_free_form_visual_name",
        categories=["tense", "word_choice"],
        cefr_level="B1",
    )

    lines = build_learner_context_lines(profile)

    assert lines is not None
    assert "coffee_shop_with_free_form_visual_name" not in lines
    assert learner_text not in lines


def test_select_display_error_types_sorts_by_count_then_category() -> None:
    """(-count, category) 确定性排序：同 count 按类别字典序决胜。"""
    assert select_display_error_types({"tense": 3, "article": 3, "grammar": 1}) == [
        ("article", 3),
        ("tense", 3),
        ("grammar", 1),
    ]


def test_select_display_error_types_caps_at_three() -> None:
    """API 载荷硬顶：9 类全观测也只出 top 3。"""
    assert select_display_error_types({category: 1 for category in ERROR_CATEGORIES}) == [
        ("article", 1),
        ("collocation", 1),
        ("grammar", 1),
    ]


def test_select_display_error_types_drops_out_of_set_keys() -> None:
    """读侧同源防御：手改库出现的集合外键不进载荷，防幻觉值回流展示层。"""
    assert select_display_error_types({"hallucinated": 99, "tense": 2, "other": 1}) == [
        ("tense", 2),
        ("other", 1),
    ]
    assert select_display_error_types({}) == []


def test_select_display_scenes_maps_titles_and_merges_same_copy() -> None:
    """street/travel 展示文案相同：映射后必须合并计数，不出现重复条目。"""
    assert select_display_scenes({"coffee_shop": 4, "street": 3, "travel": 1}) == [
        ("咖啡店柜台点单", 4),
        ("街头问路确认路线", 4),
    ]


def test_select_display_scenes_humanizes_unknown_scene_ids() -> None:
    """未命中预设文案的场景走 humanize 回退，任何路径不露原始 scene id。"""
    assert select_display_scenes({"gym": 2}) == [("Gym 情景对话", 2)]


def test_select_display_scenes_caps_at_twelve() -> None:
    """API 载荷硬顶：15 个不同场景只出计数最高的 12 个；空计数返回空列表。"""
    counts = {f"scene_{index:02d}": index + 1 for index in range(15)}
    assert select_display_scenes(counts) == [
        (f"Scene {index:02d} 情景对话", index + 1) for index in range(14, 2, -1)
    ]
    assert select_display_scenes({}) == []
