from api.modules.scene_engine.agent import SceneEngineAgent
from api.modules.scene_engine.schema import SceneAnalysisInput, SceneAnalysisResult


class SceneEngineService:
    def __init__(self) -> None:
        self.agent = SceneEngineAgent()

    def analyze(self, filename: str, media_url: str) -> SceneAnalysisResult:
        payload = SceneAnalysisInput(filename=filename, media_url=media_url)
        return self.agent.run(payload)
