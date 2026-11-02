"""展示名消费点一致性测试（review-copy-consumption Phase C）。

同一 Session 域模型构建 SessionResponse / HistoryEntryResponse /
HistorySessionMetaResponse，三个契约构建器的展示名必须两两相等——
reply / stream / voice / GET / history 各消费点共用同一 resolver 优先级
（design 2.3），无原始 scene id 泄漏路径。纯契约层构建，无网络无 DB。
"""

from __future__ import annotations

from api.contracts.history import HistoryEntryResponse, HistorySessionMetaResponse
from api.contracts.sessions import SessionResponse, SessionReviewResponse
from api.models.message_model import Message
from api.models.session_model import Session
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.session_engine.review_builder import (
    build_session_review,
    get_role_label,
    get_scene_title,
    identifier_variants,
)

SCENE = "gym"
ROLE = "fitness coach"


def _session(**overrides: object) -> Session:
    """构造一个带一条消息的最小开放集场景会话，测试按需覆写字段。"""
    payload: dict[str, object] = {
        "id": "sess_display",
        "user_id": "demo-user",
        "media_id": None,
        "scene": SCENE,
        "role": ROLE,
        "opener": "Hi there",
        "messages": [Message(id="msg_1", role="assistant", text="Hi there")],
    }
    payload.update(overrides)
    return Session(**payload)


def _build_all(
    session: Session,
) -> tuple[SessionResponse, HistoryEntryResponse, HistorySessionMetaResponse]:
    """同一 Session 构建三个契约响应，返回三元组供一致性断言。"""
    feedback = FeedbackResult(grammar="ok", more_natural="ok", useful_words=["ok"])
    review = build_session_review(session, feedback)
    review_response = SessionReviewResponse.from_review(review)
    return (
        SessionResponse.from_session(session),
        HistoryEntryResponse.from_session(session, review_response),
        HistorySessionMetaResponse.from_session(session, total_messages=1),
    )


def test_three_builders_agree_on_valid_llm_display_names() -> None:
    """有效 LLM 展示名：三个构建器两两相等且等于 LLM 值。"""
    session = _session(
        llm_scene_title="健身房力量训练",
        llm_role_label="教练指导",
    )
    session_response, entry_response, meta_response = _build_all(session)

    for response in (session_response, entry_response, meta_response):
        assert response.scene_title == "健身房力量训练"
        assert response.role_label == "教练指导"
    assert session_response.scene_title == entry_response.scene_title == meta_response.scene_title
    assert session_response.role_label == entry_response.role_label == meta_response.role_label


def test_three_builders_agree_on_deterministic_fallback_when_llm_none() -> None:
    """llm 字段为 None（mock/旧行）：三者相等且等于确定性回退值（现算，不硬编码）。"""
    session = _session()
    session_response, entry_response, meta_response = _build_all(session)

    expected_title = get_scene_title(session.scene, session.role)
    expected_label = get_role_label(session.scene, session.role)
    assert expected_title == "Gym · Fitness Coach 情景对话"
    for response in (session_response, entry_response, meta_response):
        assert response.scene_title == expected_title
        assert response.role_label == expected_label


def test_leaked_llm_value_falls_back_identically_across_builders() -> None:
    """泄漏的 llm 值在响应层按字段级回退：三者相等且等于确定性回退（现算）。"""
    session = _session(
        llm_scene_title="gym 训练",
        llm_role_label="教练指导",
    )
    session_response, entry_response, meta_response = _build_all(session)

    expected_title = get_scene_title(session.scene, session.role)
    for response in (session_response, entry_response, meta_response):
        assert response.scene_title == expected_title
        # 负向断言：展示名绝不等于裸原始 id。
        assert response.scene_title != SCENE
        assert response.role_label != ROLE
    assert session_response.scene_title == entry_response.scene_title == meta_response.scene_title
    assert session_response.role_label == entry_response.role_label == meta_response.role_label


def test_leaked_llm_value_on_preset_scene_contains_no_identifier_variant() -> None:
    """预设场景泄漏变体级负向断言：回退文案（预设中文）不含任何 id 变体。"""
    session = _session(
        scene="coffee_shop",
        role="barista",
        llm_scene_title="coffee_shop 柜台",
        llm_role_label="Barista 服务",
    )
    session_response, entry_response, meta_response = _build_all(session)

    for response in (session_response, entry_response, meta_response):
        lowered = f"{response.scene_title} {response.role_label}".lower()
        for identifier in ("coffee_shop", "barista"):
            for variant in identifier_variants(identifier):
                assert variant not in lowered, f"leaked {variant!r} in response"


def test_history_entry_uses_role_aware_fallback_for_unknown_scene() -> None:
    """行为收敛锁定：history 条目从未带 role 的单参回退统一为三参语义。

    旧行为 get_scene_title("gym") == "Gym 情景对话"；统一后未知场景历史条目
    与 SessionResponse 一致地展示"场景 · 角色 情景对话"组合。
    """
    session = _session()
    feedback = FeedbackResult(grammar="ok", more_natural="ok", useful_words=["ok"])
    review = build_session_review(session, feedback)
    entry = HistoryEntryResponse.from_session(session, SessionReviewResponse.from_review(review))

    assert entry.scene_title == "Gym · Fitness Coach 情景对话"
    assert entry.scene_title == get_scene_title(session.scene, session.role)
    assert entry.role_label == "角色 · Fitness Coach"
