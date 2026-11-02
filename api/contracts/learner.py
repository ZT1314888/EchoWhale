"""学员档案读 API 契约（add-only 新文件）。

载荷组装在契约层完成（from_profile 调 learner_profile 的纯展示函数），与
contracts/history.py 在 from_session 里调 review_builder 展示函数的先例一致。
契约只允许引用 select_display_* 展示函数——build_learner_context_lines 是
提示词注入专用渲染，与 API 契约解耦，不得引用。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from api.models.learner_profile_model import LearnerProfile
from api.modules.session_engine.learner_profile import (
    ERROR_CATEGORY_LABELS,
    select_display_error_types,
    select_display_scenes,
)


class LearnerProfileErrorTypeResponse(BaseModel):
    """错误类别计数条目：category 是产品封闭集合词汇，label 为服务端中文展示名。"""

    category: str
    label: str
    count: int


class LearnerProfileSceneResponse(BaseModel):
    """场景计数条目：F17 不变量下只有服务端映射后的展示名，不设原始 scene id 字段。"""

    scene_title: str
    count: int


class LearnerProfileResponse(BaseModel):
    """学员档案读载荷（可全空）：前端以 practiced_turn_count == 0 判空态。"""

    # A1..C2 封闭集合值；中文文案映射归前端（同 CEFR 等级既有约定）。
    cefr_estimate: str | None
    error_types: list[LearnerProfileErrorTypeResponse]
    scenes: list[LearnerProfileSceneResponse]
    practiced_turn_count: int
    # 对齐 history practiced_at 的展示惯例："%Y-%m-%d %H:%M"。
    updated_at: str | None

    @classmethod
    def from_profile(cls, profile: LearnerProfile | None) -> LearnerProfileResponse:
        """None（首访用户）→ 全空载荷而非 404：空态是合法展示态，前端渲染引导文案。"""
        if profile is None:
            return cls(
                cefr_estimate=None,
                error_types=[],
                scenes=[],
                practiced_turn_count=0,
                updated_at=None,
            )
        return cls(
            cefr_estimate=profile.cefr_estimate,
            error_types=[
                LearnerProfileErrorTypeResponse(
                    category=category,
                    # select_display_error_types 已按封闭集合过滤，label 查找必命中。
                    label=ERROR_CATEGORY_LABELS[category],
                    count=count,
                )
                for category, count in select_display_error_types(profile.error_type_counts)
            ],
            scenes=[
                LearnerProfileSceneResponse(scene_title=scene_title, count=count)
                for scene_title, count in select_display_scenes(profile.scene_counts)
            ],
            practiced_turn_count=profile.practiced_turn_count,
            updated_at=_format_updated_at(profile.updated_at),
        )


def _format_updated_at(updated_at: datetime) -> str:
    return updated_at.strftime("%Y-%m-%d %H:%M")
