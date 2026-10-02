from datetime import UTC, datetime

from pydantic import BaseModel, Field


class LearnerProfile(BaseModel):
    """单个认证用户的滚动学习档案（纯 Pydantic 域模型，无 ORM）。

    每认证用户一行：user_id 存 owner 全串（user:<users.id>，与会话表同一
    身份约定）；visitor:* 不建档（编排层门控排除，见 session_engine/agent）。
    三个 JSON 字段全部是写侧封顶的有界结构，行宽不随练习轮数增长：
    - error_type_counts：≤9 键（9 类封闭错误集合）；
    - scene_counts：≤ learner_profile_scene_cap 键，插入序 = 近期序；
    - cefr_history：≤ learner_profile_cefr_window 项的最近 CEFR 观测。
    """

    user_id: str
    cefr_estimate: str | None = None
    error_type_counts: dict[str, int] = Field(default_factory=dict)
    scene_counts: dict[str, int] = Field(default_factory=dict)
    cefr_history: list[str] = Field(default_factory=list)
    practiced_turn_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
