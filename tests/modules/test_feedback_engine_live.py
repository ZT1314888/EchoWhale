"""反馈引擎离线评测（RUN_FEEDBACK_EVAL=1 门控，CI 默认跳过）。

与 test_coach_engine_live.py 同款约定（G8-FEEDBACK-1 升级为评测台形态）：
固定样例集（tests/fixtures/feedback_eval_cases.json）→ 硬规则五维 + 可选
LLM judge → JSONL 逐案落盘（绑定 prompt 哈希）。提示词或 schema 契约改动后
本地手动复跑做回归。

手动复跑命令（会产生真实 LLM 调用费用，8 案 × 每案 1 次调用）：

    RUN_FEEDBACK_EVAL=1 uv run pytest tests/modules/test_feedback_engine_live.py

可选 LLM judge（纠正准确 / 更自然 / 词汇有用，额外每案一次调用）：

    FEEDBACK_EVAL_JUDGE_PROVIDER=... FEEDBACK_EVAL_JUDGE_BASE_URL=... \
    FEEDBACK_EVAL_JUDGE_API_KEY=... FEEDBACK_EVAL_JUDGE_MODEL=... \
    RUN_FEEDBACK_EVAL=1 uv run pytest tests/modules/test_feedback_engine_live.py

依赖环境已配置 live 文本 provider（TEXT_PRIMARY_*）且 MODEL_RUNTIME_MODE=live；
样例文件可用 FEEDBACK_EVAL_CASES_FILE 覆盖，缺省回落仓库内提交的 fixtures
（合成文本、无真实图片依赖）；结果写 FEEDBACK_EVAL_OUTPUT
（默认 tmp/feedback_engine_eval/results.jsonl，逐行 JSON、绑定 prompt 哈希）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from api.core.config import settings
from api.modules.feedback_engine.evaluation import (
    FeedbackJudge,
    load_feedback_evaluation_cases,
    run_feedback_evaluation,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_FEEDBACK_EVAL") != "1",
    reason="Set RUN_FEEDBACK_EVAL=1 to run feedback_engine live evaluation.",
)

DEFAULT_CASES_FILE = Path(__file__).resolve().parents[1] / "fixtures" / "feedback_eval_cases.json"


@pytest.mark.anyio
async def test_feedback_engine_live_evaluation() -> None:
    """全样例 live 评测：绝对回归项 100%，弹性项与 coach 评测台同阈值。"""
    if settings.model_runtime_mode.strip().lower() != "live":
        pytest.fail(
            "MODEL_RUNTIME_MODE must be 'live' before running the feedback evaluation "
            "(mock mode would return canned feedback and make these assertions meaningless)."
        )

    cases_file = os.getenv("FEEDBACK_EVAL_CASES_FILE") or str(DEFAULT_CASES_FILE)
    results = await run_feedback_evaluation(
        cases=load_feedback_evaluation_cases(cases_file),
        output_path=Path(
            os.getenv("FEEDBACK_EVAL_OUTPUT", "tmp/feedback_engine_eval/results.jsonl")
        ),
        judge=FeedbackJudge.from_env(),
    )

    assert results, "No feedback evaluation results were produced."
    if all(result.actual_outcome != "reply" for result in results):
        pytest.fail(
            "Every case ended in graceful_failure. Live text providers are likely not "
            "configured. Set TEXT_PRIMARY_* (PROVIDER / BASE_URL / API_KEY / MODEL) and "
            "MODEL_RUNTIME_MODE=live; see the failure_reason field in the JSONL output."
        )

    # 绝对回归项：结构封闭集合与引用保真是提示词契约的硬底线，任何一案失败都不可接受
    # （original 编造引用 = 反馈不可信；九类之外自创分类 = 契约漂移）。
    structure_rate = sum(result.structure_pass for result in results) / len(results)
    quote_fidelity_rate = sum(result.quote_fidelity_pass for result in results) / len(results)
    assert structure_rate == 1.0
    assert quote_fidelity_rate == 1.0

    # 弹性项：live 模型偶发超约束可容忍，但硬规则与最终通过率须守住 0.8。
    hard_pass_rate = sum(result.hard_pass for result in results) / len(results)
    final_pass_rate = sum(result.final_pass for result in results) / len(results)
    assert hard_pass_rate >= 0.8
    assert final_pass_rate >= 0.8
