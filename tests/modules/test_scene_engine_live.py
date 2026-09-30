from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from api.modules.scene_engine.evaluation import load_scene_evaluation_cases
from api.modules.scene_engine.evaluation import run_scene_evaluation


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_SCENE_EVAL") != "1",
    reason="Set RUN_SCENE_EVAL=1 to run scene_engine live evaluation.",
)


def test_scene_engine_live_evaluation() -> None:
    cases_file = os.getenv("SCENE_EVAL_CASES_FILE")
    if not cases_file:
        pytest.skip("Set SCENE_EVAL_CASES_FILE to a JSON file with signed sample URLs.")

    results = asyncio.run(
        run_scene_evaluation(
            cases=load_scene_evaluation_cases(cases_file),
            output_path=Path(os.getenv("SCENE_EVAL_OUTPUT", "tmp/scene_engine_eval/results.jsonl")),
            max_concurrency=int(os.getenv("SCENE_EVAL_MAX_CONCURRENCY", "5")),
        )
    )

    assert results, "No scene evaluation results were produced."

    normal_results = [item for item in results if item.sample_type == "normal"]
    edge_results = [item for item in results if item.sample_type == "edge_case"]

    if normal_results:
        scene_match_rate = sum(item.scene_match for item in normal_results) / len(normal_results)
        practice_ready_rate = sum(item.final_pass for item in normal_results) / len(normal_results)
        visual_anchor_match_rate = (
            sum(item.visual_anchor_match for item in normal_results) / len(normal_results)
        )
        vocab_match_rate = sum(item.vocab_match for item in normal_results) / len(normal_results)
        vocab_value_rate = (
            sum(item.vocab_value_pass for item in normal_results) / len(normal_results)
        )
        assert scene_match_rate >= 0.8
        assert practice_ready_rate >= 0.8
        assert visual_anchor_match_rate >= 0.7
        assert vocab_match_rate >= 0.7
        assert vocab_value_rate >= 0.8

    if edge_results:
        assert all(item.expected_outcome == item.actual_outcome for item in edge_results)
