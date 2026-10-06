"""复盘文案离线评测台（审计 Schedule Later 18）。

针对 ReviewSummarizerAgent / REVIEW_PROMPT / ReviewCopy 的固定输入回归评测：
纯硬规则、无 LLM judge（复盘五维全部可确定性判定）。模块内公开纯函数供
always-on 单测（tests/modules/test_review_evaluation.py）与 RUN_REVIEW_EVAL
门控 live 评测（tests/modules/test_review_engine_live.py）两通道 import 复用。

与 api/modules/scene_engine/evaluation.py 形态同构（折叠函数 + 门控 runner +
JSONL 逐案重放落盘），但按引擎各建模块、互不依赖（design.md 1.1 定案）。
本模块是纯新增、被 import 时无 I/O / 网络副作用，生产链路零接触。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.core.config import settings
from api.modules.feedback_engine.schema import FeedbackResult
from api.modules.session_engine.prompts.review_prompts import REVIEW_PROMPT
from api.modules.session_engine.review_builder import (
    REVIEW_COPY_MAX_CHARS as REVIEW_COPY_FIELD_LIMITS,
)
from api.modules.session_engine.review_builder import (
    ReviewCopy,
)
from api.modules.session_engine.review_summarizer import ReviewSummarizerAgent

# 与 REVIEW_PROMPT 软约束逐字段一致的长度上限（字符数）：自 eval_prompt_fixes
# 批次起与生产同表——REVIEW_COPY_MAX_CHARS 是 review_builder 的生产单一事实源
# （ReviewCopy validator 按 cap 截断），别名 import 消除双源，评测与生产逐字段
# 一致，生产 cap 调整时评测长度维度自动跟随。


class ReviewEvaluationCase(BaseModel):
    """单组复盘评测固定输入（一次真实 summarize() 调用的可重放快照）。"""

    case_id: str
    scene: str
    role: str
    learner_message: str
    # 直接复用反馈引擎 schema：errors / cefr_level 全字段随契约覆盖，非预设
    # 场景（如 gym）与预设场景共用同一输入形态。
    feedback: FeedbackResult
    # 跨域中文关键词黑名单："不编造"的确定性代理断言（维度说明见
    # _unrelated_keyword_leaks 的局限注释）。fixture 侧保证黑名单非空。
    unrelated_topic_keywords: list[str] = Field(default_factory=list)


class ReviewCopyHardChecks(BaseModel):
    """五维硬规则逐项布尔（不依赖任何模型，纯文本判定）。"""

    structure_pass: bool
    chinese_pass: bool
    length_pass: bool
    no_scene_id_pass: bool
    topic_grounding_pass: bool

    @property
    def hard_pass(self) -> bool:
        """全部维度通过才算硬规则通过。"""
        return all(
            (
                self.structure_pass,
                self.chinese_pass,
                self.length_pass,
                self.no_scene_id_pass,
                self.topic_grounding_pass,
            )
        )

    @property
    def failure_reasons(self) -> list[str]:
        """按维度声明序给出失败原因，折叠层取首个作为结果行的 failure_reason。"""
        labels = (
            ("structure_pass", "review copy violates the five-key structure contract"),
            ("chinese_pass", "review copy contains a field without Chinese characters"),
            ("length_pass", "review copy exceeds the per-field length bound"),
            ("no_scene_id_pass", "review copy leaks the raw scene or role id"),
            ("topic_grounding_pass", "review copy mentions an unrelated topic keyword"),
        )
        return [label for name, label in labels if not getattr(self, name)]


class ReviewEvaluationResult(BaseModel):
    """单案折叠后的评测结果行（JSONL 落盘形态，字段与 coach 评测台对称）。"""

    case_id: str
    scene: str
    role: str
    provider: str
    model: str
    prompt_hash: str
    raw_output: dict[str, Any] | None
    # 字段名不用 copy：与 BaseModel.copy 方法重名会触发 pydantic 遮蔽告警。
    review_copy: dict[str, Any] | None
    structure_pass: bool
    chinese_pass: bool
    length_pass: bool
    no_scene_id_pass: bool
    topic_grounding_pass: bool
    hard_pass: bool
    final_pass: bool
    actual_outcome: Literal["copy", "graceful_failure"]
    failure_reason: str


def build_review_prompt_hash(prompt: str = REVIEW_PROMPT) -> str:
    """为复盘系统提示词生成短哈希（sha256 前 12 位，与 scene 评测台同构）。

    提示词一改哈希即变，历史 JSONL 结果可按 prompt_hash 归因。
    """
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


def evaluate_review_copy(*, case: ReviewEvaluationCase, copy: ReviewCopy) -> ReviewCopyHardChecks:
    """对一份复盘文案逐项执行硬规则；always-on 与 gated live 两通道共用。

    structure_pass 恒为 True：copy 能传进来说明已通过真实链路的
    parse_llm_json + ReviewCopy.model_validate（五键 min_length=1 + strip 前置
    校验），结构失败的样本根本不会产出 ReviewCopy 对象——结构维度的反向
    断言由单测直接打 model_validate 的 ValidationError 路径。
    """
    fields = _copy_fields(copy)
    return ReviewCopyHardChecks(
        structure_pass=True,
        chinese_pass=all(_contains_cjk(text) for text in fields.values()),
        length_pass=all(
            len(text) <= REVIEW_COPY_FIELD_LIMITS[name] for name, text in fields.items()
        ),
        no_scene_id_pass=not _scene_or_role_id_leaks(copy, case.scene, case.role),
        topic_grounding_pass=not _unrelated_keyword_leaks(
            list(fields.values()), case.unrelated_topic_keywords
        ),
    )


def evaluate_review_output(
    *,
    case: ReviewEvaluationCase,
    copy: ReviewCopy | None,
    actual_outcome: Literal["copy", "graceful_failure"],
    prompt_hash: str,
    failure_reason: str = "",
) -> ReviewEvaluationResult:
    """把一次 summarize() 结果折叠成统一评测结果（graceful_failure 沿 scene 分支形态）。

    failover 全败时 summarize() 上抛 ModelProviderError，runner 兜住后以
    actual_outcome="graceful_failure" 进来：五维全 False、final_pass=False，
    live 评测的 structure 通过率因此 <1.0 显形。
    """
    if actual_outcome != "copy":
        return ReviewEvaluationResult(
            case_id=case.case_id,
            scene=case.scene,
            role=case.role,
            provider=settings.text_primary_provider,
            model=settings.text_primary_model,
            prompt_hash=prompt_hash,
            raw_output=None,
            review_copy=None,
            structure_pass=False,
            chinese_pass=False,
            length_pass=False,
            no_scene_id_pass=False,
            topic_grounding_pass=False,
            hard_pass=False,
            final_pass=False,
            actual_outcome=actual_outcome,
            failure_reason=failure_reason or "graceful_failure",
        )

    if copy is None:
        raise ValueError("copy is required when actual_outcome='copy'")

    checks = evaluate_review_copy(case=case, copy=copy)
    reasons = checks.failure_reasons
    return ReviewEvaluationResult(
        case_id=case.case_id,
        scene=case.scene,
        role=case.role,
        provider=settings.text_primary_provider,
        model=settings.text_primary_model,
        prompt_hash=prompt_hash,
        raw_output=copy.model_dump(),
        review_copy=copy.model_dump(),
        structure_pass=checks.structure_pass,
        chinese_pass=checks.chinese_pass,
        length_pass=checks.length_pass,
        no_scene_id_pass=checks.no_scene_id_pass,
        topic_grounding_pass=checks.topic_grounding_pass,
        hard_pass=checks.hard_pass,
        final_pass=checks.hard_pass,
        actual_outcome="copy",
        failure_reason=reasons[0] if reasons else "",
    )


def load_review_evaluation_cases(path: str | Path) -> list[ReviewEvaluationCase]:
    """从 JSON 文件载入复盘评测样例；兼容顶层 {"comment": ..., "cases": [...]} 结构。

    fixtures 顶层用 comment 键记录约束（JSON 无注释语法），载入时只取 cases。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["cases"] if isinstance(data, dict) else data
    return [ReviewEvaluationCase.model_validate(item) for item in items]


async def run_review_evaluation(
    *,
    cases: list[ReviewEvaluationCase],
    output_path: str | Path,
    summarizer: ReviewSummarizerAgent | None = None,
) -> list[ReviewEvaluationResult]:
    """顺序逐案跑真实 summarize()（含 failover + parse_llm_json 校验路径），JSONL 落盘。

    每完成一案就把累积结果整文件重放写入（沿 scene 先例），中断时已完成的
    样本不丢。顺序即可：复盘是短文案单次调用，无 scene 图片分析的高延迟。
    """
    agent = summarizer or ReviewSummarizerAgent()
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_hash = build_review_prompt_hash()
    results: list[ReviewEvaluationResult] = []
    for case in cases:
        try:
            copy = await agent.summarize(
                scene=case.scene,
                role=case.role,
                learner_message=case.learner_message,
                feedback=case.feedback,
            )
        except Exception as exc:  # noqa: BLE001 - 评测台兜住任意 provider 异常并记为失败样本
            results.append(
                evaluate_review_output(
                    case=case,
                    copy=None,
                    actual_outcome="graceful_failure",
                    prompt_hash=prompt_hash,
                    failure_reason=f"graceful_failure: {exc}",
                )
            )
        else:
            results.append(
                evaluate_review_output(
                    case=case, copy=copy, actual_outcome="copy", prompt_hash=prompt_hash
                )
            )
        output_file.write_text(
            "".join(f"{item.model_dump_json()}\n" for item in results),
            encoding="utf-8",
        )
    return results


def _copy_fields(copy: ReviewCopy) -> dict[str, str]:
    """把 ReviewCopy 展开成有序字段表，供逐字段维度判定复用。"""
    return {
        "scene_title": copy.scene_title,
        "role_label": copy.role_label,
        "highlight": copy.highlight,
        "next_try": copy.next_try,
        "next_step": copy.next_step,
    }


def _contains_cjk(text: str) -> bool:
    """检测是否至少含 1 个 CJK 统一表意文字（复盘文案必须中文）。"""
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def identifier_variants(identifier: str) -> set[str]:
    """原始 id 的下划线↔空格变体集合（小写化）；空串剔除防子串恒真误判。"""
    normalized = identifier.strip().lower()
    return {normalized, normalized.replace("_", " "), normalized.replace(" ", "_")} - {""}


def _scene_or_role_id_leaks(copy: ReviewCopy, scene: str, role: str) -> bool:
    """scene/role 原始 id（含下划线↔空格变体、大小写不敏感）泄漏检测。

    REVIEW_PROMPT 明确禁止把原始 id 当标题（如 "coffee_shop"），只检查
    scene_title / role_label 两个字段——标题与标签是 id 泄漏的唯一自然位置。
    """
    surface = f"{copy.scene_title} {copy.role_label}".lower()
    return any(
        variant in surface
        for identifier in (scene, role)
        for variant in identifier_variants(identifier)
    )


def _unrelated_keyword_leaks(field_texts: list[str], keywords: list[str]) -> bool:
    """任一黑名单关键词出现在任一字段即判"编造 / 张冠李戴"。

    局限说明：正向断言"文案内容 ⊆ 反馈内容"需要跨语言语义判定（英文反馈 →
    中文文案），不可靠；故用跨域关键词黑名单做确定性代理——跨域词出现即说明
    文案脱离了本轮反馈语境。黑名单按场景选取，需避开该场景会自然出现的词。
    """
    return any(keyword in text for text in field_texts for keyword in keywords)
