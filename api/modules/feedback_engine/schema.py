from pydantic import BaseModel, Field, field_validator

# CEFR 封闭集合：模型幻觉值（如 "Z9"）防御为 None，契约稳定可断言。
_CEFR_LEVELS = frozenset({"A1", "A2", "B1", "B2", "C1", "C2"})


class FeedbackInput(BaseModel):
    learner_message: str
    scene: str
    vocab_candidates: list[str] = Field(default_factory=list)
    # 学员档案注入（只加可选字段，契约零破坏）：服务端渲染的有界注入块，
    # live 路径追加进 user prompt；mock 路径忽略（mock 输出不变）。
    learner_context: str | None = None


class FeedbackErrorItem(BaseModel):
    """一处结构化错误：分类取封闭集合，原文引用 + 纠正 + 一句解释。"""

    category: str
    original: str
    correction: str
    explanation: str


class FeedbackResult(BaseModel):
    grammar: str
    more_natural: str
    useful_words: list[str]
    # 只加不改（审计 Finding 20）：新字段全部带默认值，mock 路径、降级占位与
    # 既有构造（仅传三键）不受影响；前端对 feedback 为宽松解析，渲染零改动。
    errors: list[FeedbackErrorItem] = Field(default_factory=list)
    cefr_level: str | None = None

    @field_validator("cefr_level", mode="before")
    @classmethod
    def _normalize_cefr_level(cls, value: object) -> object:
        """strip + upper 归一；不在 A1..C2 封闭集合内的值一律归为 None。

        防御模型幻觉值（大小写、空白、编造级别），保证下游可按稳定集合断言。
        """
        if not isinstance(value, str):
            return None
        normalized = value.strip().upper()
        return normalized if normalized in _CEFR_LEVELS else None
