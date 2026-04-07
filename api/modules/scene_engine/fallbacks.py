from api.modules.scene_engine.schema import SceneAnalysisResult


def build_static_scene_fallback() -> SceneAnalysisResult:
    return SceneAnalysisResult(
        scene="general_chat",
        role="friendly_assistant",
        opener="Hello! What would you like to talk about today?",
        visual_anchors=[],
        vocab_candidates=[],
        confidence=0.0,
    )
