from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator


def _normalize_scene(value: object) -> str:
    """把场景名归一化为稳定的 snake_case 标识。"""
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _normalize_phrase(value: object) -> str:
    """压缩空白并保留短语原始语义。"""
    return re.sub(r"\s+", " ", str(value).strip())


def _normalize_keywords(value: object, *, field_name: str) -> list[str]:
    """清洗关键词列表并按出现顺序去重。"""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")

    normalized_labels: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _normalize_phrase(item).lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_labels.append(normalized)
    return normalized_labels


class SceneAnalysisInput(BaseModel):
    filename: str
    media_url: str


class SceneAnalysisResult(BaseModel):
    scene: str
    role: str
    opener: str
    visual_anchors: list[str] = Field(default_factory=list)
    vocab_candidates: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    confidence: float

    @field_validator("scene", mode="before")
    @classmethod
    def normalize_scene(cls, value: object) -> str:
        """确保场景字段在入模前就符合内部标识规范。"""
        normalized = _normalize_scene(value)
        if not normalized:
            raise ValueError("scene must not be empty")
        return normalized

    @field_validator("role", "opener", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: object) -> str:
        """统一 role 和 opener 的空白格式，避免模型输出噪音。"""
        normalized = _normalize_phrase(value)
        if not normalized:
            raise ValueError("text fields must not be empty")
        return normalized

    @field_validator("visual_anchors", "vocab_candidates", "labels", mode="before")
    @classmethod
    def normalize_keyword_fields(cls, value: object, info) -> list[str]:
        """复用同一套规则清洗可练习关键词字段。"""
        return _normalize_keywords(value, field_name=info.field_name)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float) -> float:
        """限制置信度范围，避免 provider 返回越界分数。"""
        if not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value

    @model_validator(mode="after")
    def fill_compatibility_keywords(self) -> "SceneAnalysisResult":
        """兼容旧字段 labels，并回填统一后的聚合标签列表。"""
        if self.labels and not self.vocab_candidates and not self.visual_anchors:
            self.vocab_candidates = list(self.labels)

        aggregate = []
        seen: set[str] = set()
        for value in [*self.visual_anchors, *self.vocab_candidates]:
            if value in seen:
                continue
            seen.add(value)
            aggregate.append(value)

        self.labels = aggregate or list(self.labels)
        return self
