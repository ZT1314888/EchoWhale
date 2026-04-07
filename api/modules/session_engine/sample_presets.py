from __future__ import annotations

from pydantic import BaseModel

from api.modules.session_engine.schema import SampleSceneId


class SampleSessionPreset(BaseModel):
    scene: str
    role: str
    opener: str
    visual_anchors: list[str]
    vocab_candidates: list[str]


SAMPLE_SESSION_PRESETS: dict[SampleSceneId, SampleSessionPreset] = {
    "coffee": SampleSessionPreset(
        scene="coffee_shop",
        role="friendly barista",
        opener="Hello! What would you like to order today?",
        visual_anchors=["counter", "pastry case"],
        vocab_candidates=["latte", "size", "to go"],
    ),
    "office": SampleSessionPreset(
        scene="office",
        role="project teammate",
        opener="Morning! Could you give me a quick status update?",
        visual_anchors=["glass wall", "laptop"],
        vocab_candidates=["update", "timeline", "next step"],
    ),
    "street": SampleSessionPreset(
        scene="travel",
        role="helpful passerby",
        opener="Sure, where are you trying to get to?",
        visual_anchors=["crosswalk", "street sign"],
        vocab_candidates=["station", "turn left", "corner"],
    ),
}


def get_sample_session_preset(sample_scene_id: SampleSceneId) -> SampleSessionPreset:
    return SAMPLE_SESSION_PRESETS[sample_scene_id]
