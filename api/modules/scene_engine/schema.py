from pydantic import BaseModel, Field


class SceneAnalysisInput(BaseModel):
    filename: str
    media_url: str


class SceneAnalysisResult(BaseModel):
    scene: str
    role: str
    opener: str
    labels: list[str] = Field(default_factory=list)
    confidence: float
