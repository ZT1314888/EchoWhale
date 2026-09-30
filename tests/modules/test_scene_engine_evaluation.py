from __future__ import annotations

from api.modules.scene_engine.evaluation import SceneEvaluationCase
from api.modules.scene_engine.evaluation import evaluate_scene_output
from api.modules.scene_engine.schema import SceneAnalysisResult


def test_evaluate_scene_output_fails_hard_checks_for_meta_opener() -> None:
    case = SceneEvaluationCase(
        sample_id="sample-meta",
        filename="office-ui.png",
        signed_url="https://signed.test/media/demo-user/office-ui.png",
        expected_scene="office",
        expected_visual_anchor_keywords=["glass wall"],
        expected_vocab_keywords=["meeting"],
        expected_role_keywords=["coworker"],
        sample_type="edge_case",
        expected_outcome="analysis",
    )
    result = evaluate_scene_output(
        case=case,
        output=SceneAnalysisResult(
            scene="office",
            role="coworker",
            opener="As an AI, I cannot see the image clearly.",
            visual_anchors=["glass wall", "logo"],
            vocab_candidates=["meeting", "visitor"],
            confidence=0.82,
        ),
        prompt_version="scene-v2",
        prompt_hash="hash-123",
        judge_result=None,
    )

    assert result.hard_checks_pass is False
    assert result.final_pass is False
    assert "meta opener" in result.failure_reason


def test_evaluate_scene_output_records_prompt_metadata_and_pass_state() -> None:
    case = SceneEvaluationCase(
        sample_id="sample-coffee",
        filename="coffee-shop.png",
        signed_url="https://signed.test/media/demo-user/coffee-shop.png",
        expected_scene="coffee_shop",
        expected_visual_anchor_keywords=["counter", "menu board"],
        expected_vocab_keywords=["latte", "order"],
        expected_role_keywords=["barista"],
        sample_type="normal",
        expected_outcome="analysis",
    )
    output = SceneAnalysisResult(
        scene="coffee_shop",
        role="barista",
        opener="Hi there, what can I get started for you today?",
        visual_anchors=["counter", "menu board"],
        vocab_candidates=["latte", "order", "size"],
        confidence=0.91,
    )

    result = evaluate_scene_output(
        case=case,
        output=output,
        prompt_version="scene-v2",
        prompt_hash="hash-456",
        judge_result={
            "final_pass": True,
            "role_fit_pass": True,
            "opener_natural_pass": True,
            "conversation_ready_pass": True,
            "reason": "usable",
        },
    )

    assert result.prompt_version == "scene-v2"
    assert result.prompt_hash == "hash-456"
    assert result.scene_match is True
    assert result.visual_anchor_match is True
    assert result.vocab_match is True
    assert result.vocab_value_pass is True
    assert result.final_pass is True


def test_evaluate_scene_output_rejects_low_value_vocab_candidates() -> None:
    case = SceneEvaluationCase(
        sample_id="sample-office",
        filename="office-room.png",
        signed_url="https://signed.test/media/demo-user/office-room.png",
        expected_scene="office",
        expected_visual_anchor_keywords=["glass wall"],
        expected_vocab_keywords=["meeting"],
        expected_role_keywords=["coworker"],
        sample_type="normal",
        expected_outcome="analysis",
    )

    result = evaluate_scene_output(
        case=case,
        output=SceneAnalysisResult(
            scene="office",
            role="coworker",
            opener="Welcome in. Are you here for the meeting?",
            visual_anchors=["glass wall", "sofa"],
            vocab_candidates=["table", "chair"],
            confidence=0.88,
        ),
        prompt_version="scene-v3",
        prompt_hash="hash-office",
        judge_result=None,
    )

    assert result.vocab_match is False
    assert result.vocab_value_pass is False
    assert result.final_pass is False


def test_evaluate_scene_output_accepts_expected_unsupported_edge_case() -> None:
    case = SceneEvaluationCase(
        sample_id="edge-black-001",
        filename="black.png",
        signed_url="https://signed.test/media/demo-user/black.png",
        expected_scene="general_chat",
        expected_visual_anchor_keywords=[],
        expected_vocab_keywords=[],
        expected_role_keywords=[],
        sample_type="edge_case",
        expected_outcome="unsupported_image",
    )

    result = evaluate_scene_output(
        case=case,
        output=None,
        prompt_version="scene-v2",
        prompt_hash="hash-unsupported",
        judge_result=None,
        actual_outcome="unsupported_image",
        failure_reason="Unsupported scene image",
    )

    assert result.actual_outcome == "unsupported_image"
    assert result.final_pass is True
    assert result.failure_reason == ""
