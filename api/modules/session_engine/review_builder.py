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


def build_session_review(session: Session, feedback: FeedbackResult) -> SessionReview:
    """把本轮会话和反馈结果整理成前端可直接展示的复盘卡片。"""
    scene_title = get_scene_title(session.scene)
    latest_learner_message = _find_latest_learner_message(session)
    highlight = f"你已经围绕“{scene_title}”把主要意思表达出来了。"
    if latest_learner_message is not None:
        highlight = f"{highlight} 最近一次回答是：{_truncate(latest_learner_message.text)}"

    return SessionReview(
        session_id=session.id,
        title="本轮回响",
        highlight=highlight,
        next_try=get_next_try(session.scene),
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
                body="下一轮试着在一句主回应后再补一句细节。",
            ),
        ),
    )


def get_scene_title(scene: str) -> str:
    """把内部场景名映射成面向用户的中文标题。"""
    return SCENE_COPY.get(scene, {}).get("scene_title", scene.replace("_", " "))


def get_role_label(scene: str, role: str) -> str:
    """优先返回场景预设文案，缺省时再回退到原始角色名。"""
    return SCENE_COPY.get(scene, {}).get("role_label", f"角色 · {role}")


def get_next_try(scene: str) -> str:
    """给每个场景提供一条下一轮练习建议。"""
    return SCENE_COPY.get(scene, {}).get("next_try", "下一轮先把主需求说完整，再补一句细节。")


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
