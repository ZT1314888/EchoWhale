from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from api.common.exceptions import UnsupportedSceneImageError
from api.core.config import settings
from api.integrations.llm.openai import OpenAICompatibleClient
from api.modules.scene_engine.evaluation_rules import match_expected_keywords
from api.modules.scene_engine.evaluation_rules import vocab_candidates_are_valuable
from api.modules.scene_engine.prompts.scene_prompts import SCENE_INFERENCE_PROMPT
from api.modules.scene_engine.prompts.scene_prompts import SCENE_PROMPT_VERSION
from api.modules.scene_engine.schema import SceneAnalysisResult
from api.modules.scene_engine.service import SceneEngineService


META_OPENER_TOKENS = (
    "as an ai",
    "i cannot see the image",
    "i can't see the image",
    "this image shows",
    "the image shows",
)


class SceneEvaluationCase(BaseModel):
    sample_id: str
    filename: str
    signed_url: str
    expected_scene: str
    expected_visual_anchor_keywords: list[str]
    expected_vocab_keywords: list[str]
    expected_role_keywords: list[str]
    sample_type: Literal["normal", "edge_case"]
    expected_outcome: Literal["analysis", "unsupported_image"] = "analysis"


class SceneJudgeResult(BaseModel):
    final_pass: bool
    role_fit_pass: bool
    opener_natural_pass: bool
    conversation_ready_pass: bool
    reason: str


class SceneEvaluationResult(BaseModel):
    sample_id: str
    sample_type: str
    expected_outcome: str
    actual_outcome: str
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str
    raw_output: dict[str, Any] | None
    normalized_output: dict[str, Any] | None
    hard_checks_pass: bool
    scene_match: bool
    visual_anchor_match: bool
    vocab_match: bool
    vocab_value_pass: bool
    judge_result: dict[str, Any] | None
    final_pass: bool
    failure_reason: str


def build_scene_prompt_hash(prompt: str = SCENE_INFERENCE_PROMPT) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


def evaluate_scene_output(
    *,
    case: SceneEvaluationCase,
    output: SceneAnalysisResult | None,
    prompt_version: str,
    prompt_hash: str,
    judge_result: dict[str, Any] | SceneJudgeResult | None,
    actual_outcome: Literal["analysis", "unsupported_image", "graceful_failure"] = "analysis",
    failure_reason: str = "",
) -> SceneEvaluationResult:
    if actual_outcome != "analysis":
        outcome_matches = actual_outcome == case.expected_outcome
        return SceneEvaluationResult(
            sample_id=case.sample_id,
            sample_type=case.sample_type,
            expected_outcome=case.expected_outcome,
            actual_outcome=actual_outcome,
            provider=settings.vision_primary_provider,
            model=settings.vision_primary_model,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            raw_output=None,
            normalized_output=None,
            hard_checks_pass=outcome_matches,
            scene_match=False,
            visual_anchor_match=False,
            vocab_match=False,
            vocab_value_pass=False,
            judge_result=None,
            final_pass=outcome_matches,
            failure_reason="" if outcome_matches else (
                failure_reason
                or f"outcome mismatch: expected {case.expected_outcome}, got {actual_outcome}"
            ),
        )

    if output is None:
        raise ValueError("output is required when actual_outcome='analysis'")

    hard_failure = _get_hard_failure_reason(output)
    judge = _normalize_judge_result(judge_result)
    scene_match = output.scene == case.expected_scene
    visual_anchor_match = match_expected_keywords(
        case.expected_visual_anchor_keywords,
        output.visual_anchors,
    )
    vocab_match = match_expected_keywords(
        case.expected_vocab_keywords,
        output.vocab_candidates,
    )
    vocab_value_pass = vocab_candidates_are_valuable(
        case.expected_scene,
        output.vocab_candidates,
    )

    failure_reason = hard_failure or ""
    if not failure_reason and not scene_match:
        failure_reason = f"scene mismatch: expected {case.expected_scene}, got {output.scene}"
    if not failure_reason and not visual_anchor_match:
        failure_reason = "visual anchor mismatch"
    if not failure_reason and not vocab_match:
        failure_reason = "vocab mismatch"
    if not failure_reason and not vocab_value_pass:
        failure_reason = "vocab candidates are not practice-ready"
    if not failure_reason and judge is not None and not judge.final_pass:
        failure_reason = judge.reason

    final_pass = not failure_reason and (judge.final_pass if judge is not None else True)
    return SceneEvaluationResult(
        sample_id=case.sample_id,
        sample_type=case.sample_type,
        expected_outcome=case.expected_outcome,
        actual_outcome=actual_outcome,
        provider=settings.vision_primary_provider,
        model=settings.vision_primary_model,
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        raw_output=output.model_dump(),
        normalized_output=output.model_dump(),
        hard_checks_pass=hard_failure == "",
        scene_match=scene_match,
        visual_anchor_match=visual_anchor_match,
        vocab_match=vocab_match,
        vocab_value_pass=vocab_value_pass,
        judge_result=judge.model_dump() if judge is not None else None,
        final_pass=final_pass,
        failure_reason=failure_reason,
    )


def load_scene_evaluation_cases(path: str | Path) -> list[SceneEvaluationCase]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [SceneEvaluationCase.model_validate(item) for item in data]


class SceneOutputJudge:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
    ) -> None:
        self.client = OpenAICompatibleClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
        )

    @classmethod
    def from_env(cls) -> "SceneOutputJudge | None":
        provider = (
            os.getenv("SCENE_EVAL_JUDGE_PROVIDER")
            or settings.text_primary_provider
        ).strip().lower()
        if provider in {"", "mock"}:
            return None

        base_url = os.getenv("SCENE_EVAL_JUDGE_BASE_URL") or settings.text_primary_base_url
        api_key = os.getenv("SCENE_EVAL_JUDGE_API_KEY") or settings.text_primary_api_key
        model = os.getenv("SCENE_EVAL_JUDGE_MODEL") or settings.text_primary_model
        timeout_seconds = int(
            os.getenv("SCENE_EVAL_JUDGE_TIMEOUT_SECONDS")
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

    def judge(self, *, case: SceneEvaluationCase, output: SceneAnalysisResult) -> SceneJudgeResult:
        raw = self.client.complete_text(
            system_prompt=(
                "You judge whether a generated role and opener are suitable for English "
                "speaking practice. Return strict JSON only with keys: final_pass, "
                "role_fit_pass, opener_natural_pass, conversation_ready_pass, reason."
            ),
            user_prompt="\n".join(
                [
                    f"Expected scene: {case.expected_scene}",
                    f"Expected role keywords: {', '.join(case.expected_role_keywords) or 'none'}",
                    f"Role: {output.role}",
                    f"Opener: {output.opener}",
                ]
            ),
        )
        return SceneJudgeResult.model_validate(_load_json(raw))


async def run_scene_evaluation(
    *,
    cases: list[SceneEvaluationCase],
    output_path: str | Path,
    scene_service: SceneEngineService | None = None,
    judge: SceneOutputJudge | None = None,
    max_concurrency: int = 5,
) -> list[SceneEvaluationResult]:
    service = scene_service or SceneEngineService()
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_hash = build_scene_prompt_hash()
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    results: list[SceneEvaluationResult] = []

    async def evaluate_case(case: SceneEvaluationCase) -> SceneEvaluationResult:
        async with semaphore:
            try:
                output = await asyncio.to_thread(service.analyze, case.filename, case.signed_url)
            except UnsupportedSceneImageError as exc:
                return evaluate_scene_output(
                    case=case,
                    output=None,
                    prompt_version=SCENE_PROMPT_VERSION,
                    prompt_hash=prompt_hash,
                    judge_result=None,
                    actual_outcome="unsupported_image",
                    failure_reason=str(exc),
                )
            except Exception as exc:
                return evaluate_scene_output(
                    case=case,
                    output=None,
                    prompt_version=SCENE_PROMPT_VERSION,
                    prompt_hash=prompt_hash,
                    judge_result=None,
                    actual_outcome="graceful_failure",
                    failure_reason=f"graceful_failure: {exc}",
                )

            current_judge_result: SceneJudgeResult | None = None
            if judge is not None and output.confidence >= 0.65:
                current_judge_result = await asyncio.to_thread(
                    judge.judge,
                    case=case,
                    output=output,
                )

            return evaluate_scene_output(
                case=case,
                output=output,
                prompt_version=SCENE_PROMPT_VERSION,
                prompt_hash=prompt_hash,
                judge_result=current_judge_result,
                actual_outcome="analysis",
            )

    for result in await asyncio.gather(*(evaluate_case(case) for case in cases)):
        results.append(result)
        output_file.write_text(
            "".join(f"{item.model_dump_json()}\n" for item in results),
            encoding="utf-8",
        )
    return results


def _get_hard_failure_reason(output: SceneAnalysisResult) -> str:
    opener = output.opener.lower()
    if any(token in opener for token in META_OPENER_TOKENS):
        return "meta opener is not suitable for speaking practice"
    if len(output.opener.split()) > 20:
        return "opener is too long"
    if len(output.role.split()) > 4:
        return "role is too long"
    return ""


def _normalize_judge_result(
    value: dict[str, Any] | SceneJudgeResult | None,
) -> SceneJudgeResult | None:
    if value is None:
        return None
    if isinstance(value, SceneJudgeResult):
        return value
    return SceneJudgeResult.model_validate(value)


def _load_json(raw: str) -> dict[str, Any]:
    normalized = raw.strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`")
        if normalized.lower().startswith("json"):
            normalized = normalized[4:].strip()
    return json.loads(normalized)
