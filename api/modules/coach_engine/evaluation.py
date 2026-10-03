"""教练回复离线评测台（审计 Schedule Later 18）。

与 api/modules/scene_engine/evaluation.py 形态同构的评测台：固定输入样例集 +
硬规则校验器（always-on 单测与 RUN_COACH_EVAL 门控 live 评测共用同一组公开纯
函数）+ 可选 LLM judge（角色贴合 / CEFR 适配 / 一小步拉伸）+ JSONL 逐案重放
落盘。按引擎各建模块、不抽公共层（design.md 1.1 定案），不跨引擎 import
scene_engine / session_engine。

"生产代码零改动"约定：本模块是纯新增、被 import 时无 I/O / 网络副作用；不得
直接 import provider 的私有拼装函数 _build_coach_user_prompt——真实提示词
拼装路径经 OpenAICompatibleChatProvider.reply() 间接覆盖（live 评测与 judge
专用，always-on 通道用 MockChatProvider）。
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
from api.integrations.llm.openai import OpenAICompatibleClient
from api.models.message_model import Message
from api.modules.coach_engine.prompts.coach_prompts import build_coach_system_prompt
from api.modules.coach_engine.providers.chat_provider import (
    ChatProvider,
    OpenAICompatibleChatProvider,
)
from api.modules.coach_engine.schema import CoachReplyInput

# 教练侧 meta 泄漏黑名单：场景评测台 META_OPENER_TOKENS（scene_engine/
# evaluation.py）的扩展自持副本——刻意不做跨引擎 import（避免 coach_engine →
# scene_engine 依赖），并按教练语境追加语言模型自暴露与"无图可看"类 token
# （教练拿到的 visual anchors 是文本线索，回复宣称看不见输入比场景台更不可接受）。
COACH_META_LEAK_TOKENS = (
    "as an ai",
    "as a language model",
    "i am an ai",
    "i'm an ai",
    "i cannot see the image",
    "i can't see the image",
    "i cannot see",
    "i can't see",
    "this image shows",
    "the image shows",
)

# 不复读原句的豁免阈值："yes please" 这类短应答在教练回复里自然复现是正常对话
# 行为，按整句连续子序列匹配必然误报，故少于 4 个 token 的学习者消息豁免。
NO_ECHO_MIN_TOKENS = 4

# 长度上限（词数）：提示词契约是 "at most 3 short sentences plus one follow-up
# question"，上限给足余量防误杀，只拦截明显失控的长输出。
COACH_REPLY_MAX_WORDS = 80


class CoachReplyMessage(BaseModel):
    """评测用例里的最近消息（role/text 两键，镜像生产 Message 的最小面）。"""

    role: str
    text: str


class CoachReplyEvaluationCase(BaseModel):
    """单组教练评测固定输入（一次 reply() 调用的完整可重放快照）。"""

    case_id: str
    scene: str
    role: str
    learner_message: str
    visual_anchors: list[str] = Field(default_factory=list)
    vocab_candidates: list[str] = Field(default_factory=list)
    recent_messages: list[CoachReplyMessage] = Field(default_factory=list)
    # learner_cefr 注入 build_coach_system_prompt 覆盖水平行；learner_context 是
    # 服务端渲染形态的有界注入块字符串——fixture 直接给字符串，评测台不依赖
    # learner_profile 渲染器（渲染器归 session_engine，已有独立测试锁定）。
    learner_cefr: str | None = None
    learner_context: str | None = None


class CoachReplyHardChecks(BaseModel):
    """五维硬规则逐项布尔（不依赖任何模型，纯文本判定）。"""

    english_only_pass: bool
    length_pass: bool
    follow_up_pass: bool
    meta_leak_pass: bool
    no_echo_pass: bool

    @property
    def hard_pass(self) -> bool:
        """全部维度通过才算硬规则通过。"""
        return all(
            (
                self.english_only_pass,
                self.length_pass,
                self.follow_up_pass,
                self.meta_leak_pass,
                self.no_echo_pass,
            )
        )

    @property
    def failure_reasons(self) -> list[str]:
        """按维度声明序给出失败原因，折叠层取首个作为结果行的 failure_reason。"""
        labels = (
            ("english_only_pass", "reply is not English only"),
            ("length_pass", "reply is empty or exceeds the length bound"),
            ("follow_up_pass", "reply must contain exactly one follow-up question"),
            ("meta_leak_pass", "reply leaks meta/AI phrasing"),
            ("no_echo_pass", "reply echoes the learner message verbatim"),
        )
        return [label for name, label in labels if not getattr(self, name)]


class CoachJudgeResult(BaseModel):
    """LLM judge 输出契约（strict JSON）：三维度对应 prd R1 的角色贴合 /
    CEFR 适配 / 一小步拉伸。"""

    final_pass: bool
    role_fit_pass: bool
    cefr_fit_pass: bool
    stretch_pass: bool
    reason: str


class CoachEvaluationResult(BaseModel):
    """单案折叠后的评测结果行（JSONL 落盘形态）。"""

    case_id: str
    scene: str
    role: str
    learner_cefr: str | None
    provider: str
    model: str
    prompt_hash: str
    learner_context_present: bool
    raw_output: dict[str, Any] | None
    english_only_pass: bool
    length_pass: bool
    follow_up_pass: bool
    meta_leak_pass: bool
    no_echo_pass: bool
    hard_pass: bool
    judge_result: dict[str, Any] | None
    final_pass: bool
    actual_outcome: Literal["reply", "graceful_failure"]
    failure_reason: str


def build_coach_prompt_hash(system_prompt: str) -> str:
    """为实际发送的系统提示词生成短哈希（sha256 前 12 位，与 scene 评测台同构）。

    绑定对象是每组实际发送的系统提示词（build_coach_system_prompt(
    case.learner_cefr) 的输出）而非模板常量：B1/B2 用例哈希天然不同，模板或
    CEFR 注入值任一变化都会改变落盘哈希，历史结果可归因。
    """
    return hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:12]


def normalize_english_tokens(text: str) -> list[str]:
    """小写化后取英文 token 序列（含撇号），供 no_echo 的连续子序列匹配使用。"""
    return re.findall(r"[a-z']+", text.lower())


def evaluate_coach_reply_hard_checks(
    *, reply_text: str, learner_message: str
) -> CoachReplyHardChecks:
    """对一条教练回复逐项执行五维硬规则；always-on 与 gated live 两通道共用。

    维度与依据（design.md 2.2）：仅英语（系统提示词 "Reply in English only"）、
    词数有界（"at most 3 short sentences plus one follow-up question"）、追问
    存在且恰好一次（"one follow-up question"）、meta 泄漏黑名单、不复读学习者
    原句（≥4 token 的整句连续子序列匹配，短句豁免防误报）。
    """
    words = reply_text.split()
    learner_tokens = normalize_english_tokens(learner_message)
    reply_tokens = normalize_english_tokens(reply_text)
    no_echo_pass = True
    if len(learner_tokens) >= NO_ECHO_MIN_TOKENS:
        # 只有完整复读学习者原句才判失败；零散词重叠（话题词、虚词）不误报。
        no_echo_pass = not _contains_contiguous_subsequence(reply_tokens, learner_tokens)
    return CoachReplyHardChecks(
        english_only_pass=not _contains_non_english_script(reply_text),
        length_pass=bool(words) and len(words) <= COACH_REPLY_MAX_WORDS,
        # 学习者原句复读已被独立维度禁止，问号不会被借道混入。
        follow_up_pass=reply_text.count("?") == 1,
        meta_leak_pass=not any(token in reply_text.lower() for token in COACH_META_LEAK_TOKENS),
        no_echo_pass=no_echo_pass,
    )


def build_coach_reply_input(case: CoachReplyEvaluationCase) -> CoachReplyInput:
    """把评测用例组装成生产 CoachReplyInput（runner 与 always-on 单测共用）。

    recent_messages 需从评测镜像模型转回生产 Message 模型（评测台不假设
    Message 的 id/feedback/created_at 字段，fixture 只承诺 role/text）。
    """
    return CoachReplyInput(
        scene=case.scene,
        role=case.role,
        learner_message=case.learner_message,
        visual_anchors=list(case.visual_anchors),
        vocab_candidates=list(case.vocab_candidates),
        recent_messages=[
            Message(role=message.role, text=message.text) for message in case.recent_messages
        ],
        learner_context=case.learner_context,
        learner_cefr=case.learner_cefr,
    )


def evaluate_coach_reply(
    *,
    case: CoachReplyEvaluationCase,
    reply_text: str | None,
    actual_outcome: Literal["reply", "graceful_failure"],
    prompt_hash: str,
    judge_result: dict[str, Any] | CoachJudgeResult | None,
    failure_reason: str = "",
) -> CoachEvaluationResult:
    """把一次模型回复折叠成统一评测结果（graceful_failure 沿 scene 分支形态）。

    graceful_failure 时硬规则全 False、final_pass=False：live 评测通过率因此
    <1.0 显形，而不是静默丢样本。
    """
    if actual_outcome != "reply":
        return CoachEvaluationResult(
            case_id=case.case_id,
            scene=case.scene,
            role=case.role,
            learner_cefr=case.learner_cefr,
            provider=settings.text_primary_provider,
            model=settings.text_primary_model,
            prompt_hash=prompt_hash,
            learner_context_present=bool(case.learner_context),
            raw_output=None,
            english_only_pass=False,
            length_pass=False,
            follow_up_pass=False,
            meta_leak_pass=False,
            no_echo_pass=False,
            hard_pass=False,
            judge_result=None,
            final_pass=False,
            actual_outcome=actual_outcome,
            failure_reason=failure_reason or "graceful_failure",
        )

    if reply_text is None:
        raise ValueError("reply_text is required when actual_outcome='reply'")

    checks = evaluate_coach_reply_hard_checks(
        reply_text=reply_text, learner_message=case.learner_message
    )
    judge = _normalize_judge_result(judge_result)
    reasons = checks.failure_reasons
    failure_reason = reasons[0] if reasons else ""
    if not failure_reason and judge is not None and not judge.final_pass:
        failure_reason = judge.reason
    final_pass = checks.hard_pass and (judge.final_pass if judge is not None else True)
    return CoachEvaluationResult(
        case_id=case.case_id,
        scene=case.scene,
        role=case.role,
        learner_cefr=case.learner_cefr,
        provider=settings.text_primary_provider,
        model=settings.text_primary_model,
        prompt_hash=prompt_hash,
        learner_context_present=bool(case.learner_context),
        raw_output={"text": reply_text},
        english_only_pass=checks.english_only_pass,
        length_pass=checks.length_pass,
        follow_up_pass=checks.follow_up_pass,
        meta_leak_pass=checks.meta_leak_pass,
        no_echo_pass=checks.no_echo_pass,
        hard_pass=checks.hard_pass,
        judge_result=judge.model_dump() if judge is not None else None,
        final_pass=final_pass,
        actual_outcome="reply",
        failure_reason=failure_reason,
    )


def load_coach_evaluation_cases(path: str | Path) -> list[CoachReplyEvaluationCase]:
    """从 JSON 文件载入教练评测样例；兼容顶层 {"comment": ..., "cases": [...]} 结构。

    fixtures 顶层用 comment 键记录约束（JSON 无注释语法），载入时只取 cases。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data["cases"] if isinstance(data, dict) else data
    return [CoachReplyEvaluationCase.model_validate(item) for item in items]


class CoachReplyJudge:
    """可选 LLM 裁判（live-only）：与 SceneOutputJudge 同构的二次判定器。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        """保存用于二次裁判的文本模型客户端。"""
        self.client = OpenAICompatibleClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )

    @classmethod
    def from_env(cls) -> CoachReplyJudge | None:
        """从 COACH_EVAL_JUDGE_* 环境变量解析裁判模型，缺省回落 text 主 provider。

        provider 为空 / mock 时返回 None（评测仍可跑，只缺 judge 维度）。
        """
        provider = (
            (os.getenv("COACH_EVAL_JUDGE_PROVIDER") or settings.text_primary_provider)
            .strip()
            .lower()
        )
        if provider in {"", "mock"}:
            return None

        base_url = os.getenv("COACH_EVAL_JUDGE_BASE_URL") or settings.text_primary_base_url
        api_key = os.getenv("COACH_EVAL_JUDGE_API_KEY") or settings.text_primary_api_key
        model = os.getenv("COACH_EVAL_JUDGE_MODEL") or settings.text_primary_model
        timeout_seconds = int(
            os.getenv("COACH_EVAL_JUDGE_TIMEOUT_SECONDS") or settings.text_primary_timeout_seconds
        )
        if not base_url or not model:
            return None
        return cls(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )

    def judge(self, *, case: CoachReplyEvaluationCase, reply_text: str) -> CoachJudgeResult:
        """用文本模型补充判断角色贴合度 / CEFR 适配度 / 一小步拉伸。"""
        raw = self.client.complete_text(
            system_prompt=(
                "You judge whether a coach reply is suitable for English speaking practice. "
                "Return strict JSON only with keys: final_pass, role_fit_pass, cefr_fit_pass, "
                "stretch_pass, reason."
            ),
            user_prompt="\n".join(
                [
                    f"Scene: {case.scene}",
                    f"Role: {case.role}",
                    f"Learner CEFR: {case.learner_cefr or 'unknown'}",
                    f"Learner message: {case.learner_message}",
                    f"Coach reply: {reply_text}",
                ]
            ),
        )
        return CoachJudgeResult.model_validate(parse_llm_json(raw))


async def run_coach_evaluation(
    *,
    cases: list[CoachReplyEvaluationCase],
    output_path: str | Path,
    chat_provider: ChatProvider | None = None,
    judge: CoachReplyJudge | None = None,
) -> list[CoachEvaluationResult]:
    """顺序逐案跑完整批样例，并逐案把累积结果整文件重放写入输出文件。

    默认用 text 主槽位构造 OpenAICompatibleChatProvider（真实拼装路径经
    reply() 间接覆盖）。顺序即可：教练单次调用是短文本请求，量级与 scene
    图片分析不同，无需并发。每完成一案就重放写盘，中断时已完成样本不丢。
    """
    provider = chat_provider or OpenAICompatibleChatProvider(
        base_url=settings.text_primary_base_url,
        api_key=settings.text_primary_api_key,
        model=settings.text_primary_model,
        timeout_seconds=settings.text_primary_timeout_seconds,
    )
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    results: list[CoachEvaluationResult] = []
    for case in cases:
        # 哈希绑定每组实际发送的系统提示词：模板或 CEFR 任一变化即可归因。
        prompt_hash = build_coach_prompt_hash(build_coach_system_prompt(case.learner_cefr))
        try:
            reply = await provider.reply(build_coach_reply_input(case))
        except Exception as exc:  # noqa: BLE001 - 评测台兜住任意 provider 异常并记为失败样本
            results.append(
                evaluate_coach_reply(
                    case=case,
                    reply_text=None,
                    actual_outcome="graceful_failure",
                    prompt_hash=prompt_hash,
                    judge_result=None,
                    failure_reason=f"graceful_failure: {exc}",
                )
            )
        else:
            judge_result = None
            if judge is not None and reply.text.strip():
                judge_result = await asyncio.to_thread(
                    judge.judge, case=case, reply_text=reply.text
                )
            results.append(
                evaluate_coach_reply(
                    case=case,
                    reply_text=reply.text,
                    actual_outcome="reply",
                    prompt_hash=prompt_hash,
                    judge_result=judge_result,
                )
            )
        output_file.write_text(
            "".join(f"{item.model_dump_json()}\n" for item in results),
            encoding="utf-8",
        )
    return results


def _contains_non_english_script(text: str) -> bool:
    """检测 CJK 统一表意文字 / 谚文 / 假名字符（系统提示词要求 Reply in English only）。"""
    return any(
        ("\u4e00" <= char <= "\u9fff")
        or ("\uac00" <= char <= "\ud7af")
        or ("\u3040" <= char <= "\u30ff")
        for char in text
    )


def _contains_contiguous_subsequence(haystack: list[str], needle: list[str]) -> bool:
    """判断 needle 是否作为连续子序列出现在 haystack 中（no_echo 的匹配原语）。"""
    if not needle:
        return False
    width = len(needle)
    return any(
        haystack[index : index + width] == needle for index in range(len(haystack) - width + 1)
    )


def _normalize_judge_result(
    value: dict[str, Any] | CoachJudgeResult | None,
) -> CoachJudgeResult | None:
    """把裁判结果统一成模型对象，方便后续序列化（沿 scene 先例）。"""
    if value is None:
        return None
    if isinstance(value, CoachJudgeResult):
        return value
    return CoachJudgeResult.model_validate(value)
