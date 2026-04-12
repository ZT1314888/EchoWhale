from api.modules.scene_engine.schema import SceneAnalysisResult


def build_static_scene_fallback() -> SceneAnalysisResult:
    """构造最保守的兜底场景结果，供上游显式识别失败路径。"""
    return SceneAnalysisResult(
        scene="general_chat",
        role="friendly_assistant",
        opener="Hello! What would you like to talk about today?",
        visual_anchors=[],
        vocab_candidates=[],
        confidence=0.0,
    )
