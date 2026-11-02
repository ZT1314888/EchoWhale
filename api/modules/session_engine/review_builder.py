import logging

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from api.models.review_model import (
    FeedbackMetric,
    PracticeFeedback,
    SessionReview,
    UsefulWordsMetric,
)
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackResult

logger = logging.getLogger(__name__)

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

# ReviewCopy 字段长度硬顶（生产单一事实源）：五字段 40/40/120/80/80，与
# REVIEW_PROMPT 的软约束逐字段一致——提示词管不住失控输出，校验层截断才是硬保证
# （eval_prompt_fixes 批次 design 2.3）。session_engine/evaluation.py 的
# REVIEW_COPY_FIELD_LIMITS 从这里 import，评测与生产同表。
REVIEW_COPY_MAX_CHARS: dict[str, int] = {
    "scene_title": 40,
    "role_label": 40,
    "highlight": 120,
    "next_try": 80,
    "next_step": 80,
}


def identifier_variants(identifier: str) -> set[str]:
    """原始 id 的下划线↔空格变体集合（小写化）；空串剔除防子串恒真误判。

    单一事实源：评测台 session_engine/evaluation.py 的泄漏检测从本函数 import，
    生产消费侧（resolve_scene_title / resolve_role_label）与评测台因此共享同一
    变体归集规则，杜绝"评测判干净、生产判泄漏"的双源漂移。
    """
    normalized = identifier.strip().lower()
    return {normalized, normalized.replace("_", " "), normalized.replace(" ", "_")} - {""}


def contains_identifier_variant(value: str, *identifiers: str) -> bool:
    """值的小写形态包含任一原始 id 变体即判定泄漏（大小写不敏感子串检测）。

    供展示名逐字段防护检测使用：任一命中即说明该字段不能直接当展示名消费。
    """
    normalized = value.lower()
    return any(
        variant in normalized
        for identifier in identifiers
        for variant in identifier_variants(identifier)
    )


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

    @field_validator(
        "scene_title",
        "role_label",
        "highlight",
        "next_try",
        "next_step",
        mode="after",
    )
    @classmethod
    def _truncate_to_cap(cls, value: str, info: ValidationInfo) -> str:
        """超长字段按 cap 截断并留观测日志（截断而非拒绝，design 2.3）。

        拒绝会把其余字段完好的复盘整份打回重试/failover，换来全模板降级，损失
        大于半句截断；与教练 2000 字符硬顶同为"超长截断 + 观测日志"纪律。截断
        发生在 strip 之后（after 阶段），纯空白仍被 _strip_text + min_length=1
        拒绝，failover 语义不变。
        """
        cap = REVIEW_COPY_MAX_CHARS[info.field_name or ""]
        if len(value) <= cap:
            return value
        logger.warning(
            "review_copy_truncated field=%s length=%d cap=%d",
            info.field_name,
            len(value),
            cap,
        )
        return value[:cap]


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
        # 消费侧 _bound 保留为双保险（design 2.3）：validator 已按 cap 截断，
        # 此处行为零变化。
        highlight = _bound(copy.highlight, REVIEW_COPY_MAX_CHARS["highlight"])
        next_try = _bound(copy.next_try, REVIEW_COPY_MAX_CHARS["next_try"])
        next_step = _bound(copy.next_step, REVIEW_COPY_MAX_CHARS["next_step"])

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


def resolve_scene_title(scene: str, role: str | None, llm_title: str | None) -> str:
    """场景展示名解析：LLM 复盘值优先，无效按字段级回退确定性路径。

    优先级矩阵（design 2.1，逐字段独立判定）：
    - None / 空白 → 确定性路径（已知场景预设文案，未知场景 humanize 组合回退）；
    - 超长（> cap）→ 确定性回退；
    - 含原始 scene/role id 变体 → 确定性回退 + scene_display_fallback warning；
    - 有效（非空、≤cap、无泄漏）→ 消费 LLM 值（开放集场景获得贴切展示名的核心收益）。

    本函数只判定 scene_title 字段，role_label 由 resolve_role_label 独立判定，
    两个字段互不牵连：scene_title 有效而 role_label 泄漏时各自走各自分支。
    """
    identifiers = (scene, role) if role else (scene,)
    return _resolve_display_value(
        "scene_title",
        llm_title,
        get_scene_title(scene, role),
        identifiers,
    )


def resolve_role_label(scene: str, role: str, llm_label: str | None) -> str:
    """角色标签解析：语义与 resolve_scene_title 对称，只判定 role_label 字段。"""
    return _resolve_display_value(
        "role_label",
        llm_label,
        get_role_label(scene, role),
        (scene, role),
    )


def _resolve_display_value(
    field: str,
    llm_value: str | None,
    fallback: str,
    identifiers: tuple[str, ...],
) -> str:
    """LLM 展示名的字段级有效性判定与回退（两个 resolver 共用单一实现）。

    有效性判定：非 None、strip 后非空、原值长度在 REVIEW_COPY_MAX_CHARS 内
    （对原值而非 strip 后判定——ReviewCopy validator 已在生产写侧截断，正常值
    天然达标，超长分支只拦截绕过校验器入库的历史脏值）、strip 后值不含原始
    scene/role id 变体。有效返回 strip 后的 LLM 值；无效回退确定性路径。

    为什么不抛错：展示名是纯展示属性，解析失败回退可信基线（预设文案或
    humanize 组合）即可——任何响应路径都不得因展示名问题整轮失败，也不得
    输出原始 scene id（审计 Finding 20 不变量）。None 静默走确定性路径
    （mock 模式/复盘降级/历史旧行的常态，不刷日志），仅当 LLM 值存在但无效
    时留 scene_display_fallback warning 供观测。
    """
    if llm_value is None:
        return fallback
    stripped = llm_value.strip()
    if not stripped:
        reason = "empty"
    elif len(llm_value) > REVIEW_COPY_MAX_CHARS[field]:
        reason = "too_long"
    elif contains_identifier_variant(stripped, *identifiers):
        reason = "raw_id_leak"
    else:
        return stripped
    logger.warning(
        "scene_display_fallback field=%s reason=%s identifiers=%s",
        field,
        reason,
        ",".join(identifiers),
    )
    return fallback


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
