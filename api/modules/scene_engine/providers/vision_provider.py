from api.modules.scene_engine.schema import SceneAnalysisInput, SceneAnalysisResult
from api.modules.scene_engine.tools.image_tools import infer_tags_from_filename


class MockVisionProvider:
    def analyze(self, payload: SceneAnalysisInput) -> SceneAnalysisResult:
        filename = payload.filename.lower()
        labels = infer_tags_from_filename(payload.filename)

        if any(token in filename for token in ("coffee", "cafe", "latte")):
            return SceneAnalysisResult(
                scene="coffee_shop",
                role="barista",
                opener="Hi there, what can I get started for you today?",
                labels=labels or ["coffee", "counter", "menu"],
                confidence=0.83,
            )
        if any(token in filename for token in ("office", "desk", "meeting")):
            return SceneAnalysisResult(
                scene="office",
                role="coworker",
                opener="Morning. Are you ready to talk through today's tasks?",
                labels=labels or ["desk", "laptop", "notes"],
                confidence=0.78,
            )
        if any(token in filename for token in ("street", "travel", "station")):
            return SceneAnalysisResult(
                scene="travel",
                role="local_guide",
                opener="You look a little lost. Where are you trying to go?",
                labels=labels or ["street", "map", "sign"],
                confidence=0.74,
            )

        return SceneAnalysisResult(
            scene="restaurant",
            role="server",
            opener="Welcome in. Have you decided what you'd like to order?",
            labels=labels or ["table", "menu", "chair"],
            confidence=0.71,
        )
