from pydantic import BaseModel, Field, field_validator

from api.models.review_model import (
    FeedbackMetric,
    PracticeFeedback,
    SessionReview,
    UsefulWordsMetric,
)
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackResult

SCENE_COPY = {
    "coffee_shop": {
        "scene_title": "咖啡店柜台点单",
        "role_label": "店员对话",
        "next_try": "下一轮先说主需求，再补一条口味或杯型细节。",
    },
    "office": {
        "scene_title": "办公室状态同步",
        "role_label": "同事沟通",
        "next_try": "下一轮先给进度结论，再补一句下一步动作。",
    },
    "travel": {
        "scene_title": "街头问路确认路线",
        "role_label": "路人问答",
        "next_try": "下一轮先说目的地，再复述一次关键地标或转弯位置。",
    },
    "street": {
        "scene_title": "街头问路确认路线",
        "role_label": "路人问答",
        "next_try": "下一轮先说目的地，再复述一次关键地标或转弯位置。",
    },
    "restaurant": {
        "scene_title": "餐厅点单练习",
        "role_label": "点单练习",
        "next_try": "下一轮先说主菜，再补饮料或口味偏好。",
    },
}

# ReviewCopy 消费侧硬顶（与 REVIEW_PROMPT 的软约束一致）：提示词管不住失控输出，
# 落卡前逐字段截断，防止超长文案撑爆复盘卡片。scene_title/role_label 本期不被
# 复盘卡片消费（冗余保留，供未来随契约下发），故只给被消费字段配硬顶常量。
_REVIEW_COPY_HIGHLIGHT_MAX_CHARS = 120
_REVIEW_COPY_NEXT_TRY_MAX_CHARS = 80
_REVIEW_COPY_NEXT_STEP_MAX_CHARS = 80


class ReviewCopy(BaseModel):
    """LLM 复盘文案契约（审计 Finding 20）。

    字段全部 min_length=1：模型返回空串/缺键 → pydantic ValidationError
    （ValueError 子类）→ failover 骨架判定为可重试 → 主备切换，
    全败后上抛 → 编排层降级模板复盘。
    """

    scene_title: str = Field(min_length=1)
    role_label: str = Field(min_length=1)
    highlight: str = Field(min_length=1)
    next_try: str = Field(min_length=1)
    next_step: str = Field(min_length=1)

    @field_validator(
        "scene_title",
        "role_label",
        "highlight",
        "next_try",
        "next_step",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: object) -> object:
        """先 strip 再校验：纯空白文案等价于空串，按契约失败并触发重试。"""
        if isinstance(value, str):
            return value.strip()
        return value


def build_session_review(
    session: Session,
    feedback: FeedbackResult,
    copy: ReviewCopy | None = None,
) -> SessionReview:
    """把本轮会话和反馈结果整理成前端可直接展示的复盘卡片。

    copy=None 走模板复盘（mock 模式与降级兜底，行为与历史版本逐字节一致）；
    copy 提供时用 LLM 复盘文案替换 highlight/next_try/next_step，
    消费侧再做 _bound 截断硬顶。
    """
    scene_title = get_scene_title(session.scene)
    latest_learner_message = _find_latest_learner_message(session)
    highlight = f"你已经围绕“{scene_title}”把主要意思表达出来了。"
    if latest_learner_message is not None:
        highlight = f"{highlight} 最近一次回答是：{_truncate(latest_learner_message.text)}"
    next_try = get_next_try(session.scene)
    next_step = "下一轮试着在一句主回应后再补一句细节。"
    if copy is not None:
        highlight = _bound(copy.highlight, _REVIEW_COPY_HIGHLIGHT_MAX_CHARS)
        next_try = _bound(copy.next_try, _REVIEW_COPY_NEXT_TRY_MAX_CHARS)
        next_step = _bound(copy.next_step, _REVIEW_COPY_NEXT_STEP_MAX_CHARS)

    return SessionReview(
        session_id=session.id,
        title="本轮回响",
        highlight=highlight,
        next_try=next_try,
        feedback=PracticeFeedback(
            grammar=FeedbackMetric(title="Grammar", body=feedback.grammar),
            more_natural=FeedbackMetric(title="More Natural", body=feedback.more_natural),
            useful_words=UsefulWordsMetric(
                title="Useful Words",
                words=list(feedback.useful_words),
                body="把这些词带进下一轮回答，会更自然。",
            ),
            next_step=FeedbackMetric(
                title="Next Step",
                body=next_step,
            ),
        ),
    )


def get_scene_title(scene: str, role: str | None = None) -> str:
    """把内部场景名映射成面向用户的中文标题。

    未命中预设文案时回退为"场景名 · 角色名 情景对话"的自然语言组合：
    任何路径都不得把原始 scene id（如 gym）当标题输出（审计 Finding 20）；
    history 契约的现有单参调用不受影响。
    """
    preset = SCENE_COPY.get(scene, {}).get("scene_title")
    if preset is not None:
        return preset
    scene_name = _humanize_identifier(scene)
    if role:
        return f"{scene_name} · {_humanize_identifier(role)} 情景对话"
    return f"{scene_name} 情景对话"


def get_role_label(scene: str, role: str) -> str:
    """优先返回场景预设文案，缺省时回退为"角色 · 角色名"自然语言组合。

    回退值经大写化处理，不再可能是裸 snake_case 原始 id。
    """
    preset = SCENE_COPY.get(scene, {}).get("role_label")
    if preset is not None:
        return preset
    return f"角色 · {_humanize_identifier(role)}"


def get_next_try(scene: str) -> str:
    """给每个场景提供一条下一轮练习建议。"""
    return SCENE_COPY.get(scene, {}).get("next_try", "下一轮先把主需求说完整，再补一句细节。")


def _humanize_identifier(value: str) -> str:
    """把 snake_case/小写标识符转成首字母大写的自然语言词组（gym → Gym）。"""
    return " ".join(part.capitalize() for part in value.replace("_", " ").split())


def _bound(value: str, limit: int) -> str:
    """ReviewCopy 消费侧硬顶：strip 后按上限截断。"""
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit]


def _find_latest_learner_message(session: Session):
    """倒序查找最近一条学习者消息，供 highlight 摘要使用。"""
    for message in reversed(session.messages):
        if message.role == "user":
            return message
    return None


def _truncate(value: str, limit: int = 48) -> str:
    """把摘要文本裁到固定长度，避免复盘卡片过长。"""
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."
