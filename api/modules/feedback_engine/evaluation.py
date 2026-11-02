"""反馈引擎离线评测台（缺口 G8 · 多 Agent 升级 P0 标准第 4 条）。

与 api/modules/coach_engine/evaluation.py 形态同构的评测台：固定输入样例集 +
硬规则校验器（always-on 单测与 RUN_FEEDBACK_EVAL 门控 live 评测共用同一组公开
纯函数）+ 可选 LLM judge（纠正准确 / 更自然 / 词汇有用）+ JSONL 逐案重放落盘。
按引擎各建模块、不抽公共层（design.md 1.1 定案），不跨引擎 import coach /
scene / session 评测台。

"生产代码零改动"约定：本模块是纯新增、被 import 时无 I/O / 网络副作用；
user prompt 装配经 prompts.build_feedback_user_prompt 单一装配点复用（与
live 链路字节一致），不复制装配逻辑；系统提示词即 FEEDBACK_PROMPT 常量。

硬规则五维依据 FEEDBACK_PROMPT 字段契约（验收卡 G8-FEEDBACK-1）：
结构封闭集合 / 引用保真 / grammar 文本形态 / more_natural 形态 / useful_words
数量与形态。cefr_level 不设维度：schema 写侧校验已把非法值归一为 None，
硬规则恒真无信息量（live 观测走 raw_output 与 judge）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.core.config import settings
from api.integrations.llm.json_utils import parse_llm_json
from api.integrations.llm.runtime import (
    TextCompletionProvider,
    provider_slot_from_settings,
)
from api.modules.feedback_engine.prompts.feedback_prompts import (
    FEEDBACK_PROMPT,
    build_feedback_user_prompt,
)
from api.modules.feedback_engine.schema import FeedbackInput, FeedbackResult

# 错误分类封闭集合（FEEDBACK_PROMPT 契约原文的九类；与 schema 写侧防御同源，
# 独立副本——评测台不 import agent/state，避免触发运行时装配面）。
FEEDBACK_ERROR_CATEGORIES = frozenset(
    {
        "grammar",
        "tense",
        "article",
        "preposition",
        "word_choice",
        "collocation",
        "register",
        "spelling",
        "other",
    }
)

MAX_ERRORS = 3
GRAMMAR_TEXT_MAX_CHARS = 320
EXPLANATION_MAX_WORDS = 40  # 契约 20 词，给 2 倍余量防误杀（与 coach 长度维度同哲学）
MORE_NATURAL_MAX_SENTENCES = 2
USEFUL_WORDS_MIN = 2
USEFUL_WORDS_MAX = 4
USEFUL_WORD_MAX_TOKENS = 4


class FeedbackEvaluationCase(BaseModel):
    """单组反馈评测固定输入（一次 review() 调用的完整可重放快照）。"""

    case_id: str
    scene: str
    learner_message: str
    # vocab_candidates 需满足 useful_words 维度的形态契约（0 个或 2-4 个、
    # 每项 1-4 个英文 token）——mock 通道直接透传该字段，fixture 载入测试
    # 显式断言该约束（与 coach fixture 约束写进 comment 的做法一致）。
    vocab_candidates: list[str] = Field(default_factory=list)
    learner_context: str | None = None


class FeedbackHardChecks(BaseModel):
    """五维硬规则逐项布尔（不依赖任何模型，纯文本判定）。"""

    structure_pass: bool
    quote_fidelity_pass: bool
    grammar_text_pass: bool
    more_natural_pass: bool
    useful_words_pass: bool

    @property
    def hard_pass(self) -> bool:
        """全部维度通过才算硬规则通过。"""
        return all(
            (
                self.structure_pass,
                self.quote_fidelity_pass,
                self.grammar_text_pass,
                self.more_natural_pass,
                self.useful_words_pass,
            )
        )

    @property
    def failure_reasons(self) -> list[str]:
        """按维度声明序给出失败原因，折叠层取首个作为结果行的 failure_reason。"""
        labels = (
            ("structure_pass", "errors violate the closed-set structure contract"),
            ("quote_fidelity_pass", "error.original does not quote the learner message"),
            ("grammar_text_pass", "grammar field violates the line/length contract"),
            ("more_natural_pass", "more_natural is empty, non-English or over 2 sentences"),
            ("useful_words_pass", "useful_words violate the count/shape contract"),
        )
        return [label for name, label in labels if not getattr(self, name)]


class FeedbackJudgeResult(BaseModel):
    """LLM judge 输出契约（strict JSON）：纠正准确 / 更自然 / 词汇有用。"""

    final_pass: bool
    correction_accuracy_pass: bool
    naturalness_pass: bool
    usefulness_pass: bool
    reason: str


class FeedbackEvaluationResult(BaseModel):
    """单案折叠后的评测结果行（JSONL 落盘形态）。"""

    case_id: str
    scene: str
    provider: str
    model: str
    prompt_hash: str
    learner_context_present: bool
    raw_output: dict[str, Any] | None
    structure_pass: bool
    quote_fidelity_pass: bool
    grammar_text_pass: bool
    more_natural_pass: bool
    useful_words_pass: bool
    hard_pass: bool
    judge_result: dict[str, Any] | None
    # judge 自身故障的观测键：正常路径恒 None；graceful_failure 分支也恒 None
    # （provider 失败时 judge 根本未被调用）。judge 缺席时 final_pass 回落
    # hard_pass——judge 是增强信号，以硬规则为准（沿 coach 评测台口径）。
    judge_error: str | None = None
    final_pass: bool
    actual_outcome: Literal["reply", "graceful_failure"]
    failure_reason: str


def build_feedback_prompt_hash() -> str:
    """为系统提示词生成短哈希（sha256 前 12 位，与 coach/scene 评测台同构）。

    绑定对象是 FEEDBACK_PROMPT 常量：反馈的系统提示词无每案动态注入
    （learner_context 在 user prompt），全样例哈希一致是预期形态；
    模板任一改动都会改变落盘哈希，历史结果可归因。
    """
    return hashlib.sha256(FEEDBACK_PROMPT.encode("utf-8")).hexdigest()[:12]


def build_feedback_evaluation_input(case: FeedbackEvaluationCase) -> FeedbackInput:
    """把评测用例组装成生产 FeedbackInput（runner 与 always-on 单测共用）。"""
    return FeedbackInput(
        learner_message=case.learner_message,
        scene=case.scene,
        vocab_candidates=list(case.vocab_candidates),
        learner_context=case.learner_context,
    )


def evaluate_feedback_result_hard_checks(
    *, feedback: FeedbackResult, learner_message: str
) -> FeedbackHardChecks:
    """对一份结构化反馈逐项执行五维硬规则；always-on 与 gated live 两通道共用。"""
    errors = feedback.errors
    structure_pass = len(errors) <= MAX_ERRORS and all(
        item.category in FEEDBACK_ERROR_CATEGORIES
        and item.original.strip() != ""
        and item.correction.strip() != ""
        and len(item.explanation.split()) <= EXPLANATION_MAX_WORDS
        for item in errors
    )
    # 引用保真（strip + 大小写不敏感）：模型引用学习者原句时首字母大写化、
    # 边缘空白都是正常形态；只要片段确出自原句即算保真。
    learner_lower = learner_message.lower()
    quote_fidelity_pass = all(item.original.strip().lower() in learner_lower for item in errors)
    grammar_lines = [line for line in feedback.grammar.splitlines() if line.strip()]
    if errors:
        grammar_text_pass = (
            feedback.grammar.strip() != ""
            and len(feedback.grammar) <= GRAMMAR_TEXT_MAX_CHARS
            and len(grammar_lines) == len(errors)
            and all(item.original.strip().lower() in feedback.grammar.lower() for item in errors)
        )
    else:
        grammar_text_pass = (
            feedback.grammar.strip() != "" and len(feedback.grammar) <= GRAMMAR_TEXT_MAX_CHARS
        )
    more_natural_pass = (
        feedback.more_natural.strip() != ""
        and _count_sentences(feedback.more_natural) <= MORE_NATURAL_MAX_SENTENCES
        and not _contains_non_english_script(feedback.more_natural)
    )
    useful_words_pass = USEFUL_WORDS_MIN <= len(feedback.useful_words) <= USEFUL_WORDS_MAX and all(
        _is_short_english_phrase(word) for word in feedback.useful_words
    )
    return FeedbackHardChecks(
        structure_pass=structure_pass,
        quote_fidelity_pass=quote_fidelity_pass,
        grammar_text_pass=grammar_text_pass,
        more_natural_pass=more_natural_pass,
        useful_words_pass=useful_words_pass,
    )


def evaluate_feedback_result(
    *,
    case: FeedbackEvaluationCase,
    feedback: FeedbackResult | None,
    actual_outcome: Literal["reply", "graceful_failure"],
    prompt_hash: str,
    judge_result: dict[str, Any] | FeedbackJudgeResult | None,
    judge_error: str | None = None,
    failure_reason: str = "",
) -> FeedbackEvaluationResult:
    """把一次模型反馈折叠成统一评测结果（graceful_failure 沿 coach 分支形态）。

    graceful_failure 时硬规则全 False、final_pass=False：live 评测通过率因此
    <1.0 显形，而不是静默丢样本。judge 缺席时 final_pass 回落 hard_pass。
    """
    if actual_outcome != "reply":
        return FeedbackEvaluationResult(
            case_id=case.case_id,
            scene=case.scene,
            provider=settings.text_primary_provider,
            model=settings.text_primary_model,
            prompt_hash=prompt_hash,
            learner_context_present=bool(case.learner_context),
            raw_output=None,
            structure_pass=False,
            quote_fidelity_pass=False,
            grammar_text_pass=False,
            more_natural_pass=False,
            useful_words_pass=False,
            hard_pass=False,
            judge_result=None,
            final_pass=False,
            actual_outcome=actual_outcome,
            failure_reason=failure_reason or "graceful_failure",
        )

    if feedback is None:
        raise ValueError("feedback is required when actual_outcome='reply'")

    checks = evaluate_feedback_result_hard_checks(
        feedback=feedback, learner_message=case.learner_message
    )
    judge = _normalize_judge_result(judge_result)
    reasons = checks.failure_reasons
    failure_reason = reasons[0] if reasons else ""
    if not failure_reason and judge is not None and not judge.final_pass:
        failure_reason = judge.reason
    final_pass = checks.hard_pass and (judge.final_pass if judge is not None else True)
    return FeedbackEvaluationResult(
        case_id=case.case_id,
        scene=case.scene,
        provider=settings.text_primary_provider,
        model=settings.text_primary_model,
        prompt_hash=prompt_hash,
        learner_context_present=bool(case.learner_context),
        raw_output=feedback.model_dump(),
        structure_pass=checks.structure_pass,
        quote_fidelity_pass=checks.quote_fidelity_pass,
        grammar_text_pass=checks.grammar_text_pass,
        more_natural_pass=checks.more_natural_pass,
        useful_words_pass=checks.useful_words_pass,
        hard_pass=checks.hard_pass,
        judge_result=judge.model_dump() if judge is not None else None,
        judge_error=judge_error,
        final_pass=final_pass,
        actual_outcome="reply",
        failure_reason=failure_reason,
    )


def load_feedback_evaluation_cases(path: str | Path) -> list[FeedbackEvaluationCase]:
    """从 JSON 文件载入反馈评测样例；兼容顶层 {"comment": ..., "cases": [...]} 结构。

    fixtures 顶层用 comment 键记录约束（JSON 无注释语法），载入时只取 cases。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["cases"] if isinstance(data, dict) else data
    return [FeedbackEvaluationCase.model_validate(item) for item in items]


class FeedbackJudge:
    """可选 LLM 裁判（live-only）：与 CoachReplyJudge 同构的二次判定器。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        """保存用于二次裁判的文本模型客户端。"""
        from api.integrations.llm.openai import OpenAICompatibleClient

        self.client = OpenAICompatibleClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )

    @classmethod
    def from_env(cls) -> FeedbackJudge | None:
        """从 FEEDBACK_EVAL_JUDGE_* 环境变量解析裁判模型，缺省回落 text 主 provider。

        provider 为空 / mock 时返回 None（评测仍可跑，只缺 judge 维度）。
        """
        provider = (
            (os.getenv("FEEDBACK_EVAL_JUDGE_PROVIDER") or settings.text_primary_provider)
            .strip()
            .lower()
        )
        if provider in {"", "mock"}:
            return None

        base_url = os.getenv("FEEDBACK_EVAL_JUDGE_BASE_URL") or settings.text_primary_base_url
        api_key = os.getenv("FEEDBACK_EVAL_JUDGE_API_KEY") or settings.text_primary_api_key
        model = os.getenv("FEEDBACK_EVAL_JUDGE_MODEL") or settings.text_primary_model
        timeout_seconds = int(
            os.getenv("FEEDBACK_EVAL_JUDGE_TIMEOUT_SECONDS")
            or settings.text_primary_timeout_seconds
        )
        if not base_url or not model:
            return None
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )

    def judge(
        self, *, case: FeedbackEvaluationCase, feedback: FeedbackResult
    ) -> FeedbackJudgeResult:
        """用文本模型补充判断纠正准确度 / 更自然改写 / 词汇有用性。"""
        raw = self.client.complete_text(
            system_prompt=(
                "You judge whether an English writing coach's structured feedback is "
                "accurate and helpful for a speaking-practice learner. Return strict JSON "
                "only with keys: final_pass, correction_accuracy_pass, naturalness_pass, "
                "usefulness_pass, reason."
            ),
            user_prompt="\n".join(
                [
                    f"Scene: {case.scene}",
                    f"Learner message: {case.learner_message}",
                    f"Coach feedback JSON: {feedback.model_dump_json()}",
                ]
            ),
        )
        return FeedbackJudgeResult.model_validate(parse_llm_json(raw))


async def run_feedback_evaluation(
    *,
    cases: list[FeedbackEvaluationCase],
    output_path: str | Path,
    text_provider: TextCompletionProvider | None = None,
    judge: FeedbackJudge | None = None,
) -> list[FeedbackEvaluationResult]:
    """顺序逐案跑完整批样例，并逐案把累积结果整文件重放写入输出文件。

    默认用 text 主槽位构造 TextCompletionProvider（与反馈引擎 live 路径同款
    装配：json_mode + feedback token 预算）。顺序即可：反馈是短文本 JSON 请求，
    量级无需并发。每完成一案就重放写盘，中断时已完成样本不丢。
    """
    provider = text_provider or _build_default_text_provider()
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    results: list[FeedbackEvaluationResult] = []
    prompt_hash = build_feedback_prompt_hash()
    for case in cases:
        try:
            feedback = await _request_feedback(provider, build_feedback_evaluation_input(case))
        except Exception as exc:  # noqa: BLE001 - 评测台兜住任意 provider 异常并记为失败样本
            results.append(
                evaluate_feedback_result(
                    case=case,
                    feedback=None,
                    actual_outcome="graceful_failure",
                    prompt_hash=prompt_hash,
                    judge_result=None,
                    failure_reason=f"graceful_failure: {exc}",
                )
            )
        else:
            judge_result = None
            judge_error: str | None = None
            if judge is not None:
                # judge 是增强信号，其自身故障不应炸掉评测：兜住后记 judge_error、
                # judge 置空，final_pass 在折叠层自动回落 hard_pass（以硬规则为准）。
                try:
                    judge_result = await asyncio.to_thread(
                        judge.judge, case=case, feedback=feedback
                    )
                except Exception as exc:  # noqa: BLE001 - 与 provider 兜底同口径
                    judge_result = None
                    judge_error = f"judge_failed: {exc}"
            results.append(
                evaluate_feedback_result(
                    case=case,
                    feedback=feedback,
                    actual_outcome="reply",
                    prompt_hash=prompt_hash,
                    judge_result=judge_result,
                    judge_error=judge_error,
                )
            )
        output_file.write_text(
            "".join(f"{item.model_dump_json()}\n" for item in results),
            encoding="utf-8",
        )
    return results


def _build_default_text_provider() -> TextCompletionProvider:
    """按 settings 构造 text 主槽位 provider（与反馈引擎 live 路径同款装配）。"""
    return TextCompletionProvider(
        provider_slot_from_settings("text", "primary"),
        json_mode=settings.llm_json_mode_enabled,
        max_tokens=settings.llm_feedback_max_tokens,
    )


async def _request_feedback(
    provider: TextCompletionProvider, payload: FeedbackInput
) -> FeedbackResult:
    """调用文本模型并校验结构化输出（与 FeedbackEngineAgent._request_feedback 同构）。

    不 import agent 的私有函数：评测台经 provider.complete + FEEDBACK_PROMPT +
    build_feedback_user_prompt 复用同一装配路径，解析失败按 provider 错误上抛，
    由 runner 兜成 graceful_failure。
    """
    raw = await provider.complete(
        system_prompt=FEEDBACK_PROMPT,
        user_prompt=build_feedback_user_prompt(payload),
    )
    return FeedbackResult.model_validate(parse_llm_json(raw))


def _count_sentences(text: str) -> int:
    """按终止标点切句计数（more_natural 的 ≤2 句契约检查）。"""
    return len([part for part in re.split(r"[.!?]+(?:\s|$)", text.strip()) if part.strip()])


def _is_short_english_phrase(word: str) -> bool:
    """useful_words 条目形态：1-4 个英文 token（字母/撇号/连字符/空格）。"""
    tokens = re.findall(r"[a-z']+", word.lower())
    return (
        bool(tokens)
        and len(tokens) <= USEFUL_WORD_MAX_TOKENS
        and not _contains_non_english_script(word)
    )


def _contains_non_english_script(text: str) -> bool:
    """检测 CJK 统一表意文字 / 谚文 / 假名字符（反馈产出全英文契约）。"""
    return any(
        ("\u4e00" <= char <= "\u9fff")
        or ("\uac00" <= char <= "\ud7af")
        or ("\u3040" <= char <= "\u30ff")
        for char in text
    )


def _normalize_judge_result(
    value: dict[str, Any] | FeedbackJudgeResult | None,
) -> FeedbackJudgeResult | None:
    """把裁判结果统一成模型对象，方便后续序列化（沿 coach/scene 先例）。"""
    if value is None:
        return None
    if isinstance(value, FeedbackJudgeResult):
        return value
    return FeedbackJudgeResult.model_validate(value)
