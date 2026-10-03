"""复盘引擎离线评测（RUN_REVIEW_EVAL=1 门控，CI 默认跳过）。

与 test_scene_engine_live.py / test_feedback_engine_live.py 同款约定：复盘
提示词（REVIEW_PROMPT）是产品核心资产，提示词改动后本地手动复跑做回归。
复盘评测是纯硬规则断言，不接 LLM judge。

手动复跑命令（会产生真实 LLM 调用费用，6 案每案至多主备多次重试）：

    RUN_REVIEW_EVAL=1 uv run pytest tests/modules/test_review_engine_live.py

依赖环境已配置 live 文本 provider（TEXT_PRIMARY_* / TEXT_FALLBACK_*）且
MODEL_RUNTIME_MODE=live；样例文件可用 REVIEW_EVAL_CASES_FILE 覆盖，缺省回落
仓库内提交的 fixtures；结果写 REVIEW_EVAL_OUTPUT
（默认 tmp/review_engine_eval/results.jsonl，逐行 JSON、绑定 REVIEW_PROMPT 哈希）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from api.core.config import settings
from api.modules.session_engine.evaluation import (
    load_review_evaluation_cases,
    run_review_evaluation,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REVIEW_EVAL") != "1",
    reason="Set RUN_REVIEW_EVAL=1 to run review_engine live evaluation.",
)

DEFAULT_CASES_FILE = Path(__file__).resolve().parents[1] / "fixtures" / "review_eval_cases.json"


@pytest.mark.anyio
async def test_review_engine_live_evaluation() -> None:
    """全样例 live 评测：结构契约 100%，弹性项阈值 0.8。"""
    if settings.model_runtime_mode.strip().lower() != "live":
        pytest.fail(
            "MODEL_RUNTIME_MODE must be 'live' before running the review evaluation "
            "(mock mode would short-circuit to template review copy and make these "
            "assertions meaningless)."
        )

    cases_file = os.getenv("REVIEW_EVAL_CASES_FILE") or str(DEFAULT_CASES_FILE)
    results = await run_review_evaluation(
        cases=load_review_evaluation_cases(cases_file),
        output_path=Path(os.getenv("REVIEW_EVAL_OUTPUT", "tmp/review_engine_eval/results.jsonl")),
    )

    assert results, "No review evaluation results were produced."

    # 结构契约 100%：结构失败会在真实链路触发 failover，全败时 summarize()
    # 上抛 ModelProviderError → 记 graceful_failure → 通过率 <1.0 在此显形。
    structure_rate = sum(result.structure_pass for result in results) / len(results)
    assert structure_rate == 1.0

    # 弹性项：中文 / 长度 / 无 id 泄漏 / 无关话题按 0.8 守门（graceful_failure
    # 样本会拉低比率，属于真实质量信号而非统计噪声）。
    chinese_rate = sum(result.chinese_pass for result in results) / len(results)
    length_rate = sum(result.length_pass for result in results) / len(results)
    no_scene_id_rate = sum(result.no_scene_id_pass for result in results) / len(results)
    topic_grounding_rate = sum(result.topic_grounding_pass for result in results) / len(results)
    assert chinese_rate >= 0.8
    assert length_rate >= 0.8
    assert no_scene_id_rate >= 0.8
    assert topic_grounding_rate >= 0.8
