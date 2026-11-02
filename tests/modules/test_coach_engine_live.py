"""教练引擎离线评测（RUN_COACH_EVAL=1 门控，CI 默认跳过）。

与 test_scene_engine_live.py / test_feedback_engine_live.py 同款约定：提示词
与动态学员档案是产品核心资产，提示词/注入逻辑改动后本地手动复跑做回归。

手动复跑命令（会产生真实 LLM 调用费用，10 案 + 可选 judge 每案一次）：

    RUN_COACH_EVAL=1 uv run pytest tests/modules/test_coach_engine_live.py

可选 LLM judge（角色贴合 / CEFR 适配 / 一小步拉伸，额外每案一次调用）：

    COACH_EVAL_JUDGE_PROVIDER=... COACH_EVAL_JUDGE_BASE_URL=... \
    COACH_EVAL_JUDGE_API_KEY=... COACH_EVAL_JUDGE_MODEL=... \
    RUN_COACH_EVAL=1 uv run pytest tests/modules/test_coach_engine_live.py

依赖环境已配置 live 文本 provider（TEXT_PRIMARY_*）且 MODEL_RUNTIME_MODE=live；
样例文件可用 COACH_EVAL_CASES_FILE 覆盖，缺省回落仓库内提交的 fixtures
（合成文本、无真实图片依赖）；结果写 COACH_EVAL_OUTPUT
（默认 tmp/coach_engine_eval/results.jsonl，逐行 JSON、绑定 prompt 哈希）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from api.core.config import settings
from api.modules.coach_engine.evaluation import (
    CoachReplyJudge,
    load_coach_evaluation_cases,
    run_coach_evaluation,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_COACH_EVAL") != "1",
    reason="Set RUN_COACH_EVAL=1 to run coach_engine live evaluation.",
)

DEFAULT_CASES_FILE = Path(__file__).resolve().parents[1] / "fixtures" / "coach_eval_cases.json"


@pytest.mark.anyio
async def test_coach_engine_live_evaluation() -> None:
    """全样例 live 评测：绝对回归项 100%，弹性项与 scene 评测台同阈值。"""
    if settings.model_runtime_mode.strip().lower() != "live":
        pytest.fail(
            "MODEL_RUNTIME_MODE must be 'live' before running the coach evaluation "
            "(mock mode would return canned replies and make these assertions meaningless)."
        )

    cases_file = os.getenv("COACH_EVAL_CASES_FILE") or str(DEFAULT_CASES_FILE)
    results = await run_coach_evaluation(
        cases=load_coach_evaluation_cases(cases_file),
        output_path=Path(os.getenv("COACH_EVAL_OUTPUT", "tmp/coach_engine_eval/results.jsonl")),
        judge=CoachReplyJudge.from_env(),
    )

    assert results, "No coach evaluation results were produced."

    # 绝对回归项：仅英语与 meta 泄漏是提示词契约的硬底线，任何一案失败都不可接受。
    english_only_rate = sum(result.english_only_pass for result in results) / len(results)
    meta_leak_rate = sum(result.meta_leak_pass for result in results) / len(results)
    assert english_only_rate == 1.0
    assert meta_leak_rate == 1.0

    # 弹性项：live 模型偶发超约束可容忍，但硬规则与最终通过率须守住 0.8。
    hard_pass_rate = sum(result.hard_pass for result in results) / len(results)
    final_pass_rate = sum(result.final_pass for result in results) / len(results)
    assert hard_pass_rate >= 0.8
    assert final_pass_rate >= 0.8
