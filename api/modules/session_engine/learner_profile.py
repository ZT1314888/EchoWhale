"""学员档案的更新数学与提示词注入渲染（纯函数，无 I/O）。

单一事实源说明：9 类错误封闭集合与 A1..C2 的契约写在
api/modules/feedback_engine/prompts/feedback_prompts.py（LLM 输出契约），
schema 侧只对 cefr_level 做归一校验、对 error category 不校验——
所以这里再持有一份封闭集合常量做写侧防御（模型幻觉值丢弃）。
全部更新来自 FeedbackResult 已有字段，零额外 LLM 调用。
"""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import median_low

from api.models.learner_profile_model import LearnerProfile
from api.modules.feedback_engine.schema import FeedbackResult

# A1..C2 封闭集合与序数映射：median_low 在 1..6 上取下中位后反查级别，
# 结果恒为已观测级别（无分数级别、无浮点）。
CEFR_LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
CEFR_ORDINALS = {level: ordinal for ordinal, level in enumerate(CEFR_LEVELS, start=1)}

# 9 类封闭错误集合（与 feedback prompts 输出契约同源，见模块 docstring）。
ERROR_CATEGORIES = frozenset(
    {
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
)

# 注入块 top 错误类别行最多列出的类别数：有界注入面（提示词注入不扩大）。
MAX_INJECTED_ERROR_CATEGORIES = 3


def apply_turn_to_profile(
    profile: LearnerProfile | None,
    *,
    user_id: str,
    scene: str,
    feedback: FeedbackResult,
    scene_cap: int,
    cefr_window: int,
) -> LearnerProfile:
    """把单轮反馈信号滚动累计进档案；首轮（profile=None）从空档案构造。

    - 错误计数：仅累加 9 类封闭集合内的 category（schema 不校验 category，
      模型幻觉值在此防御性丢弃），键集合天然 ≤9；
    - 场景：pop 后重插尾部（JSON 对象保持插入序 = 近期序），超 scene_cap
      从头（最旧）淘汰；
    - 轮数：自增；
    - CEFR：feedback.cefr_level 非 None 时 append 进窗口、超 cefr_window
      淘汰最旧，并用 median_low 序数反查写回 estimate；None（含 mock 反馈
      与非法幻觉值被 validator 归一后的结果）不动 estimate，场景/轮数照常。
    """
    base = profile or LearnerProfile(user_id=user_id)

    error_type_counts = dict(base.error_type_counts)
    for error in feedback.errors:
        if error.category not in ERROR_CATEGORIES:
            continue
        error_type_counts[error.category] = error_type_counts.get(error.category, 0) + 1

    scene_counts = dict(base.scene_counts)
    previous = scene_counts.pop(scene, 0)
    scene_counts[scene] = previous + 1
    while len(scene_counts) > scene_cap:
        oldest = next(iter(scene_counts))
        del scene_counts[oldest]

    cefr_history = list(base.cefr_history)
    cefr_estimate = base.cefr_estimate
    observed_level = feedback.cefr_level
    if observed_level is not None and observed_level in CEFR_ORDINALS:
        cefr_history.append(observed_level)
        if len(cefr_history) > cefr_window:
            cefr_history = cefr_history[-cefr_window:]
        median_ordinal = median_low(CEFR_ORDINALS[level] for level in cefr_history)
        cefr_estimate = CEFR_LEVELS[median_ordinal - 1]

    return base.model_copy(
        update={
            "error_type_counts": error_type_counts,
            "scene_counts": scene_counts,
            "cefr_history": cefr_history,
            "cefr_estimate": cefr_estimate,
            "practiced_turn_count": base.practiced_turn_count + 1,
            "updated_at": datetime.now(UTC),
        }
    )


def build_learner_context_lines(profile: LearnerProfile | None) -> str | None:
    """渲染提示词注入块；无任何可注入内容时返回 None（调用方回退静态）。

    注入面有界且服务端拼装：只含封闭集合值（CEFR、错误类别）与整数（轮数），
    绝不含学习者原文或场景名（提示词注入面不扩大）。
    """
    if profile is None:
        return None
    lines: list[str] = []
    if profile.cefr_estimate:
        lines.append(f"Learner profile: estimated CEFR {profile.cefr_estimate}.")
    if profile.error_type_counts:
        # count 降序、名称升序决胜：同一输入恒定同一输出（确定性注入）。
        top_categories = sorted(
            profile.error_type_counts,
            key=lambda category: (-profile.error_type_counts[category], category),
        )[:MAX_INJECTED_ERROR_CATEGORIES]
        lines.append(
            "Learner profile: frequent error categories so far: " + ", ".join(top_categories) + "."
        )
    if profile.practiced_turn_count > 0:
        lines.append(f"Learner profile: {profile.practiced_turn_count} practice turns completed.")
    if not lines:
        return None
    return "\n".join(lines)
